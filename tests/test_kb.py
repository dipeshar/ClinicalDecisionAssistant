"""Synthetic KB and retrieval tests; no real KBs, providers or model calls."""

from copy import deepcopy
import math
from pathlib import Path
import traceback
import warnings

import pytest

from council.kb import KBError, PassageLengthWarning, build_query, load_kb, tokenize
from council.models import Argument, CaseContext, CaseSection, Claim, Config, Role, Score

FIXTURES = Path(__file__).parent / "fixtures/kb"
CLINICAL = "BP 150/90, creatinine 2.4 mg/dL, eGFR 38, surgery on 14 March 2026, ICD-10 I25.1, heparin 5000 units"


def write_kb(folder: Path, body: str, id: str = "SURG-KB-01", name: str = "fixture.md") -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / name
    path.write_bytes(("# Synthetic summary\r\n\r\n## " + id + "\r\n" + body).encode())
    return path


def argument(role: Role = Role.SURG, round: int = 1) -> Argument:
    return Argument(
        argument_id=f"R{round}-{role}", role=role, round=round, stance="conditional",
        summary=f"summary-{role}-{round}", claims=[], conditions=[], uncertainties=[],
        rebuttal=None, revisions=None, stance_changed=False, retrieved_passage_ids=[],
        repair_used=False, status="ok", failure_reason=None,
    )


def claim(id: str, text: str) -> Claim:
    return Claim(claim_id=id, text=text, citations=[], grounding_status="ungrounded")


def judge_score(argument_id: str, flagged: str | None = None, feedback: str | None = None) -> Score:
    return Score(judge="JUDGE_A", argument_id=argument_id, model="fake-judge", round=1,
                 groundedness=1, logic=2, uncertainty=3, counterarguments=None,
                 justification={"groundedness": "not-query-justification", "logic": "x", "uncertainty": "x"},
                 untraceable_claims=[{"claim_id": flagged, "reason": "not-query-reason"}] if flagged else [],
                 feedback=[{"claim_id": feedback, "note": "not-query-note"}])


@pytest.fixture
def case() -> CaseContext:
    return CaseContext(case_id="demo", source_file="demo.md", case_hash="x", title="not-query-title",
                       sections=[CaseSection(id=id, heading=id, text=text, flagged=False, flag_reasons=[])
                                 for id, text in [("CASE-tests", CLINICAL), ("CASE-medications", "not-selected")]],
                       missing_sections=[], injection_flags=[])


def test_load_exact_passages_and_role_fields() -> None:
    kb = load_kb({Role.SURG: FIXTURES / "surgeon", Role.PHYS: FIXTURES / "physician"})
    passages = kb.passages[Role.SURG]
    assert [p.id for p in passages] == [f"SURG-KB-{i:02}" for i in range(1, 7)]
    assert all(p.kb == "SURG" and p.source_title == "Retrieval exercise (synthetic summary)" for p in passages)
    raw = (FIXTURES / "surgeon/synthetic.md").read_bytes().decode()
    assert passages[0].text == raw.split("## SURG-KB-01", 1)[1].split("\n", 1)[1].split("## SURG-KB-02")[0]
    assert len(kb.passages[Role.PHYS]) == 1


@pytest.mark.parametrize("duplicate", ["same_file", "other_file", "other_role"])
def test_duplicate_ids_rejected_globally(tmp_path: Path, duplicate: str) -> None:
    path = write_kb(tmp_path / "surg", "word " * 40)
    folders = {Role.SURG: path.parent}
    if duplicate == "same_file":
        with path.open("a") as stream:
            stream.write("\n## SURG-KB-01\n" + "word " * 40)
    elif duplicate == "other_file":
        write_kb(path.parent, "word " * 40, name="second.md")
    else:
        # PHYS sorts before SURG; duplicate checking must span folder boundaries.
        path.write_text(path.read_text().replace("SURG-KB-01", "PHYS-KB-01"))
        other = write_kb(tmp_path / "phys", "word " * 40, id="PHYS-KB-01")
        folders[Role.PHYS] = other.parent
    with pytest.raises(KBError, match="duplicate passage ID"):
        load_kb(folders)


@pytest.mark.parametrize("id,message", [
    ("PHYS-KB-01", "wrong passage prefix"), ("SURG-KB-1", "invalid passage ID"),
    ("SURG-KB-001", "invalid passage ID"), ("JUDGE_A-KB-01", "invalid passage ID"),
    ("SURG-KB-01 trailing", "invalid passage ID"),
])
def test_wrong_prefix_and_malformed_ids(tmp_path: Path, id: str, message: str) -> None:
    write_kb(tmp_path, "word " * 40, id=id)
    with pytest.raises(KBError, match=message):
        load_kb({Role.SURG: tmp_path})


@pytest.mark.parametrize("role", [Role.SURG, Role.PHYS, Role.ANAES, Role.ADMIN, Role.RED])
def test_all_role_prefixes(tmp_path: Path, role: Role) -> None:
    write_kb(tmp_path, "word " * 40, id=f"{role}-KB-01")
    assert load_kb({role: tmp_path}).passages[role][0].kb == role


@pytest.mark.parametrize("count", [0, 39, 40, 150, 151])
def test_length_is_warning_only_with_exact_bounds(tmp_path: Path, count: int) -> None:
    write_kb(tmp_path, "word " * count)
    with warnings.catch_warnings(record=True) as seen:
        warnings.simplefilter("always")
        kb = load_kb({Role.SURG: tmp_path})
    assert len(seen) == (0 if 40 <= count <= 150 else 1)
    assert all(issubclass(w.category, PassageLengthWarning) for w in seen)
    assert kb.passages[Role.SURG][0].text == "word " * count
    result = kb.retrieve(Role.SURG, 1, "absent")
    assert len(result.passages) == 1 and result.scores == [0.0]


@pytest.mark.parametrize("location", ["body", "title", "malformed_id", "filename"])
def test_privacy_rejection_contains_only_safe_location(tmp_path: Path, location: str) -> None:
    value = "fictional.kb@example.invalid"
    path = write_kb(tmp_path, CLINICAL + "\n" + value,
                    name=value + ".md" if location == "filename" else "fixture.md")
    if location == "title":
        path.write_text("# " + value + "\n## SURG-KB-01\n" + "word " * 40)
    if location == "malformed_id":
        path.write_text("# Synthetic summary\n## " + value + "\n" + "word " * 40)
    with warnings.catch_warnings(record=True) as seen, pytest.raises(KBError) as error:
        warnings.simplefilter("always")
        load_kb({Role.SURG: tmp_path})
    assert not seen  # Privacy check precedes length warnings.
    assert value not in str(error.value)
    assert value not in "".join(traceback.format_exception(error.value))
    if location not in ("filename", "malformed_id"):
        assert str(error.value) == f"KB privacy rejection: {path}: SURG-KB-01"
    if location == "filename":
        assert "[redacted filename]: SURG-KB-01" in str(error.value)


def test_shared_scan_is_used_on_every_passage(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from council import kb as module
    from council.privacy import PrivacyHit, scan_identifiers
    calls: list[str] = []

    def spy(text: str) -> list[PrivacyHit]:
        calls.append(text)
        return scan_identifiers(text)

    monkeypatch.setattr(module, "scan_identifiers", spy)
    write_kb(tmp_path, ("word " * 40) + "\n## SURG-KB-02\n" + "fictional@example.invalid")
    with pytest.raises(KBError, match="SURG-KB-02"):
        load_kb({Role.SURG: tmp_path})
    assert any("word " * 40 in text for text in calls)
    assert "fictional@example.invalid" in calls


def test_clinical_demo_text_loads(tmp_path: Path) -> None:
    write_kb(tmp_path, CLINICAL + " " + "synthetic " * 40)
    assert load_kb({Role.SURG: tmp_path}).passages[Role.SURG][0].text.startswith(CLINICAL)


def test_unreadable_empty_or_malformed_kb(tmp_path: Path) -> None:
    with pytest.raises(KBError, match="does not exist"):
        load_kb({Role.SURG: tmp_path / "missing"})
    with pytest.raises(KBError, match="no Markdown"):
        load_kb({Role.SURG: tmp_path})
    with pytest.raises(KBError, match="only specialist"):
        load_kb({Role.CHAIR: tmp_path})
    path = tmp_path / "broken.md"
    path.write_bytes(b"\xff")
    with pytest.raises(KBError, match="UTF-8"):
        load_kb({Role.SURG: tmp_path})
    path.write_text("## SURG-KB-01\n" + "word " * 40)
    with pytest.raises(KBError, match="source title"):
        load_kb({Role.SURG: tmp_path})


def test_tokenizer_is_simple() -> None:
    assert tokenize("RENAL, renal-risk ICD-10 I25.1 eGFR_38") == ["renal", "renal", "risk", "icd", "10", "i25", "1", "egfr", "38"]
    assert tokenize(" ") == []


def test_bm25_ranking_scores_and_role_isolation() -> None:
    kb = load_kb({Role.SURG: FIXTURES / "surgeon", Role.PHYS: FIXTURES / "physician"})
    result = kb.retrieve(Role.SURG, 1, "AIRWAY")
    assert result.role == Role.SURG and result.round == 1 and result.query == "AIRWAY"
    assert len(result.passages) == len(result.scores) == 5
    assert [p.id for p in result.passages] == ["SURG-KB-05", "SURG-KB-01", "SURG-KB-02", "SURG-KB-03", "SURG-KB-04"]
    assert result.scores == pytest.approx([math.log(5.5 / 1.5), 0, 0, 0, 0])
    assert result.model_validate_json(result.model_dump_json()) == result


def test_ties_repeatably_sort_by_id_not_file_order(tmp_path: Path) -> None:
    for i in range(6, 0, -1):
        write_kb(tmp_path, "word " * 40, id=f"SURG-KB-{i:02}", name=f"reverse-{7-i}.md")
    kb = load_kb({Role.SURG: tmp_path})
    expected = [f"SURG-KB-{i:02}" for i in range(1, 6)]
    for _ in range(3):
        result = kb.retrieve(Role.SURG, 1, "unseen")
        assert [p.id for p in result.passages] == expected
        assert result.scores == [0] * 5
    # Retrieval itself must break ties, even if stored passage order changes.
    kb.passages[Role.SURG] = tuple(reversed(kb.passages[Role.SURG]))
    assert [p.id for p in kb.retrieve(Role.SURG, 1, "unseen").passages] == expected


def test_round1_query_uses_only_keywords_and_configured_sections(case: CaseContext, config: Config) -> None:
    config.roles[Role.SURG].keywords = ["operative risk", "kidney"]
    config.retrieval.case_sections = ["CASE-tests", "CASE-absent"]
    own = argument()
    own.claims = [claim("R1-SURG-C1", "not-query-flagged-claim")]
    query = build_query(Role.SURG, 1, case, config, [own, argument(Role.PHYS)],
                        [judge_score("R1-SURG", "R1-SURG-C1")])
    assert query == "operative risk kidney\n" + CLINICAL


def test_round2_query_adds_peer_summaries_and_flagged_own_claims(case: CaseContext, config: Config) -> None:
    own = argument()
    own.claims = [claim("R1-SURG-C1", "flagged-first"), claim("R1-SURG-C2", "not-flagged"),
                  claim("R1-SURG-C3", "flagged-feedback")]
    peers = [argument(Role.PHYS), argument(Role.ANAES), argument(Role.ADMIN)]
    scores = [judge_score("R1-SURG", "R1-SURG-C1", "R1-SURG-C3"),
              judge_score("R1-PHYS", "R1-SURG-C2")]
    later = judge_score("R1-SURG", "R1-SURG-C2")
    later.round = 2
    query = build_query(Role.SURG, 2, case, config, [own, *peers, argument(Role.PHYS, 2)], [*scores, later])
    base = build_query(Role.SURG, 1, case, config)
    assert query == base + "\nsummary-ADMIN-1\nsummary-ANAES-1\nsummary-PHYS-1\nflagged-first\nflagged-feedback"
    assert build_query(Role.SURG, 2, case, config, list(reversed([own, *peers])), list(reversed(scores))) == query


def test_invalid_round_and_failed_own_argument(case: CaseContext, config: Config) -> None:
    kb = load_kb({Role.SURG: FIXTURES / "surgeon"})
    with pytest.raises(KBError, match="only rounds"):
        kb.retrieve(Role.SURG, 3, "query")
    with pytest.raises(KBError, match="not loaded"):
        kb.retrieve(Role.RED, 1, "query")
    with pytest.raises(KBError, match="only rounds"):
        build_query(Role.SURG, 3, case, config)
    with pytest.raises(KBError, match="keywords"):
        build_query(Role.CHAIR, 1, case, config)
    for previous in ([], [argument(), argument()], [argument().model_copy(update={"status": "failed"})]):
        with pytest.raises(KBError, match="successful own Round 1"):
            build_query(Role.SURG, 2, case, config, previous)


def test_round2_carries_cited_passages_without_changing_top_five() -> None:
    from council.models import Citation
    kb = load_kb({Role.SURG: FIXTURES / "surgeon"})
    own = argument()
    own.claims = [claim("R1-SURG-C1", "Synthetic evidence")]
    own.claims[0].citations = [Citation(passage_id=id, quote="Synthetic quotation of evidence",
                                      source_type="case" if id.startswith("CASE") else "kb",
                                      verified=False, verify_note="not checked")
                             for id in ["SURG-KB-06", "SURG-KB-01", "CASE-tests", "SURG-KB-06"]]
    result = kb.retrieve(Role.SURG, 2, "unknown")
    before = deepcopy(result)
    shown = kb.round2_passages(result, own)
    assert [p.id for p in shown] == [f"SURG-KB-{i:02}" for i in range(1, 7)]
    assert shown[-1].text == kb.passages[Role.SURG][-1].text
    assert result == before
    own.claims[0].citations[0].passage_id = "PHYS-KB-01"
    assert all(p.kb == "SURG" for p in kb.round2_passages(result, own))
    assert own.claims[0].citations[0].passage_id == "PHYS-KB-01"
    with pytest.raises(KBError, match="carryover"):
        kb.round2_passages(result, argument(Role.PHYS))


def test_same_tokenizer_for_corpus_and_query(monkeypatch: pytest.MonkeyPatch) -> None:
    from council import kb as module
    calls: list[str] = []

    def spy(text: str) -> list[str]:
        calls.append(text)
        return tokenize(text)

    monkeypatch.setattr(module, "tokenize", spy)
    kb = load_kb({Role.SURG: FIXTURES / "surgeon"})
    kb.retrieve(Role.SURG, 1, "AIRWAY-risk")
    assert calls == [p.text for p in kb.passages[Role.SURG]] + ["AIRWAY-risk"]
