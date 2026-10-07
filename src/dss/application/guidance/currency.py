"""Currency formatting for grounded scheme responses."""


def _format_currency(amount: int | float | None) -> str | None:
    """Format rupee values compactly for free-form answers."""
    if amount is None:
        return None
    if amount >= 100000:
        lakhs = amount / 100000
        return f"₹{lakhs:.1f} lakh" if lakhs != int(lakhs) else f"₹{int(lakhs)} lakh"
    return f"₹{amount:,.0f}"
