"""Draw the paragraphs a person labels to measure `classify_text` per class.

`classify_text` (classify_bill.py) gives every bill paragraph one of twelve labels, and nothing
in the repo says which label a paragraph truly has: the committee-report answer keys confirm
dollar figures for appropriations only. This writes `classifier_labels.toml`, a stratified
sample of paragraphs from the Senate-reported bills in `tests/validation_sources.py`, each
with the classifier's prediction filled in and its `label` left empty for a person to fill.
`classifier_agreement.py` then scores the classifier against the filled labels.

The sample is stratified by predicted label so the rare labels are represented: up to
`--per-class` paragraphs for each label the classifier produced, drawn with `--seed`. The
"unknown" stratum is split by whether the paragraph contains a dollar figure, since an
unlabelled paragraph with a figure is the one a reader cares about. Rerunning with a larger
`--per-class`, a new seed or after the bill list changes keeps every row already in the file,
labelled or not, and appends the new draws.

Each row carries the identity fields ADR 0019 asks for (bill, version, node ordinal, text
hash), so the scorer can tell when the fixture under a label has changed.

    uv run python docs/research/financial-semantics/classifier_sample.py
    uv run python docs/research/financial-semantics/classifier_sample.py --per-class 40 --seed 1

Reads only committed fixtures, so it needs no download.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import subprocess
import sys
import tomllib
from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parents[2])]

import classify_bill as cb  # noqa: E402

from deltatrack.bill_tree import normalize_bill  # noqa: E402
from tests.corpus_paths import fixture_path  # noqa: E402
from tests.validation_sources import JURISDICTIONS  # noqa: E402

LABELS_PATH = HERE / "classifier_labels.toml"

# Every label classify_text can return, in the order it tries them.
LABELS = (
    "restriction",
    "transfer",
    "appropriation",
    "rescission",
    "directive",
    "cap",
    "authorization",
    "fee",
    "earmark",
    "availability",
    "sub_allocation",
    "unknown",
)

HEADER = """\
# Paragraphs to label by hand, so classify_text (classify_bill.py) can be scored per class.
# Written by classifier_sample.py; scored by classifier_agreement.py. Edit only `label` and
# `note`; every other field identifies the paragraph (ADR 0019) and is checked at scoring.
#
# label: the class the paragraph truly is, one of
#   restriction transfer appropriation rescission directive cap authorization fee earmark
#   availability sub_allocation unknown
# "unknown" means none of the eleven fits. An empty label means not yet reviewed; the scorer
# skips it. `predicted` is what the classifier said and is pre-filled for comparison only:
# a row whose label equals its prediction still needs a person to have read it.
# note: anything the next reader needs (why the label, what made it hard). Free text.
"""


@dataclass(frozen=True)
class Row:
    jurisdiction: str
    bill: str
    version: str
    node_ordinal: int
    element_id: str
    path: str
    text_sha256: str
    predicted: str
    has_dollar: bool
    text: str

    @property
    def identity(self) -> tuple[str, str, int, str]:
        return (self.bill, self.version, self.node_ordinal, self.text_sha256)


def text_sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def population() -> list[Row]:
    """Every paragraph with body text in the Senate-reported bills, with its prediction."""
    rows = []
    for j in JURISDICTIONS:
        tree = normalize_bill(fixture_path(j.bill_id, j.version))
        for ordinal, node in enumerate(tree.nodes):
            if not node.body_text:
                continue
            rows.append(
                Row(
                    jurisdiction=j.slug,
                    bill=j.bill_id,
                    version=j.version,
                    node_ordinal=ordinal,
                    element_id=node.element_id,
                    path=" > ".join(node.display_path),
                    text_sha256=text_sha256(node.body_text),
                    predicted=cb.classify_text(node.body_text),
                    has_dollar=bool(cb.DOLLAR.search(node.body_text)),
                    text=node.body_text,
                )
            )
    return rows


def stratum(row: Row) -> str:
    if row.predicted == "unknown":
        return "unknown/$" if row.has_dollar else "unknown/no $"
    return row.predicted


def sample(rows: list[Row], per_class: int, seed: int, exclude: set[tuple] = frozenset()) -> list[Row]:
    """Up to `per_class` rows from each stratum, drawn with `seed`, skipping identities in `exclude`."""
    by_stratum: dict[str, list[Row]] = defaultdict(list)
    for r in rows:
        if r.identity not in exclude:
            by_stratum[stratum(r)].append(r)
    rng = random.Random(seed)
    drawn = []
    for name in sorted(by_stratum):
        pool = by_stratum[name]
        drawn.extend(rng.sample(pool, min(per_class, len(pool))))
    return drawn


def existing_rows(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return tomllib.loads(path.read_text()).get("nodes", [])


def _toml_string(value: str) -> str:
    """A TOML string: a literal multi-line one when the text allows it, else a basic string."""
    if "'''" not in value and all(ch == "\n" or ch >= " " for ch in value):
        return f"'''\n{value}'''"
    return json.dumps(value)


def _parser_revision() -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True, cwd=HERE
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return ""


def render(rows: list[dict], meta: dict) -> str:
    out = [HEADER, "[meta]"]
    for k, v in meta.items():
        out.append(f"{k} = {json.dumps(v)}")
    for r in rows:
        out.append("")
        out.append("[[nodes]]")
        for k in ("jurisdiction", "bill", "version"):
            out.append(f"{k} = {json.dumps(r[k])}")
        out.append(f"node_ordinal = {r['node_ordinal']}")
        for k in ("element_id", "path", "text_sha256", "predicted", "label", "note"):
            out.append(f"{k} = {json.dumps(r.get(k, ''))}")
        out.append(f"text = {_toml_string(r['text'])}")
    return "\n".join(out) + "\n"


def _as_dict(row: Row) -> dict:
    return {
        "jurisdiction": row.jurisdiction,
        "bill": row.bill,
        "version": row.version,
        "node_ordinal": row.node_ordinal,
        "element_id": row.element_id,
        "path": row.path,
        "text_sha256": row.text_sha256,
        "predicted": row.predicted,
        "label": "",
        "note": "",
        "text": row.text,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--per-class", type=int, default=20, help="paragraphs per predicted label (default 20)")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--out", type=Path, default=LABELS_PATH)
    args = ap.parse_args(argv)

    kept = existing_rows(args.out)
    exclude = {(r["bill"], r["version"], r["node_ordinal"], r["text_sha256"]) for r in kept}
    rows = population()
    drawn = sample(rows, args.per_class, args.seed, exclude)
    strata: dict[str, int] = defaultdict(int)
    for r in drawn:
        strata[stratum(r)] += 1

    meta = {
        "generated": date.today().isoformat(),
        "per_class": args.per_class,
        "seed": args.seed,
        "parser_revision": _parser_revision(),
        "population": len(rows),
        "bills": sorted({r.jurisdiction for r in rows}),
    }
    all_rows = kept + [_as_dict(r) for r in drawn]
    args.out.write_text(render(all_rows, meta))

    print(f"population {len(rows)} paragraphs in {len(meta['bills'])} bills")
    for name in sorted(strata):
        print(f"  {name:14} {strata[name]:>4}")
    print(f"kept {len(kept)} existing rows, added {len(drawn)}, wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
