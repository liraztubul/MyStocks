import os

# Must run before any app import: Settings requires a JWT secret and is built at import time.
os.environ.setdefault("JWT_SECRET_KEY", "test-only-secret-key-at-least-32-characters")
# Tests never use a real CoinGecko key, even if the developer's .env (read by Settings) has one.
os.environ["COINGECKO_DEMO_API_KEY"] = ""
