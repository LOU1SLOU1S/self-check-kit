def parse_price(text):
    """Parse a price string such as "$5.00" or "$1,234.50" into a float."""
    return float(text.replace("$", ""))
