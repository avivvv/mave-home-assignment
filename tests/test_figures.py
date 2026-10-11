"""The figures of evals/figures.py are drawn from a small table of scores and judge grades, and each lands in a file."""
import pandas as pd
import pytest

from agent.schema import CRITERIA
from evals.figures import FIGURES, describe, draw_all


class TestDescribe:
    def test_a_thinking_budget_and_a_round_limit(self):
        assert describe("nemotron-3-super-120b-a12b_think200_4r") == "nemotron-3-super-120b-a12b\nthinking budget 200 tokens, at most 4 rounds"

    def test_thinking_on_with_no_budget_and_an_effort(self):
        assert describe("gpt-oss-20b_thinkon_effort-low_8r") == "gpt-oss-20b\nthinking on, effort low, at most 8 rounds"

    def test_no_thinking(self):
        assert describe("some-model_6r") == "some-model\nno thinking, at most 6 rounds"

    def test_a_tag_that_is_not_a_config_tag_is_shown_as_it_is(self):
        assert describe("big") == "big"


def row(case_id, config, outcome, **values):
    verdict = outcome == "verdict"
    base = {
        "case_id": case_id, "config": config, "outcome": outcome, "rounds": 4, "tool_calls": 3, "tokens_in": 30000, "tokens_out": 2000,
        "llm_seconds": 20.0, "tool_errors": 0, "repeated_calls": 0, "truncated_results": 0, "what_followed_into_present": 0,
        "evidence_anchored": True if verdict else None, "new_log_cited": True if verdict else None, "remediation_ok": False if verdict else None,
        **{criterion: (True if verdict else None) for criterion in CRITERIA},
    }
    return {**base, **values}


@pytest.fixture
def scores():
    return pd.DataFrame([
        row("c01", "big", "verdict", grounded=False),
        row("c02", "big", "round_limit"),
        row("c01", "small", "invalid_verdict", tokens_in=80000),
        row("c02", "small", "verdict", efficiency=False, evidence_anchored=False),
    ])


def test_every_figure_is_written(scores, tmp_path):
    written = draw_all(scores, tmp_path)
    assert sorted(path.name for path in written) == sorted(FIGURES)
    assert all((tmp_path / name).stat().st_size > 0 for name in FIGURES)


def test_a_config_with_no_verdict_at_all_still_draws(scores, tmp_path):
    none = scores[scores.config == "small"].assign(outcome="round_limit")
    for column in [*CRITERIA, "evidence_anchored", "new_log_cited", "remediation_ok"]:
        none[column] = None
    written = draw_all(pd.concat([scores[scores.config == "big"], none]), tmp_path)
    assert len(written) == len(FIGURES)
