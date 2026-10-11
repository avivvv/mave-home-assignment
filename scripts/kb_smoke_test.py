"""Smoke test of the knowledge base: build it from kb/, find what must be there, get nothing for what cannot be, run the tool.

No model is called. Run from the repo root: python -m scripts.kb_smoke_test
"""
import sys

from agent.knowledge import KB_DIR, Knowledge
from agent.tools import LogTools, available_tools, run_tool
from logstore.db import connect, create_indexes, init_schema

# a question the fact sheet answers, and the passage that answers it
MUST_FIND = ("which node serves storage612", "cluster_facts#which-nodes-serve-filesystems")
# words that appear nowhere in the knowledge
CANNOT_FIND = "zebra giraffe saxophone"


def main():
    sys.stdout.reconfigure(errors="replace")
    print(f"1. build the knowledge from {KB_DIR}")
    knowledge = Knowledge()
    files = sorted({passage.passage_id.split("#")[0] for passage in knowledge.passages})
    print(f"   {len(knowledge.passages)} passages from {len(files)} file(s): {', '.join(files)}")
    for passage in knowledge.passages:
        print(f"   {passage.passage_id}: {len(passage.text)} characters")
    assert knowledge.passages, "no passage was indexed"
    assert "sources" not in files, "kb/sources.md has no header and must not be indexed"

    print(f"2. search for something that must exist: {MUST_FIND[0]!r}")
    found = knowledge.search(MUST_FIND[0])
    print("   " + ", ".join(passage.passage_id for passage in found))
    assert found and found[0].passage_id == MUST_FIND[1], f"expected {MUST_FIND[1]} first"
    assert "node-20" in found[0].text

    print(f"3. search for something that cannot exist: {CANNOT_FIND!r}")
    assert knowledge.search(CANNOT_FIND) == []
    print("   nothing, as it should be")

    print("4. the tool, with knowledge on and off")
    conn = connect(":memory:")
    init_schema(conn)
    create_indexes(conn)
    on, off = LogTools(conn, knowledge=knowledge), LogTools(conn)
    assert [tool.name for tool in available_tools(on)][-1] == "search_knowledge"
    assert "search_knowledge" not in [tool.name for tool in available_tools(off)]
    result = run_tool(on, "search_knowledge", {"reasoning": "smoke test", "query": MUST_FIND[0], "k": 2})
    assert result.passage_ids[0] == MUST_FIND[1] and len(result.passage_ids) <= 2 and f"[{MUST_FIND[1]}]" in result.text
    print(f"   on: {len(result.passage_ids)} passages, the first is {result.passage_ids[0]}")
    refused = run_tool(off, "search_knowledge", {"reasoning": "smoke test", "query": MUST_FIND[0]})
    assert refused.text.startswith("error: unknown tool")
    print(f"   off: {refused.text[:70]}...")
    print("SMOKE TEST PASSED")


if __name__ == "__main__":
    main()
