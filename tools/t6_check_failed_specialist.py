"""Standalone check: a specialist whose Round 1 turn itself failed.

Builds one case with four specialists: SURG's Round 1 turn failed (status
"failed", per contracts section 5 rule 17: null stance, empty claims), and
PHYS, ANAES and ADMIN each have an ok Round 1 argument. Round 2 never runs
for SURG (contracts rule 16), and none is supplied here for the others
either, so every final argument is each specialist's Round 1 turn.

Calls the real `final_arguments` and `compute_confidence` directly; no test
runner involved. Synthetic data only; no provider or model calls.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from council.models import Argument, Claim, Recommendation, Score  # noqa: E402
from council.scoring import compute_confidence, compute_dissent, final_arguments  # noqa: E402


def argument(role: str, status: str = "ok", stance: str | None = "for") -> Argument:
    argument_id = f"R1-{role}"
    failed = status == "failed"
    return Argument(
        argument_id=argument_id, role=role, round=1, stance=None if failed else stance,
        summary="Synthetic position", claims=[] if failed else [
            Claim(claim_id=f"{argument_id}-C1", text="Synthetic claim", citations=[],
                  grounding_status="grounded"),
        ], conditions=[], uncertainties=[], rebuttal=None, revisions=None,
        stance_changed=False, retrieved_passage_ids=[], repair_used=False,
        status=status, failure_reason="Synthetic failure" if failed else None,
    )


def score(arg: Argument, ratings: tuple[int, int, int], judge: str) -> Score:
    return Score(judge=judge, argument_id=arg.argument_id, model="fake/judge", round=1,
                 groundedness=ratings[0], logic=ratings[1], uncertainty=ratings[2],
                 counterarguments=None, justification={}, untraceable_claims=[], feedback=[])


def main() -> None:
    surg = argument("SURG", status="failed")  # Round 1 turn itself failed
    phys = argument("PHYS", stance="for")
    anaes = argument("ANAES", stance="against")
    admin = argument("ADMIN", stance="conditional")
    arguments = [surg, phys, anaes, admin]

    scores = [
        score(phys, (5, 5, 5), "JUDGE_A"), score(phys, (5, 5, 5), "JUDGE_B"),
        score(anaes, (4, 4, 4), "JUDGE_A"), score(anaes, (4, 4, 4), "JUDGE_B"),
        score(admin, (3, 3, 3), "JUDGE_A"), score(admin, (3, 3, 3), "JUDGE_B"),
    ]

    recommendation = Recommendation.PROCEED  # accepts only "for"
    final = final_arguments(arguments)
    role_notes = {"PHYS": "Accepts the recommendation.", "ANAES": "Dissents.", "ADMIN": "Dissents."}
    dissent = compute_dissent(recommendation, arguments, role_notes)
    confidence = compute_confidence(recommendation, arguments, scores, [])

    final_roles = [arg.role.value for arg in final]
    dissent_roles = [entry.role.value for entry in dissent]

    print(f"final_arguments roles: {final_roles}")
    print(f"SURG excluded from specialists_counted: {'SURG' not in final_roles}")
    print(f"specialists_counted: {confidence.inputs.specialists_counted}")
    print(f"SURG appears in dissent: {'SURG' in dissent_roles}")
    print(f"dissent roles: {dissent_roles}")
    print(f"judge_part: {confidence.inputs.judge_part}")
    print(f"agreement_part: {confidence.inputs.agreement_part}")


if __name__ == "__main__":
    main()
