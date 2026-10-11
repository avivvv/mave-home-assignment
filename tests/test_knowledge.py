"""The knowledge base: markdown files split into passages, found by the words they share with a query."""
import pytest

from agent.knowledge import Knowledge, Passage, from_config, load_passages

FACTS = """---
id: facts
title: Cluster fact sheet
source_urls: []
categories: [filesystem]
---

# Cluster fact sheet

Every statement is marked [data] or [guess].

## Node naming

- [data] `node-0` to `node-255` are the compute nodes.
- [guess] `gige1` to `gige8` are ethernet switches.

## Which nodes serve filesystems

- [data] The storage file domain storage612 is served by node-20.
"""

NOTES = """# Sources

A list of documents, with no header, so it is not knowledge.
"""


@pytest.fixture
def kb_dir(tmp_path):
    (tmp_path / "facts.md").write_text(FACTS, encoding="utf-8")
    (tmp_path / "notes.md").write_text(NOTES, encoding="utf-8")
    return tmp_path


@pytest.fixture
def knowledge(kb_dir):
    return Knowledge(kb_dir)


class TestPassages:
    def test_a_file_with_a_header_is_split_at_its_headings_into_passages_with_ids(self, kb_dir):
        passages = load_passages(kb_dir / "facts.md")
        assert [p.passage_id for p in passages] == ["facts#cluster-fact-sheet", "facts#node-naming", "facts#which-nodes-serve-filesystems"]
        assert [p.title for p in passages] == ["Cluster fact sheet", "Node naming", "Which nodes serve filesystems"]
        assert passages[1].text == "- [data] `node-0` to `node-255` are the compute nodes.\n- [guess] `gige1` to `gige8` are ethernet switches."
        assert passages[0].text.startswith("# Cluster fact sheet") and passages[0].text.endswith("[guess].")

    def test_a_file_with_no_header_gives_no_passage(self, kb_dir):
        assert load_passages(kb_dir / "notes.md") == []

    def test_the_knowledge_holds_the_passages_of_every_file_with_a_header(self, knowledge):
        assert len(knowledge.passages) == 3 and all(isinstance(p, Passage) for p in knowledge.passages)
        assert knowledge.get("facts#node-naming").title == "Node naming" and knowledge.get("facts#nothing") is None


class TestSearch:
    def test_a_query_made_of_a_passage_own_words_returns_that_passage_first(self, knowledge):
        found = knowledge.search("which node serves the storage file domain storage612")
        assert found[0].passage_id == "facts#which-nodes-serve-filesystems"

    def test_a_query_that_shares_no_word_with_any_passage_returns_nothing(self, knowledge):
        assert knowledge.search("zebra giraffe") == []

    def test_only_passages_that_share_a_word_are_returned(self, knowledge):
        assert [p.passage_id for p in knowledge.search("storage612")] == ["facts#which-nodes-serve-filesystems"]

    def test_k_caps_the_result(self, knowledge):
        # two passages mention a node; the preamble does not
        assert len(knowledge.search("node", k=1)) == 1 and len(knowledge.search("node", k=5)) == 2

    def test_letter_case_and_punctuation_do_not_matter(self, knowledge):
        assert knowledge.search("NODE-20")[0].passage_id == "facts#which-nodes-serve-filesystems"

    def test_an_empty_folder_gives_an_empty_knowledge(self, tmp_path):
        empty = Knowledge(tmp_path)
        assert empty.passages == [] and empty.search("node") == []


def test_the_configuration_says_whether_there_is_knowledge():
    assert isinstance(from_config({"knowledge": True}), Knowledge)
    assert from_config({"knowledge": False}) is None and from_config({}) is None


def test_the_fact_sheet_of_the_repository_is_knowledge_and_the_source_list_is_not():
    knowledge = Knowledge()
    ids = [p.passage_id for p in knowledge.passages]
    assert "cluster_facts#domains" in ids and "cluster_facts#which-nodes-serve-filesystems" in ids
    assert all(passage_id.startswith("cluster_facts#") for passage_id in ids)
    assert knowledge.search("storage612")[0].passage_id == "cluster_facts#which-nodes-serve-filesystems"
