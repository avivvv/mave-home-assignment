"""The five figures of the trajectory evaluation, drawn from the scores table that scripts/evaluate_trajectories.py builds.

One row of the table is one trajectory: its deterministic checks (evals/score.py) and the judge's grades, True for
pass, False for fail and None where there was no verdict to grade.
"""
import re

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import Patch  # noqa: E402

from agent.schema import CRITERIA  # noqa: E402
from evals.score import OUTCOMES  # noqa: E402

FIGURES = ("eval_outcomes.png", "eval_verdict_quality.png", "eval_case_heatmap.png", "eval_cost.png", "eval_knowledge.png")

# one colour per agent configuration, in a fixed order; status colours say how a run ended
SERIES = ("#2a78d6", "#eb6834", "#1baf7a", "#eda100")
STATUS = {"verdict": "#0ca30c", "round_limit": "#fab219", "invalid_verdict": "#d03b3b", "no_tool_call": "#ec835a", "model_error": "#ec835a", "unfinished": "#898781"}
PASS, FAIL, NONE = "#0ca30c", "#d03b3b", "#e1e0d9"
SURFACE, INK, MUTED, GRID = "#fcfcfb", "#0b0b0b", "#898781", "#e1e0d9"

# the code checks on a verdict, and the process checks, as "a run passes when ..." columns of the scores table
VERDICT_CHECKS = {"evidence_anchored": "every evidence line was shown", "new_log_cited": "the new log is in the evidence", "remediation_ok": "steps name a source, check before disruption"}
PROCESS_CHECKS = {"tool_errors": "no tool error", "repeated_calls": "no repeated call", "truncated_results": "no cut result", "what_followed_into_present": "what_followed stays in the past"}
HEATMAP_LABELS = ["outcome", *VERDICT_CHECKS.values(), *PROCESS_CHECKS.values(), *[f"judge: {c.replace('_', ' ')}" for c in CRITERIA]]
# the height the heatmap's column labels take, written at 45 degrees above the grid: about 0.55 em per character
LABEL_BAND_INCHES = max(len(label) for label in HEATMAP_LABELS) * 0.55 * 9 * 0.707 / 72 + 0.4

# the tag agent.context.config_tag builds: model, then optional think<budget>|thinkon, optional effort-<level>, then <n>r, then _kb when knowledge is on
CONFIG_TAG = re.compile(r"^(?P<model>.+?)(?:_think(?P<thinking>\d+|on))?(?:_effort-(?P<effort>\w+))?_(?P<rounds>\d+)r(?P<kb>_kb)?$")


def describe(config):
    """A configuration tag as two readable lines: the model, then its thinking, effort, round limit and knowledge."""
    match = CONFIG_TAG.match(config)
    if not match:
        return config
    thinking, effort, rounds = match["thinking"], match["effort"], match["rounds"]
    parts = ["no thinking" if thinking is None else "thinking on" if thinking == "on" else f"thinking budget {thinking} tokens"]
    if effort:
        parts.append(f"effort {effort}")
    parts.append(f"at most {rounds} rounds")
    if match["kb"]:
        parts.append("with knowledge base")
    return f"{match['model']}\n{', '.join(parts)}"


plt.rcParams.update({
    "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "axes.edgecolor": "#c3c2b7", "axes.labelcolor": INK, "text.color": INK,
    "xtick.color": MUTED, "ytick.color": MUTED, "axes.spines.top": False, "axes.spines.right": False, "font.size": 9,
    "font.family": "sans-serif", "legend.frameon": False,
})


def _configs(scores):
    return sorted(scores.config.unique())


def _k_of_n(values):
    values = values.dropna()
    return int(values.sum()), len(values)


def _style(ax):
    ax.grid(axis="x", color=GRID, linewidth=0.6)
    ax.set_axisbelow(True)
    ax.tick_params(length=0)


def outcomes(scores, ax):
    """One stacked bar per agent configuration: how its runs ended."""
    configs = _configs(scores)
    counts = {config: scores[scores.config == config].outcome.value_counts() for config in configs}
    present = [outcome for outcome in OUTCOMES if any(counts[c].get(outcome, 0) for c in configs)]
    for i, config in enumerate(configs):
        left = 0
        for outcome in present:
            n = int(counts[config].get(outcome, 0))
            if n:
                ax.barh(i, n, left=left, color=STATUS[outcome], edgecolor=SURFACE, linewidth=2, height=0.55)
                ax.text(left + n / 2, i, str(n), ha="center", va="center", color="white", fontsize=9, fontweight="bold")
                left += n
    ax.set_yticks(range(len(configs)), [describe(c) for c in configs])
    ax.invert_yaxis()
    ax.set_xlabel("investigations")
    ax.set_xlim(0, scores.groupby("config").size().max())
    ax.legend(handles=[Patch(color=STATUS[o], label=o.replace("_", " ")) for o in present], loc="lower right", bbox_to_anchor=(1, 1.02), ncol=len(present))
    _style(ax)


def pass_shares(scores, columns, ax, title):
    """Grouped bars: the share of verdict-bearing runs that pass each column, per configuration, labelled 'k of n'."""
    configs = _configs(scores)
    height = 0.8 / len(configs)
    names = list(columns)
    for i, config in enumerate(configs):
        group = scores[scores.config == config]
        for j, column in enumerate(names):
            k, n = _k_of_n(group[column])
            y = j + (i - (len(configs) - 1) / 2) * height
            ax.barh(y, k / n if n else 0, height=height * 0.92, color=SERIES[i], label=describe(config) if j == 0 else None)
            ax.text((k / n if n else 0) + 0.02, y, f"{k} of {n}", va="center", fontsize=8, color=INK)
    ax.set_yticks(range(len(names)), [columns[c] if isinstance(columns, dict) else c.replace("_", " ") for c in names])
    ax.invert_yaxis()
    ax.set_xlim(0, 1.25)
    ax.set_xticks([0, 0.5, 1], ["0", "50%", "100%"])
    ax.set_title(title, loc="left", fontsize=10)
    _style(ax)


def case_heatmap(scores, axes):
    """One block per configuration: rows are cases, columns are the outcome, the code checks and the judge's criteria."""
    configs = _configs(scores)
    cases = sorted(scores.case_id.unique())
    code = {**VERDICT_CHECKS, **PROCESS_CHECKS}
    columns = ["outcome", *code, *CRITERIA]
    labels = HEATMAP_LABELS
    for ax, config in zip(axes, configs):
        group = scores[scores.config == config].set_index("case_id")
        for y, case in enumerate(cases):
            if case not in group.index:
                continue
            row = group.loc[case]
            for x, column in enumerate(columns):
                if column == "outcome":
                    color, mark = STATUS[row.outcome], row.outcome.replace("_", "\n")
                elif column in PROCESS_CHECKS:
                    ok = row[column] == 0
                    color, mark = (PASS if ok else FAIL), ("✓" if ok else str(int(row[column])))
                elif row[column] is None or row[column] != row[column]:
                    color, mark = NONE, "–"
                else:
                    color, mark = (PASS if row[column] else FAIL), ("✓" if row[column] else "✗")
                ax.add_patch(plt.Rectangle((x + 0.04, y + 0.04), 0.92, 0.92, color=color))
                ax.text(x + 0.5, y + 0.5, mark, ha="center", va="center", fontsize=7 if column == "outcome" else 9, color="white" if color != NONE else MUTED)
        for boundary in (1, 1 + len(code)):
            ax.axvline(boundary, color=INK, linewidth=0.8)
        ax.set_xlim(0, len(columns))
        ax.set_ylim(len(cases), 0)
        ax.set_xticks([i + 0.5 for i in range(len(columns))], labels, rotation=45, ha="left", rotation_mode="anchor")
        ax.xaxis.tick_top()
        ax.set_yticks([i + 0.5 for i in range(len(cases))], cases)
        ax.set_title(describe(config), loc="left", fontsize=10, pad=(LABEL_BAND_INCHES - 0.3) * 72)
        ax.tick_params(length=0)
        for spine in ax.spines.values():
            spine.set_visible(False)


def cost(scores, axes):
    """Left: tokens of every run, a verdict or not. Right: tokens spent per verdict obtained."""
    configs = _configs(scores)
    tokens = (scores.tokens_in + scores.tokens_out) / 1000
    left, right = axes
    for i, config in enumerate(configs):
        mask = scores.config == config
        got = mask & (scores.outcome == "verdict")
        left.scatter(tokens[got], [i] * int(got.sum()), s=48, color=SERIES[i], edgecolor=SURFACE, linewidth=1.5, zorder=3, label="ended with a verdict" if i == 0 else None)
        left.scatter(tokens[mask & ~got], [i] * int((mask & ~got).sum()), s=48, facecolor=SURFACE, edgecolor=SERIES[i], linewidth=1.5, zorder=3, label="no verdict" if i == 0 else None)
        per_verdict = tokens[mask].sum() / got.sum() if got.sum() else 0
        right.barh(i, per_verdict, color=SERIES[i], height=0.55)
        right.text(per_verdict + 2, i, f"{per_verdict:.0f}k over {int(got.sum())} verdict{'s' if got.sum() != 1 else ''}" if got.sum() else "no verdict", va="center", fontsize=8)
    for ax, title, unit in ((left, "Tokens per investigation", "thousand tokens, in and out"), (right, "Tokens per verdict obtained", "thousand tokens")):
        ax.set_yticks(range(len(configs)), [describe(c) for c in configs] if ax is left else [""] * len(configs))
        ax.invert_yaxis()
        ax.set_xlabel(unit)
        ax.set_title(title, loc="left", fontsize=10)
        ax.set_xlim(0)
        _style(ax)
    right.set_xlim(0, right.get_xlim()[1] * 1.6)
    left.legend(loc="lower right", bbox_to_anchor=(1, 1.02), ncol=2)


def knowledge_configs(scores):
    """The configurations whose runs had the knowledge tool, in the order of the other figures."""
    return [config for config in _configs(scores) if scores[scores.config == config].knowledge.any()]


def knowledge(scores, axes):
    """Left: the share of runs that searched the knowledge base at all. Right: the share of remediation steps that carry a citation.

    Only the configurations that had the tool are shown; each keeps the colour it has in the other figures.
    """
    configs = knowledge_configs(scores)
    left, right = axes
    if not configs:
        for ax in axes:
            ax.text(0.5, 0.5, "no configuration had the knowledge tool", ha="center", va="center", color=MUTED, transform=ax.transAxes)
            ax.set_axis_off()
        return
    for i, config in enumerate(configs):
        colour = SERIES[_configs(scores).index(config)]
        group = scores[scores.config == config]
        used, searches = int((group.knowledge_calls > 0).sum()), int(group.knowledge_calls.sum())
        left.barh(i, used / len(group), color=colour, height=0.55)
        left.text(used / len(group) + 0.02, i, f"{used} of {len(group)} runs, {searches} search{'es' if searches != 1 else ''}", va="center", fontsize=8)
        steps, cited = int(group.n_remediation.dropna().sum()), int(group.n_citations.dropna().sum())
        right.barh(i, cited / steps if steps else 0, color=colour, height=0.55)
        right.text((cited / steps if steps else 0) + 0.02, i, f"{cited} of {steps} steps", va="center", fontsize=8)
    for ax, title in ((left, "Runs that searched the knowledge base"), (right, "Remediation steps with a citation, over the runs with a verdict")):
        ax.set_yticks(range(len(configs)), [describe(c) for c in configs] if ax is left else [""] * len(configs))
        ax.invert_yaxis()
        ax.set_xlim(0, 1.6)
        ax.set_xticks([0, 0.5, 1], ["0", "50%", "100%"])
        ax.set_title(title, loc="left", fontsize=10)
        _style(ax)


def draw_all(scores, figures_dir):
    """Draw the four figures into figures_dir and return their paths."""
    figures_dir.mkdir(parents=True, exist_ok=True)
    n_configs = len(_configs(scores))
    n_cases = scores.case_id.nunique()
    paths = []

    fig, ax = plt.subplots(figsize=(9, 1.2 + 1.0 * n_configs))
    outcomes(scores, ax)
    fig.suptitle("How the investigations ended, per agent configuration", x=0.01, ha="left", fontsize=11)
    paths.append(_save(fig, figures_dir / FIGURES[0]))

    fig, axes = plt.subplots(1, 2, figsize=(13, 3.2 + 0.5 * n_configs), gridspec_kw={"width_ratios": [6, 4]})
    pass_shares(scores, CRITERIA, axes[0], "The judge's criteria")
    pass_shares(scores, VERDICT_CHECKS, axes[1], "Code checks on the verdict")
    axes[0].legend(loc="lower left", bbox_to_anchor=(0, 1.09), ncol=n_configs)
    fig.suptitle("Verdict quality, over the runs that ended with a verdict", x=0.01, ha="left", fontsize=11)
    fig.tight_layout(rect=(0, 0, 1, 0.95))
    paths.append(_save(fig, figures_dir / FIGURES[1]))

    grid_inches = 0.38 * n_cases
    height = 0.3 + grid_inches + LABEL_BAND_INCHES + 0.7
    fig, axes = plt.subplots(1, n_configs, figsize=(2 + 6.5 * n_configs, height), squeeze=False, sharey=True)
    case_heatmap(scores, axes[0])
    fig.suptitle("Every case: outcome, code checks and the judge's grades", x=0.01, y=(height - 0.15) / height, ha="left", va="top", fontsize=11)
    fig.subplots_adjust(left=0.04, right=0.99, bottom=0.3 / height, top=(grid_inches + 0.3) / height, wspace=0.08)
    paths.append(_save(fig, figures_dir / FIGURES[2]))

    fig, axes = plt.subplots(1, 2, figsize=(13, 1.8 + 1.0 * n_configs), gridspec_kw={"width_ratios": [6, 4]})
    cost(scores, axes)
    fig.suptitle("What the investigations cost", x=0.01, ha="left", fontsize=11)
    fig.tight_layout(rect=(0, 0, 1, 0.95))
    paths.append(_save(fig, figures_dir / FIGURES[3]))

    fig, axes = plt.subplots(1, 2, figsize=(13, 1.8 + 1.0 * max(1, len(knowledge_configs(scores)))), gridspec_kw={"width_ratios": [5, 5]})
    knowledge(scores, axes)
    fig.suptitle("Use of the knowledge base, and citations of it, by the configurations that had the tool", x=0.01, ha="left", fontsize=11)
    fig.tight_layout(rect=(0, 0, 1, 0.95))
    paths.append(_save(fig, figures_dir / FIGURES[4]))
    return paths


def _save(fig, path):
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return path
