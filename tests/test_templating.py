import re

import pytest

from logstore.templating import MASKS, PLACEHOLDERS, to_template


@pytest.mark.parametrize(
    "message, template",
    [
        pytest.param("Linkerror event interval expired", "Linkerror event interval expired", id="nothing to mask"),
        pytest.param("ambient=36", "ambient=<N>", id="number"),
        pytest.param("temp 15.560 C", "temp <N>.<N> C", id="decimal number"),
        pytest.param("ip 5.5.226.0 via alt0", "ip <N>.<N>.<N>.<N> via alt<N>", id="ip address and digit in a word"),
        pytest.param("Command Failed on: node-3", "Command Failed on: <NODE>", id="node name"),
        pytest.param("gige7 link down", "<NODE> link down", id="gige name"),
        pytest.param("Interconnect-1T03 ok", "<NODE> ok", id="switch name"),
        pytest.param("nodes 5 and node 7", "nodes <N> and node <N>", id="the word node is not a name"),
        pytest.param(
            "inconsistent nodesets node-2 0x0000000e <ok> ",
            "inconsistent nodesets <NODE> <HEX> <ok>",
            id="hex before number",
        ),
        pytest.param("addr 0x1F", "addr <HEX>", id="hex with capital digits"),
        pytest.param(
            r"Component State Change: Component \042ee0\042 is in the available state (HWID=23)",
            "Component State Change: Component <Q> is in the available state (HWID=<N>)",
            id="double-quoted name",
        ),
        pytest.param(r"Component \047alt0\047 ok", "Component <Q> ok", id="single-quoted name"),
        pytest.param("wait  (command 1894)", "wait (command <N>)", id="repeated spaces"),
        pytest.param("Fan speeds ( 3552 3534 )", "Fan speeds ( <N> <N> )", id="numbers apart by a space are not a list"),
        pytest.param(r"psu failure\ ambient=28", r"psu failure\ ambient=<N>", id="a list separator outside a list"),
        pytest.param(
            "Fan speeds ( 3552 3534 3375 **** 3515 3479 )",
            "Fan speeds ( <N> <N> <N> <N> <N> <N> )",
            id="asterisks in place of a number",
        ),
        pytest.param("", "", id="empty message"),
    ],
)
def test_to_template_masks_the_variable_parts(message, template):
    assert to_template(message) == template


@pytest.mark.parametrize(
    "one_item, many_items, template",
    [
        pytest.param(
            "Targeting domains:node-D0 and nodes:node-3",
            r"Targeting domains:node-D[0-7] and nodes:node-[0-2\ 32-34\ 64-66]",
            "Targeting domains:<NODE> and nodes:<NODE>",
            id="node sets in brackets",
        ),
        pytest.param(
            "Targeting domains:node-D7 and nodes:node-225 child of command 1984",
            r"Targeting domains:node-D[0\ 2-3] and nodes:node-[232-233\ 244-245] child of command 1885",
            "Targeting domains:<NODE> and nodes:<NODE> child of command <N>",
            id="node sets followed by more text",
        ),
        pytest.param(
            "Command Failed on: node-3",
            r"Command Failed on: node-254\ node-224\ node-226",
            "Command Failed on: <NODE>",
            id="node names",
        ),
        pytest.param(
            "Failed subcommands 3503",
            r"Failed subcommands 3549\ 3550\ 3551",
            "Failed subcommands <N>",
            id="numbers",
        ),
        pytest.param(
            "inconsistent nodesets node-2 0x0000000e <ok> node-0 0x00000002 <ok> ",
            "inconsistent nodesets node-9 0x1fffffffc <ok> node-8 0x0000dffc <ok> node-7 0x1fffffffe <ok> ",
            "inconsistent nodesets <NODE> <HEX> <ok>",
            id="nodesets",
        ),
    ],
)
def test_a_list_gives_the_same_template_whatever_its_length(one_item, many_items, template):
    assert to_template(one_item) == template
    assert to_template(many_items) == template


def test_messages_that_differ_only_in_values_share_a_template():
    assert to_template("ambient=36") == to_template("ambient=27")


def test_every_placeholder_the_masks_produce_has_a_meaning():
    produced = {name for _, replacement in MASKS for name in re.findall(r"<[A-Z]+>", replacement)}
    assert produced == set(PLACEHOLDERS) == {"<Q>", "<HEX>", "<NODE>", "<N>"}
