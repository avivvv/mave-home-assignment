import pytest

from logstore.templating import MASKS, PLACEHOLDERS, number_slots, to_template


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
            "inconsistent nodesets node-2 0x0000000e <ok> node-0 0x00000002 <ok> ",
            "inconsistent nodesets <NODE> <HEX> <ok> <NODE> <HEX> <ok>",
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
        pytest.param("", "", id="empty message"),
    ],
)
def test_to_template_masks_the_variable_parts(message, template):
    assert to_template(message) == template


def test_messages_that_differ_only_in_values_share_a_template():
    assert to_template("ambient=36") == to_template("ambient=27")


def test_number_slots_are_the_values_behind_each_masked_number_in_order():
    assert number_slots("Fan speeds ( 3552 3534 )") == ["3552", "3534"]


def test_number_slots_leave_out_digits_inside_node_names_hex_and_quoted_names():
    assert number_slots(r"inconsistent nodesets node-12 0x1f \042ee0\042 <ok>") == []


def test_every_placeholder_the_masks_produce_has_a_meaning():
    produced = {replacement for _, replacement in MASKS if replacement.startswith("<")}
    assert produced == set(PLACEHOLDERS) == {"<Q>", "<HEX>", "<NODE>", "<N>"}
