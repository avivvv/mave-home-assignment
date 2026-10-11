"""The knowledge base: the markdown files of kb/ split into passages, and found by the words they share with a query.

A file is knowledge when it starts with a front-matter header that names its id. It is split at its `##` headings;
each section is a passage, and so is the text before the first heading. A passage id is `<file id>#<heading slug>`,
and that id is what a citation names. Passages are ranked by BM25: lexical, so a paraphrase that shares no word is missed.
"""
import re
from dataclasses import dataclass
from pathlib import Path

import yaml
from rank_bm25 import BM25Okapi

KB_DIR = Path(__file__).resolve().parents[1] / "kb"
WORD = re.compile(r"[a-z0-9]+")
FRONT_MATTER = re.compile(r"\A---\n(.*?)\n---\n", re.S)
HEADING = re.compile(r"^## +(.+?)\s*$", re.M)


@dataclass(frozen=True)
class Passage:
    passage_id: str
    title: str
    text: str


def tokens(text):
    """The words of a text, lowercased: letters and digits only, so node-20 is 'node' and '20'."""
    return WORD.findall(text.lower())


def slug(heading):
    return "-".join(tokens(heading))


def load_passages(path):
    """The passages of one knowledge file, or none when it has no header."""
    raw = Path(path).read_text(encoding="utf-8")
    match = FRONT_MATTER.match(raw)
    header = yaml.safe_load(match.group(1)) if match else None
    if not isinstance(header, dict) or not header.get("id"):
        return []
    doc_id, title = header["id"], header.get("title", header["id"])
    # split gives the text before the first heading, then heading and text in turn
    parts = HEADING.split(raw[match.end():])
    passages = []
    if parts[0].strip():
        passages.append(Passage(f"{doc_id}#{slug(title)}", title, parts[0].strip()))
    for heading, text in zip(parts[1::2], parts[2::2]):
        passages.append(Passage(f"{doc_id}#{slug(heading)}", heading.strip(), text.strip()))
    return passages


def from_config(config):
    """A Knowledge when the configuration turns it on (`knowledge: true` in config/models.yaml), otherwise None."""
    return Knowledge() if config.get("knowledge") else None


class Knowledge:
    """Every passage of the knowledge folder, indexed once when the object is made."""

    def __init__(self, kb_dir=KB_DIR):
        self.passages = [passage for path in sorted(Path(kb_dir).glob("*.md")) for passage in load_passages(path)]
        self._index = BM25Okapi([tokens(f"{p.title} {p.text}") for p in self.passages]) if self.passages else None

    def get(self, passage_id):
        """The passage with this id, or None."""
        return next((p for p in self.passages if p.passage_id == passage_id), None)

    def search(self, query, k=3):
        """The best k passages for the query, best first. A passage that shares no word with the query is never returned."""
        if self._index is None:
            return []
        scores = self._index.get_scores(tokens(query))
        ranked = sorted(range(len(self.passages)), key=lambda i: -scores[i])
        return [self.passages[i] for i in ranked[:k] if scores[i] > 0]
