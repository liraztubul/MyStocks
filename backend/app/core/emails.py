def normalize_email(value: str) -> str:
    """The one canonical form of an email address: trimmed and lowercase.

    Registration, login and the stock-data allowlist all compare through this, and a database
    CHECK keeps every stored address in this form, so the unique index on users.email is
    effectively case-insensitive.
    """
    return value.strip().lower()
