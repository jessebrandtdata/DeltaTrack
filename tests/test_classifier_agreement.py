"""Per-class precision and recall of classify_text against the hand labels.

`docs/research/financial-semantics/classifier_agreement.py` scores `classify_text` on the
paragraphs in `classifier_labels.toml` a person has labelled. The unit tests pin the metric
arithmetic and the sampler's bookkeeping on constructed rows; the slow gate checks that every
row in the committed label file still names a paragraph whose text matches its recorded hash,
so a corpus change cannot silently re-point a label.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "docs" / "research" / "financial-semantics"))

import classifier_agreement as agree  # noqa: E402
import classifier_sample as sampler  # noqa: E402


def test_metrics_count_precision_over_predictions_and_recall_over_labels():
    pairs = [
        ("appropriation", "appropriation"),
        ("appropriation", "appropriation"),
        ("appropriation", "unknown"),
        ("restriction", "appropriation"),
        ("restriction", "restriction"),
    ]
    m = agree.metrics(pairs)
    assert m["appropriation"] == {"support": 3, "predicted": 3, "tp": 2, "precision": 2 / 3, "recall": 2 / 3}
    assert m["restriction"] == {"support": 2, "predicted": 1, "tp": 1, "precision": 1.0, "recall": 0.5}
    # unknown was predicted once and never labelled: precision 0, recall undefined
    assert m["unknown"] == {"support": 0, "predicted": 1, "tp": 0, "precision": 0.0, "recall": None}
    assert "fee" not in m


def test_metrics_on_no_rows_is_empty():
    assert agree.metrics([]) == {}


def test_binary_metrics_fold_every_other_label_into_not_appropriation():
    pairs = [
        ("appropriation", "appropriation"),
        ("appropriation", "cap"),  # a missed appropriation
        ("not_appropriation", "appropriation"),  # the coarse label, wrongly called an appropriation
        ("restriction", "restriction"),  # a specific label counts as not_appropriation here
        ("not_appropriation", "unknown"),
    ]
    m = agree.binary_metrics(pairs)
    assert m["appropriation"] == {"support": 2, "predicted": 2, "tp": 1, "precision": 0.5, "recall": 0.5}
    assert m["not_appropriation"] == {"support": 3, "predicted": 3, "tp": 2, "precision": 2 / 3, "recall": 2 / 3}


def test_summary_scores_coarse_rows_in_the_binary_table_only():
    scored = [
        agree.Scored("j", "b", 1, "p", "appropriation", "appropriation", "t"),
        agree.Scored("j", "b", 2, "p", "not_appropriation", "restriction", "t"),
        agree.Scored("j", "b", 3, "p", "restriction", "restriction", "t"),
    ]
    text = agree.summary(scored, unlabelled=4)
    assert "appropriation or not, 3 labelled rows" in text
    assert "per class, 2 rows whose label names a class" in text
    assert "agree 2 of 2" in text
    assert "unlabelled rows skipped: 4" in text


def _row(ordinal: int, predicted: str, has_dollar: bool = True) -> sampler.Row:
    return sampler.Row(
        jurisdiction="j",
        bill="b",
        version="v",
        node_ordinal=ordinal,
        element_id=f"e{ordinal}",
        path="p",
        text_sha256=f"h{ordinal}",
        predicted=predicted,
        has_dollar=has_dollar,
        text=f"text {ordinal}",
    )


def test_sample_takes_up_to_per_class_from_each_stratum_and_splits_unknown_by_dollar():
    rows = [_row(i, "appropriation") for i in range(10)]
    rows += [_row(10 + i, "unknown", has_dollar=True) for i in range(5)]
    rows += [_row(20 + i, "unknown", has_dollar=False) for i in range(5)]
    rows += [_row(30, "fee")]
    drawn = sampler.sample(rows, per_class=3, seed=0)
    by_stratum = {}
    for r in drawn:
        by_stratum.setdefault(sampler.stratum(r), []).append(r)
    assert {k: len(v) for k, v in by_stratum.items()} == {
        "appropriation": 3,
        "unknown/$": 3,
        "unknown/no $": 3,
        "fee": 1,
    }


def test_sample_is_deterministic_for_a_seed_and_skips_excluded_identities():
    rows = [_row(i, "appropriation") for i in range(10)]
    first = sampler.sample(rows, per_class=4, seed=7)
    assert first == sampler.sample(rows, per_class=4, seed=7)
    again = sampler.sample(rows, per_class=4, seed=7, exclude={r.identity for r in first})
    assert not {r.identity for r in again} & {r.identity for r in first}


def test_rerun_tops_each_stratum_up_and_adds_nothing_at_the_same_size():
    rows = [_row(i, "appropriation") for i in range(10)]
    rows += [_row(10 + i, "unknown", has_dollar=False) for i in range(10)]
    first = sampler.sample(rows, per_class=4, seed=1)
    kept = [sampler._as_dict(r) for r in first]
    have = sampler.existing_strata(kept)
    assert have == {"appropriation": 4, "unknown/no $": 4}
    exclude = {r.identity for r in first}
    assert sampler.sample(rows, per_class=4, seed=1, exclude=exclude, have=have) == []
    more = sampler.sample(rows, per_class=6, seed=1, exclude=exclude, have=have)
    assert sorted(sampler.stratum(r) for r in more) == ["appropriation"] * 2 + ["unknown/no $"] * 2


def test_render_round_trips_through_tomllib(tmp_path):
    import tomllib

    rows = [sampler._as_dict(_row(1, "appropriation"))]
    rows[0]["text"] = "For salaries and expenses, $1,000: Provided, That it's ''' odd \\ text"
    rows[0]["label"] = "appropriation"
    rows[0]["note"] = 'quoted "note"'
    text = sampler.render(rows, {"seed": 0, "bills": ["j"]})
    parsed = tomllib.loads(text)
    assert parsed["meta"] == {"seed": 0, "bills": ["j"]}
    assert parsed["nodes"] == rows


@pytest.mark.slow
def test_committed_labels_still_name_their_paragraphs():
    """Every row's text hash matches the committed bill XML; labelled rows score without error."""
    import tomllib

    rows = tomllib.loads(sampler.LABELS_PATH.read_text())["nodes"]
    assert rows, "the label file is empty"
    for r in rows:
        text = agree._nodes(r["bill"], r["version"])[r["node_ordinal"]].body_text
        assert sampler.text_sha256(text) == r["text_sha256"], (r["bill"], r["node_ordinal"])
    scored, unlabelled = agree.load()
    assert len(scored) + unlabelled == len(rows)
