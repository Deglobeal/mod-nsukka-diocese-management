"""Phone-number normalization for notification delivery."""


def normalize_nigerian_phone(value: str) -> str:
    """
    Normalize an accepted Nigerian phone number to E.164 format.

    Accepted examples:
        08012345678
        +2348012345678
        +234 801 234 5678
        (0801) 234-5678
    """
    if not isinstance(value, str):
        raise ValueError("A Nigerian phone number must be a string.")

    normalized = "".join(
        char for char in value.strip() if char not in " \t\r\n()-"
    )

    if (
        len(normalized) == 11
        and normalized.startswith("0")
        and normalized[1:].isascii()
        and normalized[1:].isdigit()
    ):
        return f"+234{normalized[1:]}"

    if (
        len(normalized) == 14
        and normalized.startswith("+234")
        and normalized[4:].isascii()
        and normalized[4:].isdigit()
    ):
        return normalized

    raise ValueError("Enter a valid Nigerian phone number.")
