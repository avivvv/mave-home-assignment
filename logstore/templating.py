import re

# applied in order
MASKS = [
    (re.compile(r"\\04[27].*?\\04[27]"), "<Q>"),
    (re.compile(r"\b0x[0-9a-fA-F]+\b"), "<HEX>"),
    (re.compile(r"\b(node|gige|Interconnect)-?[\w-]*\d\b"), "<NODE>"),
    (re.compile(r"\d+"), "<N>"),
    (re.compile(r"\s+"), " "),
]


def to_template(message):
    for pattern, replacement in MASKS:
        message = pattern.sub(replacement, message)
    return message.strip()
