import os

# Must run before any app import: Settings requires a JWT secret and is built at import time.
os.environ.setdefault("JWT_SECRET_KEY", "test-only-secret-key-at-least-32-characters")
