import re

NODE_RE = re.compile(r"\b(node|gige|Interconnect)-?[\w-]*\d\b")
NUMBER_RE = re.compile(r"\d+")

# applied in order
MASKS = [
    (re.compile(r"\\04[27].*?\\04[27]"), "<Q>"),
    (re.compile(r"\b0x[0-9a-fA-F]+\b"), "<HEX>"),
    (NODE_RE, "<NODE>"),
    (NUMBER_RE, "<N>"),
    (re.compile(r"\s+"), " "),
]
# what each placeholder stands for
PLACEHOLDERS = {
    "<N>": "a number",
    "<NODE>": "a node or switch name",
    "<HEX>": "a hexadecimal value",
    "<Q>": "a quoted name",
}


def to_template(message):
    for pattern, replacement in MASKS:
        message = pattern.sub(replacement, message)
    return message.strip()


def number_slots(message):
    """The values behind each <N> of the message's template, in order."""
    for pattern, replacement in MASKS:
        if pattern is NUMBER_RE:
            return pattern.findall(message)
        message = pattern.sub(replacement, message)
