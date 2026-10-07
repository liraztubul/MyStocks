# Restore drill

Restores the latest encrypted backup into a **throwaway local PostgreSQL container** and checks
it. It never touches production: the script reads no database URL, publishes no port, and
talks only to its own container, `mystocks-restore-drill`.

Run it after any change to the backup workflow, and from time to time anyway: a backup is only
as good as its last successful restore.

## What happens

1. Finds the newest successful run of the "Database backup" workflow and downloads its artifact
   (still encrypted) into a temporary folder, which is deleted when the script ends.
2. Starts `postgres:18`. The image is read from `PG_CLIENT_IMAGE` in
   `.github/workflows/backup.yml`, so the drill always uses the backup's own PostgreSQL version.
3. Decrypts the dump with your passphrase, streaming it straight into the container. The
   plaintext never touches your disk and disappears with the container.
4. Restores it with `pg_restore --exit-on-error`, then prints:
   - rows per table;
   - the Alembic schema version, orphaned transactions (must be 0), non-lowercase emails
     (must be 0) and the newest trade's time;
   - one user's latest 25 transactions (by default the user with the most).

If anything fails after the container started, the script removes the container itself.

## One-time setup (your machine)

- **Docker Desktop**, running.
- **Git Bash** (comes with Git for Windows; it includes `gpg`). Run every command below in Git
  Bash from the repository root.
- **GitHub CLI**, logged in to an account that can read this repository's Actions artifacts:
  ```bash
  winget install --id GitHub.cli     # then open a new Git Bash window
  gh auth login                      # GitHub.com, HTTPS, log in with a browser
  ```
  Without `gh`, download the artifact by hand instead (see "Without the GitHub CLI" below).

## Run the drill

```bash
# 1. Go to the repository root.
cd ~/Documents/MyStocks

# 2. Type the backup passphrase. -s keeps it off the screen, and because it's read rather than
#    typed into a command, it doesn't end up in your shell history.
read -rs BACKUP_PASSPHRASE; export BACKUP_PASSPHRASE

# 3. Run the drill (newest backup).
scripts/restore-drill.sh

#    Or show a specific user's transactions:
scripts/restore-drill.sh --user you@example.com

# 4. Forget the passphrase in this shell.
unset BACKUP_PASSPHRASE
```

What a good run looks like: every table listed with plausible counts, `orphan_transactions`
and `non_lowercase_emails` both 0, `newest_trade` close to your latest real trade, and the
user's transactions matching what the app shows. Compare a couple of counts with production
(the app's transactions page, or the Neon console) if you want a stronger check.

To look around in the restored copy before cleaning up:

```bash
docker exec -it mystocks-restore-drill psql -U postgres -d restored
```

## Clean up

```bash
scripts/restore-drill.sh --cleanup
```

This removes the container, and with it the restored data. The downloaded artifact is already
gone (the script deletes its temporary folder on exit). Optionally free the image space too:
`docker image rm postgres:18` (only if nothing else uses it).

## Without the GitHub CLI

1. GitHub → Actions → **Database backup** → the newest green run → **Artifacts** → download
   `mystocks-db-<run id>`. It arrives as a zip.
2. Unzip it: inside is `mystocks.dump.gpg` (still encrypted).
3. Run the drill on that file, then delete the zip and the `.gpg`:
   ```bash
   read -rs BACKUP_PASSPHRASE; export BACKUP_PASSPHRASE
   scripts/restore-drill.sh --file ~/Downloads/mystocks.dump.gpg
   unset BACKUP_PASSPHRASE
   ```

## When it fails

| Message | Meaning |
|---|---|
| `BACKUP_PASSPHRASE is not set` | Step 2 wasn't run in this shell. |
| `decryption failed (wrong BACKUP_PASSPHRASE?)` | Wrong passphrase, or the file isn't a backup. |
| `no successful backup run found` | No green backup in the last 14 days (artifacts expire), or the workflow is disabled. |
| `a container named mystocks-restore-drill already exists` | A previous drill is still there: run `--cleanup`. |
| `gh is not logged in` | Run `gh auth login`. |

## Restoring into Neon for real

The drill deliberately doesn't. For a real recovery, follow "Backups and restore" in the README:
restore into a **new** Neon branch or database first, check it with the same queries, and only
then point `DATABASE_URL` at it.
