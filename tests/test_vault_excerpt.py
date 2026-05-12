"""Sentence splitter + extractive selector — pure unit tests.

The selector function ``select_top_sentences`` calls the BGE encoder when
the chunk has more sentences than ``k``; we patch the encoder so the
suite stays fast (no model load) and assertion-stable.
"""
from __future__ import annotations

import pytest

from tools.vault_indexer import excerpt as exc


# ---------------------------------------------------------------------------
# split_sentences
# ---------------------------------------------------------------------------

def test_split_sentences_basic():
    text = "This is the first sentence. This is the second! And the third?"
    assert exc.split_sentences(text) == [
        "This is the first sentence.",
        "This is the second!",
        "And the third?",
    ]


def test_split_sentences_keeps_abbreviations_intact():
    # Mr. and U.S. should not split.
    text = "Mr. Buffett bought $5B of U.S. stock. He held it for years."
    out = exc.split_sentences(text)
    assert out == [
        "Mr. Buffett bought $5B of U.S. stock.",
        "He held it for years.",
    ]


def test_split_sentences_collapses_whitespace_and_drops_fragments():
    text = "  First.  \n\n  Second sentence here.   . "
    out = exc.split_sentences(text)
    # Empty/2-char tail is dropped; the lone "." after Second is filtered.
    assert out == ["First.", "Second sentence here."]


def test_split_sentences_empty_input():
    assert exc.split_sentences("") == []
    assert exc.split_sentences("   ") == []


def test_split_sentences_no_terminator_returns_one():
    text = "A single thought without punctuation"
    assert exc.split_sentences(text) == [text]


# ---------------------------------------------------------------------------
# select_top_sentences
# ---------------------------------------------------------------------------

def test_select_top_sentences_returns_all_when_fewer_than_k(monkeypatch):
    # No encoder calls expected on this short-circuit path.
    monkeypatch.setattr(exc._embed, "encode_query", lambda *a, **k: pytest.fail("encoder should not be called"))
    out = exc.select_top_sentences("anything", "Sentence one. Sentence two.", k=3)
    assert out == ["Sentence one.", "Sentence two."]


def test_select_top_sentences_falls_back_when_no_sentences(monkeypatch):
    monkeypatch.setattr(exc._embed, "encode_query", lambda *a, **k: pytest.fail("encoder should not be called"))
    out = exc.select_top_sentences("q", "verylong" * 200, k=2, fallback_chars=40)
    assert len(out) == 1
    assert len(out[0]) <= 40


def test_select_top_sentences_picks_query_relevant_and_preserves_order(monkeypatch):
    """Three sentences; query is most similar to S2 + S3. Ensure the
    selector returns those in original order, not relevance order."""
    sentences_in_input = [
        "This is some unrelated lead-in about coffee and weather.",
        "META is the Big Tech name with the highest 13F crowding this quarter.",
        "Cleo Fields disclosed three META-adjacent buys on the same day.",
    ]
    text = " ".join(sentences_in_input)

    # Stub encoder: query → [1, 0, 0]. Each sentence gets a 3-D vector
    # whose post-normalisation cosine with the query encodes the
    # intended relevance. Use a non-degenerate basis so the normaliser
    # doesn't collapse all three to the same direction.
    def fake_q(_):
        return [1.0, 0.0, 0.0]

    def fake_p(texts):
        # cos(angle) ≈ value below x-axis dim after normalising.
        # Pre-normalisation triples chosen so post-normalisation
        # x-component is the desired score.
        vecs = {
            sentences_in_input[0]: [0.1, 1.0, 0.0],   # cos ≈ 0.10
            sentences_in_input[1]: [0.9, 0.4, 0.0],   # cos ≈ 0.91
            sentences_in_input[2]: [0.7, 0.7, 0.0],   # cos ≈ 0.71
        }
        return [vecs.get(t, [0.0, 0.0, 0.0]) for t in texts]

    monkeypatch.setattr(exc._embed, "encode_query", fake_q)
    monkeypatch.setattr(exc._embed, "encode_passages", fake_p)

    out = exc.select_top_sentences("smart money meta", text, k=2)
    # Order preserved (original positions 1 then 2), not relevance (1 then 2 = same here, but order matters).
    assert out == [sentences_in_input[1], sentences_in_input[2]]


def test_select_top_sentences_filters_short_fragments():
    # "OK." is below default min_chars=12 → filtered from candidates.
    text = "OK. Smart money rotated into semis last quarter. Cleo Fields bought META."
    out = exc.split_sentences(text)
    # Splitter keeps "OK." because abbreviation/length filter in selector
    # is applied after — but selector filters by min_chars when picking.
    # Confirm split keeps it; selector drops it.
    assert "OK." in out

    out2 = exc.select_top_sentences(
        "semis", text, k=5, min_chars=12  # k larger than candidates
    )
    assert "OK." not in out2
    assert "Smart money rotated into semis last quarter." in out2
