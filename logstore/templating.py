import re

NODE_RE = re.compile(r"\b(node|gige|Interconnect)-?[\w-]*\d\b")
NUMBER_RE = re.compile(r"\d+")

# applied in order
MASKS = [
    (re.compile(r"\\04[27].*?\\04[27]"), "<Q>"),
    (re.compile(r"\b0x[0-9a-fA-F]+\b"), "<HEX>"),
    # a set of nodes in brackets, e.g. node-[0-2\ 32-34] or node-D[0-7]
    (re.compile(r"\bnode-D?\[[^\]]*\]"), "<NODE>"),
    (NODE_RE, "<NODE>"),
    (NUMBER_RE, "<N>"),
    # asterisks printed where a number could not be shown, e.g. Fan speeds ( 3552 **** 3515 )
    (re.compile(r"(?<!\S)\*+(?!\S)"), "<N>"),
    (re.compile(r"\s+"), " "),
    # a list becomes one item, so its length does not change the template
    (re.compile(r"<NODE>(?:\\ <NODE>)+"), "<NODE>"),
    (re.compile(r"<N>(?:\\ <N>)+"), "<N>"),
    (re.compile(r"<NODE> <HEX> <ok>(?: <NODE> <HEX> <ok>)+"), "<NODE> <HEX> <ok>"),
]
# what each placeholder stands for
PLACEHOLDERS = {
    "<N>": "a number, a list of numbers, or asterisks where a number could not be shown",
    "<NODE>": "a node or switch name, or a list or set of them",
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
