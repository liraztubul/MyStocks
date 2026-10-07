#!/usr/bin/env bash
# Restore drill: restore the latest encrypted backup into a throwaway local PostgreSQL container
# and print sanity checks. Never touches production: it reads no database URL, publishes no
# port, and only ever talks to its own container. See docs/restore.md.
#
#   export BACKUP_PASSPHRASE   (set it with: read -rs BACKUP_PASSPHRASE; export BACKUP_PASSPHRASE)
#   scripts/restore-drill.sh                      # download the latest backup artifact with gh
#   scripts/restore-drill.sh --file path.dump.gpg # or use one you downloaded yourself
#   scripts/restore-drill.sh --user someone@example.com   # whose transactions to show
#   scripts/restore-drill.sh --cleanup            # remove the drill container
set -euo pipefail

CONTAINER=mystocks-restore-drill
DB=restored
REPO_ROOT=$(cd "$(dirname "$0")/.." && pwd)
WORKFLOW="$REPO_ROOT/.github/workflows/backup.yml"
# Git Bash on Windows would otherwise rewrite container paths like /tmp/... into C:\...
export MSYS_NO_PATHCONV=1

fail() { echo "restore-drill: $*" >&2; exit 1; }

FILE=""
DRILL_USER=""
while [ $# -gt 0 ]; do
  case "$1" in
    --file) FILE=${2:?--file needs a path}; shift 2 ;;
    --user) DRILL_USER=${2:?--user needs an email}; shift 2 ;;
    --cleanup)
      # Checked first: docker rm -f succeeds even when there's nothing to remove.
      if docker ps -a --format '{{.Names}}' | grep -qx "$CONTAINER"; then
        docker rm -f "$CONTAINER" >/dev/null && echo "Removed container $CONTAINER."
      else
        echo "No container named $CONTAINER (nothing to clean up)."
      fi
      exit 0 ;;
    -h|--help) sed -n '2,11p' "$0"; exit 0 ;;
    *) fail "unknown option: $1 (try --help)" ;;
  esac
done

# --- Preconditions -------------------------------------------------------------------------------
command -v docker >/dev/null || fail "docker is not installed or not on PATH"
docker info >/dev/null 2>&1 || fail "docker is not running"
command -v gpg >/dev/null || fail "gpg is not installed (Git for Windows includes it)"
[ -n "${BACKUP_PASSPHRASE:-}" ] || fail "BACKUP_PASSPHRASE is not set (see docs/restore.md, step 2)"
if docker ps -a --format '{{.Names}}' | grep -qx "$CONTAINER"; then
  fail "a container named $CONTAINER already exists; remove it first: $0 --cleanup"
fi

# The same PostgreSQL major version the backup was made with (read from the workflow), so the
# drill restores exactly what production backups contain.
IMAGE=$(sed -n 's/^ *PG_CLIENT_IMAGE: *\([^ ]*\).*/\1/p' "$WORKFLOW" | head -1)
[ -n "$IMAGE" ] || fail "couldn't read PG_CLIENT_IMAGE from $WORKFLOW"

WORK=$(mktemp -d)
STARTED=0
DONE=0
# However the script ends: remove the downloaded (still encrypted) artifact, and if the drill
# failed after starting its container, remove that too so the next run can start clean.
cleanup_on_exit() {
  rm -rf "$WORK"
  if [ "$STARTED" = 1 ] && [ "$DONE" = 0 ]; then
    docker rm -f "$CONTAINER" >/dev/null 2>&1 && echo "Removed the failed drill's container." >&2
  fi
}
trap cleanup_on_exit EXIT

# --- 1. Get the encrypted dump -------------------------------------------------------------------
if [ -z "$FILE" ]; then
  command -v gh >/dev/null || fail "gh (GitHub CLI) is not installed; install it or use --file"
  gh auth status >/dev/null 2>&1 || fail "gh is not logged in: run gh auth login"
  RUN=$(gh run list --repo liraztubul/MyStocks --workflow backup.yml --status success --limit 1 \
    --json databaseId,createdAt --jq '.[0] | "\(.databaseId) \(.createdAt)"')
  [ -n "$RUN" ] || fail "no successful backup run found (artifacts are kept 14 days)"
  RUN_ID=${RUN%% *}
  echo "Latest successful backup: run $RUN_ID, created ${RUN#* }"
  gh run download "$RUN_ID" --repo liraztubul/MyStocks --name "mystocks-db-$RUN_ID" --dir "$WORK"
  FILE="$WORK/mystocks.dump.gpg"
fi
[ -f "$FILE" ] || fail "no such file: $FILE"
echo "Encrypted dump: $(wc -c <"$FILE" | tr -d ' ') bytes"

# --- 2. Throwaway PostgreSQL ---------------------------------------------------------------------
# No -p: the database is reachable only from inside the container. The password is random and
# never shown; nothing here needs it (psql runs inside the container as the postgres user).
echo "Starting $CONTAINER ($IMAGE)..."
docker run -d --name "$CONTAINER" -e POSTGRES_DB="$DB" \
  -e POSTGRES_PASSWORD="$(head -c 24 /dev/urandom | od -An -tx1 | tr -d ' \n')" \
  "$IMAGE" >/dev/null
STARTED=1
for _ in $(seq 1 60); do
  docker exec "$CONTAINER" pg_isready -U postgres -d "$DB" >/dev/null 2>&1 && break
  sleep 1
done
docker exec "$CONTAINER" pg_isready -U postgres -d "$DB" >/dev/null 2>&1 || fail "postgres didn't start"
sleep 2 # the image restarts the server once after initialising

# --- 3. Decrypt straight into the container and restore ------------------------------------------
# The passphrase goes to gpg on file descriptor 3, never as an argument (which other processes
# could see) and never printed. The plaintext dump never touches this machine's disk: it's
# streamed into the container and deleted with it.
echo "Decrypting into the container..."
gpg --batch --quiet --pinentry-mode loopback --passphrase-fd 3 --decrypt "$FILE" 3<<<"$BACKUP_PASSPHRASE" \
  | docker exec -i "$CONTAINER" sh -c 'cat > /tmp/mystocks.dump' \
  || fail "decryption failed (wrong BACKUP_PASSPHRASE?)"
echo "Restoring..."
docker exec "$CONTAINER" pg_restore --no-owner --no-privileges --exit-on-error \
  -U postgres -d "$DB" /tmp/mystocks.dump
docker exec "$CONTAINER" rm -f /tmp/mystocks.dump

# --- 4. Sanity checks ----------------------------------------------------------------------------
psql_drill() { docker exec -i "$CONTAINER" psql -X -q -U postgres -d "$DB" -v ON_ERROR_STOP=1 "$@"; }

echo
echo "== Rows per table"
psql_drill <<'SQL'
SELECT table_name AS "table",
       (xpath('/row/n/text()', query_to_xml(format('SELECT count(*) AS n FROM public.%I', table_name),
                                            false, true, '')))[1]::text::bigint AS "rows"
FROM information_schema.tables
WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
ORDER BY 1;
SQL

echo "== Schema version and integrity"
psql_drill <<'SQL'
SELECT (SELECT version_num FROM alembic_version)                         AS alembic_version,
       (SELECT count(*) FROM transactions t
         WHERE NOT EXISTS (SELECT 1 FROM users u WHERE u.id = t.user_id)) AS orphan_transactions,
       (SELECT count(*) FROM users WHERE email <> lower(email))          AS non_lowercase_emails,
       (SELECT max(executed_at) FROM transactions)                       AS newest_trade;
SQL

echo "== One user's transactions"
# Default: the user with the most transactions. Emails are shown: this is your own data, on your
# own machine, in a container that only you can reach.
psql_drill -v who="$DRILL_USER" <<'SQL'
WITH chosen AS (
  SELECT u.id, u.email FROM users u
  WHERE u.email = lower(:'who')
     OR (:'who' = '' AND u.id = (SELECT user_id FROM transactions
                                 GROUP BY user_id ORDER BY count(*) DESC LIMIT 1))
)
SELECT c.email, t.symbol, t.side, t.quantity, t.price, t.fee, t.executed_at
FROM chosen c JOIN transactions t ON t.user_id = c.id
ORDER BY t.executed_at DESC
LIMIT 25;
SQL

DONE=1
echo
echo "Drill done. Explore with:  docker exec -it $CONTAINER psql -U postgres -d $DB"
echo "Clean up with:             $0 --cleanup"
