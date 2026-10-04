import pytest

from logstore.templating import to_template


@pytest.mark.parametrize(
    "message, template",
    [
        ("Linkerror event interval expired", "Linkerror event interval expired"),
        ("ambient=36", "ambient=<N>"),
        ("Command Failed on: node-3", "Command Failed on: <NODE>"),
        (
            "inconsistent nodesets node-2 0x0000000e <ok> node-0 0x00000002 <ok> ",
            "inconsistent nodesets <NODE> <HEX> <ok> <NODE> <HEX> <ok>",
        ),
        (
            r"Component State Change: Component \042ee0\042 is in the available state (HWID=23)",
            "Component State Change: Component <Q> is in the available state (HWID=<N>)",
        ),
        ("wait  (command 1894)", "wait (command <N>)"),
        ("", ""),
    ],
)
def test_to_template(message, template):
    assert to_template(message) == template


def test_messages_that_differ_only_in_values_share_a_template():
    assert to_template("ambient=36") == to_template("ambient=27")
