from decimal import Decimal

from django import template

from finance.formatting import format_idr


register = template.Library()


@register.filter
def idr(value):
    return format_idr(value)


@register.filter
def pct(value):
    try:
        number = Decimal(value or 0) * Decimal("100")
    except Exception:
        number = Decimal("0")
    return f"{number:.1f}%"


@register.filter
def progress(value):
    try:
        number = float(value or 0)
    except Exception:
        number = 0
    return max(0, min(100, number))


@register.filter
def format_cell(value):
    if isinstance(value, Decimal):
        return format_idr(value)
    return value
