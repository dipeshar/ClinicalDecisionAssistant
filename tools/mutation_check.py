"""Re-run committed-code audits. Synthetic decision support; clinical sign-off required."""

import argparse
import ast
import json
from pathlib import Path
import subprocess
import sys
from typing import Any, Sequence

ROOT = Path(__file__).resolve().parents[1]
Mutation = tuple[str, str, str, str, str]


def build_t1(source: str) -> list[Mutation]:
    """Keep the original T1 rules, also covering contract shapes added later."""
    tree = ast.parse(source)
    lines = source.splitlines(keepends=True)
    mutations: list[Mutation] = []


    def add(rule: str, old: str, new: str, test: str) -> None:
        assert old in source, (rule, old)
        mutations.append((rule, source.replace(old, new, 1), test, old.strip(), new.strip()))


    for node in tree.body:
        if not isinstance(node, ast.ClassDef) or node.name == "ContractModel":
            continue
        if any(isinstance(base, ast.Name) and base.id == "StrEnum" for base in node.bases):
            assignment = next(child for child in node.body if isinstance(child, ast.Assign))
            old = "".join(lines[assignment.lineno - 1:assignment.end_lineno])
            new = old.replace(assignment.value.value, "INVALID")
            changed = "".join(lines[:assignment.lineno - 1] + [new] + lines[assignment.end_lineno:])
            mutations.append((f"Exact enum {node.name}", changed, f"test_enum_values[{node.name}-",
                              f"{node.name}: {old.strip()}", new.strip()))
        else:
            field = next(child for child in node.body if isinstance(child, ast.AnnAssign))
            start, end = field.lineno - 1, field.end_lineno
            changed = "".join(lines[:start] + ["    pass  # deliberately removed field\n"] + lines[end:])
            mutations.append((f"Shape {node.name}", changed, f"test_contract_round_trip_and_fields[{node.name}]",
                              f"{node.name}.{field.target.id}", "removed field"))

    add("Reject extra/trust fields", 'extra="forbid"', 'extra="ignore"', "test_drafts_reject_code_owned_fields")
    add("Finite numeric values", "allow_inf_nan=False", "allow_inf_nan=True", "test_finite_numbers")
    add("Rating lower bound", "strict=True, ge=1, le=5", "strict=True, ge=0, le=5", "test_rating_bounds_and_integer_type")
    add("Rating upper bound", "strict=True, ge=1, le=5", "strict=True, ge=1, le=6", "test_rating_bounds_and_integer_type")
    add("Rating integer type", "strict=True, ge=1, le=5", "strict=False, ge=1, le=5", "test_rating_bounds_and_integer_type")
    add("Percentage lower bound", "Field(ge=0, le=100)", "Field(ge=-1, le=100)", "test_percentage_bounds")
    add("Percentage upper bound", "Field(ge=0, le=100)", "Field(ge=0, le=101)", "test_percentage_bounds")
    add("Positive revision index", "Field(strict=True, ge=1)", "Field(strict=True, ge=0)", "test_revision_index_rules")
    add("Round domain", "Round = Literal[1, 2]", "Round = Literal[1, 2, 3]", "test_two_rounds_and_attempts_only")
    add("Judge domain", 'Judge = Literal["JUDGE_A", "JUDGE_B"]', 'Judge = Literal["JUDGE_A", "JUDGE_B", "SURG"]', "test_judges_only")
    add("Attempt domain", "attempt: Literal[1, 2]", "attempt: Literal[1, 2, 3]", "test_two_rounds_and_attempts_only")
    add("Revision action/index relationship", "if (self.action == RevisionAction.DROPPED) != (self.new_claim_index is None):", "if False:", "test_revision_index_rules")
    add("Failed stance null", "if self.stance is not None:", "if False:", "test_failed_argument_rejects_content")
    add("Failed lists empty", "if self.claims or self.conditions or self.uncertainties:", "if False:", "test_failed_argument_rejects_content")
    add("Failed rebuttal/revisions null", "if self.rebuttal is not None or self.revisions is not None:", "if False:", "test_failed_argument_rejects_content")
    add("Failed reason required", "if not self.failure_reason:", "if False:", "test_failed_argument_rejects_content")
    add("Successful stance required", "if self.stance is None:", "if False:", "test_ok_argument_requires_stance_and_no_failure")
    add("Successful failure reason null", "if self.failure_reason is not None:", "if False:", "test_ok_argument_requires_stance_and_no_failure")
    add("Round 1 no revision/rebuttal", "if self.round == 1 and (self.rebuttal is not None or self.revisions is not None):", "if False:", "test_round1_has_no_rebuttal_or_revisions")
    add("Round 1 no counterargument score", "if self.round == 1 and self.counterarguments is not None:", "if False:", "test_score_round_rules")
    add("Round 2 counterargument score required", "if self.round == 2 and self.counterarguments is None:", "if False:", "test_score_round_rules")
    add("Round 2 feedback empty", "if self.round == 2 and self.feedback:", "if False:", "test_score_round_rules")
    add("Bare report incomplete", "if self.status != ReportStatus.INCOMPLETE:", "if False:", "test_bare_report_rejects_chair_content")
    add("Bare report null confidence/warning", "if self.confidence is not None or self.council_warning is not None:", "if False:", "test_bare_report_rejects_chair_content")
    add("Bare report empty chair content", "if (self.recommendation_basis or self.strongest_for or self.strongest_against\n                    or self.required_actions or self.dissent or self.role_notes or self.narrative):", "if False:", "test_bare_report_rejects_chair_content")
    add("Non-bare confidence required", "elif self.confidence is None:", "elif False:", "test_non_bare_report_requires_confidence")
    add("Fixed disclaimer", 'disclaimer: Literal[\n        "decision support only, requires human clinical sign-off, synthetic data"\n    ] = DISCLAIMER', "disclaimer: str = DISCLAIMER", "test_fixed_disclaimer")
    add("Required fields", "passage_id: str\n", 'passage_id: str = ""\n', "test_required_fields")
    add("Optional human comment", 'comment: str = ""', "comment: str", "test_optional_human_comment_and_red_persona")
    add("Optional red-team persona", "persona_prompt: str | None = None", "persona_prompt: str | None", "test_optional_human_comment_and_red_persona")
    for old, new in [
        ("citations: list[CitationDraft]", "citations: list[Citation]"),
        ("claims: list[ClaimDraft]", "claims: list[Claim]"),
        ("response_claims: list[ClaimDraft]", "response_claims: list[Claim]"),
        ("rebuttal: RebuttalDraft | None", "rebuttal: Rebuttal | None"),
        ("revisions: list[RevisionDraft] | None", "revisions: list[Revision] | None"),
        ("findings: list[RedTeamFindingDraft]", "findings: list[RedTeamFinding]"),
        ("injection_check: InjectionCheckDraft", "injection_check: InjectionCheck"),
    ]:
        expected = "test_round2_argument_draft_round_trip" if old.startswith(("rebuttal:", "revisions:")) else "test_contract_round_trip_and_fields"
        add("Nested draft " + old, old, new, expected)

    return mutations


def build_from_spec(source: str, spec: list[dict[str, str]]) -> list[Mutation]:
    """Later tasks can supply rule/old/new/test entries in a JSON list."""
    mutations: list[Mutation] = []
    for row in spec:
        if set(row) != {"rule", "old", "new", "test"}:
            raise ValueError("mutation entries require rule, old, new and test")
        if not all(isinstance(value, str) and value for value in row.values()):
            raise ValueError("mutation entries must contain nonempty strings")
        if source.count(row["old"]) != 1:
            raise ValueError(f"mutation must match exactly once: {row['rule']}")
        mutations.append((row["rule"], source.replace(row["old"], row["new"], 1),
                          row["test"], row["old"], row["new"]))
    return mutations


def require_clean(root: Path) -> None:
    """Never overwrite unrelated work during an audit."""
    status = subprocess.run(["git", "status", "--porcelain"], cwd=root,
                            capture_output=True, text=True, check=True)
    if status.stdout.strip() or status.stderr.strip():
        raise ValueError("mutation audit requires a clean, fully readable Git working tree")


def run_tests(root: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-B", "-X", "pycache_prefix=.venv/mutation-unused-pycache",
         "-m", "pytest", "-p", "no:cacheprovider", "-q", "--tb=no"],
        cwd=root, capture_output=True, text=True, timeout=120,
    )


def run_mutation(root: Path, target: Path, mutation: Mutation) -> dict[str, Any]:
    """Restore the tracked target even when tests fail, time out or are interrupted."""
    rule, changed, expected, old, new = mutation
    require_clean(root)
    relative = target.relative_to(root).as_posix()
    subprocess.run(["git", "ls-files", "--error-unmatch", "--", relative],
                   cwd=root, capture_output=True, check=True)
    try:
        target.write_text(changed, encoding="utf-8")
        run = run_tests(root)
        failed = [line for line in run.stdout.splitlines() if line.startswith("FAILED ")]
        # A clean exit (0) is the only outcome that means the mutation survived. Any
        # other exit code is a kill: an ordinary test failure (1), a collection error
        # from an import-time crash (2), or anything else pytest can report. Do not
        # gate on a "FAILED " line naming `expected`: a collection error never
        # produces one, since it happens before any test runs, yet it just as surely
        # proves the code broke and the suite no longer passes.
        killed = run.returncode != 0
        return dict(rule=rule, broke=old, replacement=new, killed=killed,
                    failed_tests=failed, exit_code=run.returncode)
    finally:
        subprocess.run(["git", "restore", "--", relative], cwd=root, check=True)
        require_clean(root)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", default="src/council/models.py")
    parser.add_argument("--spec", type=Path, help="JSON mutations for a later task; default: built-in T1")
    parser.add_argument("--start", type=int, default=0)
    parser.add_argument("--end", type=int)
    parser.add_argument("--list", action="store_true", help="preview without changing files")
    args = parser.parse_args(argv)
    target = (ROOT / args.target).resolve()
    if not target.is_relative_to(ROOT):
        raise ValueError("target must be inside the repository")
    source = target.read_text(encoding="utf-8")
    mutations = (build_from_spec(source, json.loads(args.spec.read_text(encoding="utf-8")))
                 if args.spec else build_t1(source))
    end = len(mutations) if args.end is None else args.end
    if not 0 <= args.start < end <= len(mutations):
        raise ValueError("select a nonempty range within the mutation list")
    if args.list:
        print(json.dumps([dict(index=i, rule=item[0], test=item[2])
                          for i, item in enumerate(mutations)], indent=2))
        return 0
    require_clean(ROOT)
    baseline = run_tests(ROOT)
    if baseline.returncode != 0:
        print(baseline.stdout + baseline.stderr)
        raise ValueError("baseline tests must pass before mutation checking")
    results: list[dict[str, Any]] = []
    output = ROOT / ".venv/mutation-results.json"
    for index in range(args.start, end):
        record = dict(index=index, **run_mutation(ROOT, target, mutations[index]))
        results.append(record)
        output.write_text(json.dumps(results, indent=2), encoding="utf-8")
        print(f"{index}: {record['rule']}: {'KILLED' if record['killed'] else 'SURVIVED/ERROR'}", flush=True)
        if not record["killed"]:
            return 1
    print(f"Detected {len(results)} mutations; restored committed code; Git status clean.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
