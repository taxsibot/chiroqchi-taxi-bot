def format_currency(amount: int, lang: str = "uz") -> str:
    """Return formatted currency string with spaces as thousands separator."""
    formatted = f"{amount:,}".replace(",", " ")
    return f"{formatted} so'm"
