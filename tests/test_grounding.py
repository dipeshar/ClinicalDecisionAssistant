"""Independent quote-rule examples use synthetic text and no model calls."""

from council.grounding import ground_claim, quote_failure, verify_citation
from council.models import Citation, CitationDraft, ClaimDraft

TEXT = "The synthetic patient has stable kidney function and requires further review before surgery."


def check(quote: str, text: str = TEXT) -> Citation:
    return verify_citation(CitationDraft(passage_id="CASE-tests", quote=quote),
                           {"CASE-tests": text}, {"CASE-tests"})


def test_exact_match() -> None:
    result = check("The synthetic patient has stable kidney function")
    assert result.verified is True
    assert result.verify_note == ""
    assert result.source_type == "case"


def test_case_difference() -> None:
    assert check("THE SYNTHETIC PATIENT HAS STABLE KIDNEY FUNCTION").verified


def test_extra_whitespace() -> None:
    assert check("  the\t synthetic\npatient   has stable kidney function ",
                 "The   synthetic\npatient\thas\u00a0stable kidney function.").verified


def test_curly_vs_straight_quotes() -> None:
    assert check('The patient\'s chart says "stable kidney function"',
                 "The patient’s chart says “stable kidney function”").verified


def test_em_dash_vs_hyphen() -> None:
    assert check("The synthetic finding - stable kidney function",
                 "The synthetic finding — stable kidney function").verified


def test_ellipsis_parts_in_order() -> None:
    assert check("synthetic patient ... further review before surgery").verified


def test_ellipsis_parts_out_of_order_fail() -> None:
    result = check("further review before surgery ... synthetic patient")
    assert result.verified is False
    assert result.verify_note == "quote text not found in source in order"


def test_under_four_words_fails() -> None:
    result = check("stable kidney function")
    assert result.verified is False
    assert result.verify_note == "quote has fewer than 4 words"


def test_over_forty_words_fails() -> None:
    text = " ".join(["synthetic"] * 41)
    result = check(text, text)
    assert result.verified is False
    assert result.verify_note == "quote has more than 40 words"


def test_passage_not_shown_this_turn_fails() -> None:
    result = verify_citation(CitationDraft(passage_id="SURG-KB-01", quote=TEXT),
                             {"SURG-KB-01": TEXT}, {"SURG-KB-02"})
    assert result.verified is False
    assert result.verify_note == "passage was not shown in this turn"


def test_unknown_passage_id_fails() -> None:
    # Merely listing an unknown ID as shown does not create a source.
    result = verify_citation(CitationDraft(passage_id="SURG-KB-99", quote=TEXT),
                             {"CASE-tests": TEXT}, {"SURG-KB-99"})
    assert result.verified is False
    assert result.verify_note == "unknown passage ID"


def test_one_changed_word_fails() -> None:
    result = check("The synthetic patient has worsening kidney function")
    assert result.verified is False
    assert result.verify_note == "quote text not found in source in order"


def test_four_word_boundary_passes() -> None:
    assert check("The synthetic patient has").verified


def test_forty_word_boundary_passes() -> None:
    text = " ".join(["synthetic"] * 40)
    assert check(text, text).verified


def test_ellipsis_word_count_is_total_and_excludes_skip_marker() -> None:
    assert check("synthetic patient...further review").verified
    assert check("synthetic patient ... review").verified is False
    first, last = " ".join(["first"] * 20), " ".join(["last"] * 21)
    assert check(first + " ... " + last, first + " middle " + last).verified is False


def test_ellipsis_cannot_reuse_overlapping_words() -> None:
    assert check("synthetic patient ... patient has", "synthetic patient has").verified is False
    assert check("synthetic patient ... synthetic patient", "synthetic patient").verified is False


def test_later_occurrence_can_complete_ordered_match() -> None:
    assert check("stable kidney ... synthetic patient",
                 "synthetic patient stable kidney synthetic patient").verified


def test_empty_or_punctuation_only_quote_fails() -> None:
    for quote in ("", "...", "... ... ... ...", "! ? : ;"):
        assert check(quote, quote).verified is False


def test_substring_at_word_boundaries_is_not_a_quote() -> None:
    assert check("The patient has risk", "The patient has risks").verified is False
    assert check("patient has stable kidneys", "outpatient has stable kidneys").verified is False


def test_literal_punctuation_not_regex_or_fuzzy_matching() -> None:
    assert check("The result is 2.4 today", "The result is 2x4 today").verified is False
    assert check("The result is 2.4 today", "The result is 2.5 today").verified is False


def test_citation_preserves_data_and_sets_code_owned_fields() -> None:
    quote = "  The SYNTHETIC patient has stable kidney function "
    draft = CitationDraft(passage_id="SURG-KB-01", quote=quote)
    before = draft.model_dump()
    result = verify_citation(draft, {"SURG-KB-01": TEXT}, {"SURG-KB-01"})
    assert result.model_dump() == dict(before, source_type="kb", verified=True, verify_note="")
    assert draft.model_dump() == before
    assert Citation.model_validate_json(result.model_dump_json()) == result


def test_case_source_must_also_be_shown() -> None:
    result = verify_citation(CitationDraft(passage_id="CASE-tests", quote=TEXT), {"CASE-tests": TEXT}, set())
    assert result.verified is False


def test_round2_carryover_only_verifies_when_shown_again() -> None:
    draft = CitationDraft(passage_id="SURG-KB-06", quote=TEXT)
    assert not verify_citation(draft, {"SURG-KB-06": TEXT}, {"SURG-KB-01"}).verified
    assert verify_citation(draft, {"SURG-KB-06": TEXT}, {"SURG-KB-01", "SURG-KB-06"}).verified


def test_no_cross_source_stitching() -> None:
    draft = CitationDraft(passage_id="CASE-tests", quote="synthetic patient ... further review")
    assert not verify_citation(draft, {"CASE-tests": "synthetic patient", "SURG-KB-01": "further review"},
                                {"CASE-tests", "SURG-KB-01"}).verified


def test_quote_is_checked_against_its_named_source() -> None:
    sources = {"CASE-tests": "The other source says different things", "SURG-KB-01": TEXT}
    draft = CitationDraft(passage_id="SURG-KB-01", quote=TEXT)
    assert verify_citation(draft, sources, set(sources)).verified
    draft.quote = sources["CASE-tests"]
    assert not verify_citation(draft, sources, set(sources)).verified


def test_leading_and_trailing_ellipsis() -> None:
    assert check("... synthetic patient has stable ...").verified


def test_claim_requires_citations() -> None:
    result = ground_claim(ClaimDraft(text="Synthetic claim", citations=[]), "R1-SURG-C1", {}, set())
    assert result.grounding_status == "ungrounded"


def test_claim_requires_every_citation_to_pass() -> None:
    good = CitationDraft(passage_id="CASE-tests", quote=TEXT)
    bad = CitationDraft(passage_id="CASE-tests", quote="The synthetic patient has worsening kidney function")
    draft = ClaimDraft(text="Synthetic claim", citations=[good, bad])
    before = draft.model_dump()
    result = ground_claim(draft, "R1-SURG-C1", {"CASE-tests": TEXT}, {"CASE-tests"})
    assert result.claim_id == "R1-SURG-C1" and result.text == "Synthetic claim"
    assert result.grounding_status == "ungrounded"
    assert [c.verified for c in result.citations] == [True, False]
    assert draft.model_dump() == before


def test_rechecking_repaired_claim_can_ground_it() -> None:
    draft = ClaimDraft(text="Synthetic claim", citations=[CitationDraft(passage_id="CASE-tests", quote=TEXT)])
    result = ground_claim(draft, "R2-SURG-C1", {"CASE-tests": TEXT}, {"CASE-tests"})
    assert result.claim_id == "R2-SURG-C1" and result.grounding_status == "grounded"


def test_failure_notes_do_not_echo_untrusted_data() -> None:
    value = "fictional@example.invalid"
    result = verify_citation(CitationDraft(passage_id=value, quote=value), {}, set())
    assert value not in result.verify_note
    assert value not in (quote_failure(value + " changed quote words", TEXT) or "")
