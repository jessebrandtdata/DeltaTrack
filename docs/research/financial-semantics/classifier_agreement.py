"""Precision and recall of `classify_text`, per class, against hand labels.

`classifier_labels.toml` (drawn by classifier_sample.py) holds paragraphs a person has read
and labelled. For each labelled row this re-reads the paragraph from the committed bill XML,
checks its text hash so a label never scores a paragraph that has since changed, runs
`classify_text` on it, and counts the pair (label, predicted).

Per class, precision is the share of paragraphs predicted as that class whose label is that
class; recall is the share of paragraphs labelled that class the classifier predicted as it.
Both are over the labelled rows only, so they describe the sample, not the bills: the sample
is stratified by prediction (classifier_sample.py), which over-represents rare predictions.
Rows with an empty label are skipped and counted.

    uv run python docs/research/financial-semantics/classifier_agreement.py
    uv run python docs/research/financial-semantics/classifier_agreement.py --details

Reads only committed fixtures, so it needs no download.
"""

from __future__ import annotations

import argparse
import sys
import tomllib
from collections import Counter
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parents[2])]

import classify_bill as cb  # noqa: E402
from classifier_sample import LABELS, LABELS_PATH, text_sha256  # noqa: E402

from deltatrack.bill_tree import normalize_bill  # noqa: E402
from tests.corpus_paths import fixture_path  # noqa: E402


@dataclass(frozen=True)
class Scored:
    jurisdiction: str
    bill: str
    node_ordinal: int
    path: str
    label: str
    predicted: str
    text: str


class StaleLabel(Exception):
    """A labelled paragraph's text no longer matches the hash recorded with its label."""


@lru_cache(maxsize=None)
def _nodes(bill: str, version: str):
    return normalize_bill(fixture_path(bill, version)).nodes


def load(path: Path = LABELS_PATH) -> tuple[list[Scored], int]:
    """Every labelled row scored against the live classifier, and the count of unlabelled rows."""
    rows = tomllib.loads(path.read_text()).get("nodes", [])
    scored, unlabelled, stale, bad = [], 0, [], []
    for r in rows:
        if not r["label"]:
            unlabelled += 1
            continue
        if r["label"] not in LABELS:
            bad.append((r["bill"], r["node_ordinal"], r["label"]))
            continue
        text = _nodes(r["bill"], r["version"])[r["node_ordinal"]].body_text
        if text_sha256(text) != r["text_sha256"]:
            stale.append((r["bill"], r["node_ordinal"]))
            continue
        scored.append(
            Scored(
                jurisdiction=r["jurisdiction"],
                bill=r["bill"],
                node_ordinal=r["node_ordinal"],
                path=r["path"],
                label=r["label"],
                predicted=cb.classify_text(text),
                text=text,
            )
        )
    if bad:
        raise ValueError(f"labels outside classify_text's set: {bad}")
    if stale:
        raise StaleLabel(f"paragraph text changed under {len(stale)} label(s): {stale}")
    return scored, unlabelled


def metrics(pairs: list[tuple[str, str]]) -> dict[str, dict[str, float | int | None]]:
    """Per class: support (labelled as it), predicted (called it), tp, precision, recall.

    Precision is None for a class never predicted; recall is None for a class never labelled.
    """
    support, predicted, tp = Counter(), Counter(), Counter()
    for label, pred in pairs:
        support[label] += 1
        predicted[pred] += 1
        if label == pred:
            tp[label] += 1
    out = {}
    for c in LABELS:
        if not support[c] and not predicted[c]:
            continue
        out[c] = {
            "support": support[c],
            "predicted": predicted[c],
            "tp": tp[c],
            "precision": tp[c] / predicted[c] if predicted[c] else None,
            "recall": tp[c] / support[c] if support[c] else None,
        }
    return out


def _pct(x: float | None) -> str:
    return "     —" if x is None else f"{100 * x:5.1f}%"


def summary(scored: list[Scored], unlabelled: int) -> str:
    pairs = [(s.label, s.predicted) for s in scored]
    m = metrics(pairs)
    lines = [f"{'class':16}{'labelled':>9}{'predicted':>10}{'correct':>8}{'precision':>11}{'recall':>8}"]
    lines.append("-" * 62)
    for c, v in m.items():
        lines.append(
            f"{c:16}{v['support']:>9}{v['predicted']:>10}{v['tp']:>8}{_pct(v['precision']):>11}{_pct(v['recall']):>8}"
        )
    agree = sum(1 for label, pred in pairs if label == pred)
    lines.append("-" * 62)
    lines.append(f"labelled rows {len(pairs)}, agree {agree} ({_pct(agree / len(pairs) if pairs else None).strip()})")
    lines.append(f"unlabelled rows skipped: {unlabelled}")
    confusions = Counter((s.label, s.predicted) for s in scored if s.label != s.predicted)
    if confusions:
        lines.append("disagreements (label -> predicted):")
        for (label, pred), n in confusions.most_common():
            lines.append(f"  {label} -> {pred}: {n}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--labels", type=Path, default=LABELS_PATH)
    ap.add_argument("--details", action="store_true", help="print every disagreeing paragraph")
    args = ap.parse_args(argv)

    scored, unlabelled = load(args.labels)
    print(summary(scored, unlabelled))
    if args.details:
        for s in scored:
            if s.label != s.predicted:
                print(f"\n[{s.jurisdiction} #{s.node_ordinal}] {s.path}\n  label {s.label}  predicted {s.predicted}")
                print(f"  {s.text[:300]}{'…' if len(s.text) > 300 else ''}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
