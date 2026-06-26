from decimal import Decimal


def format_idr(value) -> str:
    try:
        number = Decimal(value or 0)
    except Exception:
        number = Decimal("0")
    formatted = f"{number:,.0f}".replace(",", ".")
    return f"Rp{formatted}"

