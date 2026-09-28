"""Money helpers. All amounts are stored as integer paise (1 rupee = 100 paise)."""


def format_inr(paise, show_paise=False):
    """Format paise as an Indian-grouped rupee string, e.g. 12345600 -> '₹1,23,456'."""
    if paise is None:
        return "—"
    negative = paise < 0
    paise = abs(int(paise))
    rupees, rem = divmod(paise, 100)
    digits = str(rupees)
    if len(digits) > 3:
        head, tail = digits[:-3], digits[-3:]
        groups = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        digits = ",".join(groups) + "," + tail
    text = f"₹{digits}"
    if show_paise:
        text += f".{rem:02d}"
    return f"-{text}" if negative else text


def rupees_to_paise(rupees):
    return int(round(float(rupees) * 100))
