"""Citation verification (retrieval-depth-and-debiasing-program, Phase 2).

Pure-function tests for ``app.rx.citation_check`` — no DB, no model. Gate
evidence: zero false-clean on planted fabrications, robust to OCR/transcript
formatting drift, honest UNVERIFIABLE handling (never silently passes).
"""
from __future__ import annotations

from app.rx import citation_check as cc


# ---------------------------------------------------------------------------
# verify_quote — the core substring check
# ---------------------------------------------------------------------------

def test_exact_match_verifies():
    chunk = "The terminal rate has likely been reached, the chair said."
    r = cc.verify_quote("terminal rate has likely been reached", chunk)
    assert r["verified"] is True
    assert r["reason"] == "match"


def test_fabricated_quote_flagged():
    chunk = "Revenue grew 4% on services strength."
    r = cc.verify_quote("management guided to a 20% decline next quarter", chunk)
    assert r["verified"] is False
    assert r["reason"] == "not_found"  # the trust-critical flag (D1)


def test_case_and_whitespace_insensitive():
    chunk = "Margins   EXPANDED\n  120 basis points year over year."
    r = cc.verify_quote("margins expanded 120 basis points", chunk)
    assert r["verified"] is True


def test_smart_punctuation_folds():
    # Chunk has curly quotes + em-dash (OCR/transcript artifacts); quote is
    # hand-typed with straight quotes + hyphen.
    chunk = "He called it a “soft landing” — a best case outcome."
    r = cc.verify_quote('a "soft landing" - a best case outcome', chunk)
    assert r["verified"] is True


def test_ellipsis_elided_quote_in_order():
    chunk = "We see demand durability in data center even as gaming softens."
    r = cc.verify_quote("demand durability … even as gaming softens", chunk)
    assert r["verified"] is True


def test_ellipsis_fragment_out_of_order_fails():
    chunk = "Gaming softens while data center demand durability holds."
    # second fragment appears BEFORE the first in the chunk → not in order.
    r = cc.verify_quote("demand durability … gaming softens", chunk)
    assert r["verified"] is False
    assert r["reason"] == "not_found"


def test_punctuation_free_transcript_run_on():
    # Whisper-style: no sentence punctuation, just a run-on.
    chunk = ("so the way i think about it is you want margin of safety "
             "you never pay full price for a business thats the whole game")
    r = cc.verify_quote("you want margin of safety", chunk)
    assert r["verified"] is True


def test_missing_quote_is_unverifiable_not_failure():
    assert cc.verify_quote(None, "x")["reason"] == "no_quote"
    assert cc.verify_quote("", "x")["reason"] == "no_quote"


def test_missing_chunk_text_is_unverifiable():
    r = cc.verify_quote("some quote here that is long enough", None)
    assert r["verified"] is False
    assert r["reason"] == "no_chunk_text"


def test_too_short_quote_not_falsely_verified():
    # A 3-char quote would substring-match almost anything → must NOT verify.
    chunk = "the fed is done"
    r = cc.verify_quote("fed", chunk)
    assert r["verified"] is False
    assert r["reason"] == "too_short"


# ---------------------------------------------------------------------------
# annotate_source_refs + status_from_refs
# ---------------------------------------------------------------------------

def test_annotate_marks_each_ref():
    refs = [
        {"path": "a.md", "quote": "margin of safety", "text": "you want margin of safety always"},
        {"path": "b.md", "quote": "fabricated claim not present", "text": "totally different content here"},
    ]
    out = cc.annotate_source_refs(refs)
    assert out[0]["citation_verified"] is True
    assert out[0]["citation_reason"] == "match"
    assert out[1]["citation_verified"] is False
    assert out[1]["citation_reason"] == "not_found"
    # Immutability: originals untouched.
    assert "citation_verified" not in refs[0]


def test_annotate_passthrough_non_list():
    assert cc.annotate_source_refs(None) is None
    assert cc.annotate_source_refs({"not": "a list"}) == {"not": "a list"}


def test_status_all_verified():
    refs = [{"quote": "margin of safety principle", "text": "the margin of safety principle matters"}]
    assert cc.status_from_refs(cc.annotate_source_refs(refs)) == "all_verified"


def test_status_has_mismatch_dominates():
    refs = [
        {"quote": "real quote present here", "text": "this has the real quote present here ok"},
        {"quote": "invented quote absent", "text": "unrelated chunk body text"},
    ]
    assert cc.status_from_refs(cc.annotate_source_refs(refs)) == "has_mismatch"


def test_status_unverifiable_when_no_chunk_text():
    refs = [{"quote": "a quote with no source text to check"}]
    assert cc.status_from_refs(cc.annotate_source_refs(refs)) == "unverifiable"


def test_status_no_quotes_on_empty():
    assert cc.status_from_refs([]) == "no_quotes"
    assert cc.status_from_refs(None) == "no_quotes"
    assert cc.status_from_refs([{"path": "a.md"}]) == "no_quotes"


def test_status_derives_from_raw_unannotated_refs():
    # status_from_refs must work even if annotate wasn't called first.
    refs = [{"quote": "verbatim span here exactly", "text": "contains verbatim span here exactly indeed"}]
    assert cc.status_from_refs(refs) == "all_verified"
