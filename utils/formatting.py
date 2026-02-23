# kalyn/utils/formatting.py

def format_rupiah(n: int) -> str:
    """
    Format integer to Indonesian-style with '.' as thousands separator.
    Example: 1234567 -> "1.234.567"
    """
    return f"{n:,.0f}".replace(",", ".")