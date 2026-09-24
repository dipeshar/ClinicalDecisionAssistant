"""Data contracts for synthetic decision support requiring clinical sign-off.

Drafts contain only LLM-owned fields, recursively. Full records are assembled
by code. These models validate shapes; source checks, scoring, budget locks,
and orchestration belong to the later tasks listed in docs/tasks.md.
"""

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, JsonValue, model_validator


class Role(StrEnum):
    SURG = "SURG"
    PHYS = "PHYS"
    ANAES = "ANAES"
    ADMIN = "ADMIN"
    JUDGE_A = "JUDGE_A"
    JUDGE_B = "JUDGE_B"
    RED = "RED"
    CHAIR = "CHAIR"


class Stance(StrEnum):
    FOR = "for"
    AGAINST = "against"
    CONDITIONAL = "conditional"


class SourceType(StrEnum):
    CASE = "case"
    KB = "kb"


class GroundingStatus(StrEnum):
    GROUNDED = "grounded"
    UNGROUNDED = "ungrounded"


class RevisionAction(StrEnum):
    KEPT = "kept"
    REVISED = "revised"
    DROPPED = "dropped"


class TurnStatus(StrEnum):
    OK = "ok"
    FAILED = "failed"


class Round2Status(StrEnum):
    OK = "ok"
    FAILED = "failed"
    SKIPPED = "skipped"


class Criterion(StrEnum):
    GROUNDEDNESS = "groundedness"
    LOGIC = "logic"
    UNCERTAINTY = "uncertainty"
    COUNTERARGUMENTS = "counterarguments"


class FindingCategory(StrEnum):
    MISSING_INFO = "missing_info"
    ASSUMPTION = "assumption"
    CONTRADICTION = "contradiction"
    OVERCONFIDENCE = "overconfidence"
    INJECTION = "injection"


class Level(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class InjectionVerdict(StrEnum):
    NO_SIGN = "no_sign"
    POSSIBLE_INFLUENCE = "possible_influence"
    INFLUENCED = "influenced"
    NOT_RUN = "not_run"


class RedTeamInjectionVerdict(StrEnum):
    """Verdicts the model may write; `not_run` is reserved for code."""

    NO_SIGN = "no_sign"
    POSSIBLE_INFLUENCE = "possible_influence"
    INFLUENCED = "influenced"


class ReportStatus(StrEnum):
    COMPLETE = "COMPLETE"
    INCOMPLETE = "INCOMPLETE"


class Recommendation(StrEnum):
    PROCEED = "proceed"
    PROCEED_WITH_MODIFICATIONS = "proceed_with_modifications"
    DELAY_PENDING_INVESTIGATION = "delay_pending_investigation"
    DECLINE = "decline"


class Decision(StrEnum):
    APPROVED = "approved"
    REJECTED = "rejected"
    COMMENT_ONLY = "comment_only"


class Step(StrEnum):
    INGEST = "ingest"
    RETRIEVE = "retrieve"
    SPECIALIST = "specialist"
    JUDGE = "judge"
    RED_TEAM = "red_team"
    CHAIR = "chair"
    HUMAN = "human"


class EventType(StrEnum):
    START = "start"
    LLM_CALL = "llm_call"
    RETRIEVAL = "retrieval"
    VALIDATION = "validation"
    BUDGET = "budget"
    ERROR = "error"
    DECISION = "decision"
    PRIVACY_BLOCK = "privacy_block"


Round = Literal[1, 2]
Judge = Literal["JUDGE_A", "JUDGE_B"]
Rating = Annotated[int, Field(strict=True, ge=1, le=5)]
Percentage = Annotated[float, Field(ge=0, le=100)]
PositiveIndex = Annotated[int, Field(strict=True, ge=1)]
DISCLAIMER = "decision support only, requires human clinical sign-off, synthetic data"


class ContractModel(BaseModel):
    """Reject extra fields, including attempted trust fields in drafts."""

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class InjectionFlag(ContractModel):
    section_id: str
    line_number: int
    matched_pattern: str


class CaseSection(ContractModel):
    id: str
    heading: str
    text: str
    flagged: bool
    flag_reasons: list[str]


class CaseContext(ContractModel):
    case_id: str
    source_file: str
    case_hash: str
    title: str
    sections: list[CaseSection]
    missing_sections: list[str]
    injection_flags: list[InjectionFlag]


class Passage(ContractModel):
    id: str
    kb: str
    source_title: str
    text: str


class RetrievalResult(ContractModel):
    role: str
    round: Round
    query: str
    passages: list[Passage]
    scores: list[float]


class CitationDraft(ContractModel):
    passage_id: str
    quote: str


class Citation(CitationDraft):
    source_type: SourceType
    verified: bool
    verify_note: str


class ClaimDraft(ContractModel):
    text: str
    citations: list[CitationDraft]


class Claim(ContractModel):
    claim_id: str
    text: str
    citations: list[Citation]
    grounding_status: GroundingStatus


class RebuttalDraft(ContractModel):
    target_argument_id: str
    target_claim_id: str
    why_strongest: str
    response_claims: list[ClaimDraft]


class Rebuttal(ContractModel):
    target_argument_id: str
    target_claim_id: str
    why_strongest: str
    response_claims: list[Claim]


class RevisionDraft(ContractModel):
    round1_claim_id: str
    action: RevisionAction
    new_claim_index: PositiveIndex | None
    reason: str

    @model_validator(mode="after")
    def check_index(self) -> Self:
        if (self.action == RevisionAction.DROPPED) != (self.new_claim_index is None):
            raise ValueError("dropped needs a null index; kept/revised need an index")
        return self


class Revision(RevisionDraft):
    new_claim_id: str | None


class ArgumentDraft(ContractModel):
    stance: Stance
    summary: str
    claims: list[ClaimDraft]
    conditions: list[str]
    uncertainties: list[str]
    rebuttal: RebuttalDraft | None
    revisions: list[RevisionDraft] | None


class Argument(ContractModel):
    argument_id: str
    role: Role
    round: Round
    stance: Stance | None
    summary: str
    claims: list[Claim]
    conditions: list[str]
    uncertainties: list[str]
    rebuttal: Rebuttal | None
    revisions: list[Revision] | None
    stance_changed: bool
    retrieved_passage_ids: list[str]
    repair_used: bool
    status: TurnStatus
    failure_reason: str | None

    @model_validator(mode="after")
    def check_failure(self) -> Self:
        if self.status == TurnStatus.FAILED:
            if self.stance is not None:
                raise ValueError("failed argument must have null stance")
            if self.claims or self.conditions or self.uncertainties:
                raise ValueError("failed argument must have empty content lists")
            if self.rebuttal is not None or self.revisions is not None:
                raise ValueError("failed argument must have null rebuttal and revisions")
            if not self.failure_reason:
                raise ValueError("failed argument needs a failure_reason")
        else:
            if self.stance is None:
                raise ValueError("ok argument needs a stance")
            if self.failure_reason is not None:
                raise ValueError("ok argument must have null failure_reason")
        if self.round == 1 and (self.rebuttal is not None or self.revisions is not None):
            raise ValueError("rebuttal and revisions are Round 2 only")
        return self


class UntraceableClaim(ContractModel):
    claim_id: str
    reason: str


class FeedbackNote(ContractModel):
    claim_id: str | None
    note: str


class ScoreDraft(ContractModel):
    argument_id: str
    groundedness: Rating
    logic: Rating
    uncertainty: Rating
    counterarguments: Rating | None
    justification: dict[Criterion, str]
    untraceable_claims: list[UntraceableClaim]
    feedback: list[FeedbackNote]


class Score(ScoreDraft):
    judge: Judge
    model: str
    round: Round

    @model_validator(mode="after")
    def check_round(self) -> Self:
        if self.round == 1 and self.counterarguments is not None:
            raise ValueError("Round 1 counterarguments must be null")
        if self.round == 2 and self.counterarguments is None:
            raise ValueError("Round 2 needs a counterarguments score")
        if self.round == 2 and self.feedback:
            raise ValueError("Round 2 feedback must be empty")
        return self


class FailedJudgeCall(ContractModel):
    judge: Judge
    round: Round


class CriterionMeans(ContractModel):
    groundedness: float | None
    logic: float | None
    uncertainty: float | None
    counterarguments: float | None


class CriterionGaps(ContractModel):
    groundedness: int | None
    logic: int | None
    uncertainty: int | None
    counterarguments: int | None


class ArgumentScoreSummary(ContractModel):
    argument_id: str
    role: Role
    round: Round
    judges_scored: list[Judge]
    mean: CriterionMeans
    gap: CriterionGaps
    disagreement_count: int


class RoundMeans(ContractModel):
    round1: float | None
    round2: float | None


class SharedScore(RoundMeans):
    change: float | None


class UngroundedCounts(ContractModel):
    round1: int | None
    round2: int | None


class RevisionCounts(ContractModel):
    kept: int
    revised: int
    dropped: int


class RoundComparison(ContractModel):
    role: Role
    shared_score: SharedScore
    ungrounded_claims: UngroundedCounts
    revisions: RevisionCounts
    round2_status: Round2Status


class Scorecard(ContractModel):
    run_id: str
    scores: list[Score]
    skipped_arguments: list[str]
    failed_judge_calls: list[FailedJudgeCall]
    per_argument: list[ArgumentScoreSummary]
    code_ungrounded_claims: list[str]
    round_comparison: list[RoundComparison]


class RedTeamFindingDraft(ContractModel):
    category: FindingCategory
    severity: Level
    description: str
    evidence_ids: list[str]
    affected_roles: list[Role]
    suggested_action: str


class RedTeamFinding(RedTeamFindingDraft):
    finding_id: str


class InjectionCheckDraft(ContractModel):
    verdict: RedTeamInjectionVerdict
    notes: str


class InjectionCheck(ContractModel):
    verdict: InjectionVerdict
    notes: str
    scanner_flag_count: int
    claims_citing_flagged_lines: list[str]


class RedTeamReportDraft(ContractModel):
    findings: list[RedTeamFindingDraft]
    injection_check: InjectionCheckDraft


class RedTeamReport(ContractModel):
    findings: list[RedTeamFinding]
    injection_check: InjectionCheck


class Penalty(ContractModel):
    count: int
    penalty: float


class ConfidenceInputs(ContractModel):
    judge_part: Percentage
    judge_round_used: Round | None
    agreement_part: Percentage
    specialists_counted: int
    specialists_accepting: int
    base: float
    ungrounded_claims: Penalty
    high_severity_findings: Penalty
    judge_disagreements: Penalty
    total_penalty: float


class Confidence(ContractModel):
    level: Level
    score: Percentage
    inputs: ConfidenceInputs


class JudgeParticipation(ContractModel):
    judge: Judge
    model: str
    rounds_scored: list[Round]


class JudgeSummary(ContractModel):
    mean_score: RoundMeans
    disagreement_count: int
    judges: list[JudgeParticipation]
    failed_judge_calls: list[FailedJudgeCall]
    round_comparison: list[RoundComparison]
    code_ungrounded_claims: list[str]


class PrivacySummary(ContractModel):
    synthetic_marker_found: bool
    ingest_identifier_hits: int
    outbound_prompts_checked: int
    outbound_prompts_blocked: int
    approved_providers: list[str]
    providers_used: list[str]


class RequiredAction(ContractModel):
    text: str
    source_ids: list[str]


class Dissent(ContractModel):
    role: Role
    stance: Stance
    argument_id: str
    note: str


class HumanDecision(ContractModel):
    run_id: str
    decision: Decision
    comment: str = ""
    reviewer: str
    decided_at: datetime
    report_hash: str


class ReportDraft(ContractModel):
    recommendation: Recommendation
    recommendation_basis: list[str]
    strongest_for: list[str]
    strongest_against: list[str]
    required_actions: list[RequiredAction]
    role_notes: dict[Role, str]
    narrative: str


class Report(ContractModel):
    run_id: str
    case_id: str
    status: ReportStatus
    incomplete_reasons: list[str]
    failed_turns: list[str]
    recommendation: Recommendation | None
    recommendation_basis: list[str]
    confidence: Confidence | None
    council_warning: str | None
    strongest_for: list[str]
    strongest_against: list[str]
    required_actions: list[RequiredAction]
    role_notes: dict[Role, str]
    dissent: list[Dissent]
    red_team_findings: list[RedTeamFinding]
    injection_check: InjectionCheck
    privacy_summary: PrivacySummary
    judge_summary: JudgeSummary
    narrative: str
    citations_index: list[Citation]
    disclaimer: Literal[
        "decision support only, requires human clinical sign-off, synthetic data"
    ] = DISCLAIMER
    human_decision: HumanDecision | None

    @model_validator(mode="after")
    def check_bare_report(self) -> Self:
        if self.recommendation is None:
            if self.status != ReportStatus.INCOMPLETE:
                raise ValueError("bare report must be INCOMPLETE")
            if self.confidence is not None or self.council_warning is not None:
                raise ValueError("bare report needs null confidence and council_warning")
            if (self.recommendation_basis or self.strongest_for or self.strongest_against
                    or self.required_actions or self.dissent or self.role_notes or self.narrative):
                raise ValueError("bare report needs empty chair content and dissent")
        elif self.confidence is None:
            raise ValueError("only a bare report may have null confidence")
        return self


class TraceEvent(ContractModel):
    run_id: str
    seq: int
    timestamp: str
    step: Step
    event_type: EventType
    role: str | None
    round: Round | None
    model: str | None
    prompt: str | None
    retrieved_passage_ids: list[str] | None
    raw_output: str | None
    parsed_ref: str | None
    tokens_in: int | None
    tokens_out: int | None
    latency_ms: int | None
    attempt: Literal[1, 2]
    repair: bool
    budget_tokens_used: int
    error: str | None
    finish_reason: str | None
    reasoning: str | None


class BudgetState(ContractModel):
    """Serializable budget state; synchronized accounting is implemented in T7."""

    tokens_used: int
    calls_used: int
    started_at: float
    exhausted: bool
    reason: str | None


class ModelChoice(ContractModel):
    provider: str
    model: str


class ModelChoices(ContractModel):
    specialist: ModelChoice
    chair: ModelChoice
    red_team: ModelChoice
    judge_a: ModelChoice
    judge_b: ModelChoice


class RoleValues(ContractModel):
    specialist: float
    judge: float
    red_team: float
    chair: float


ReasoningEffort = Literal["none", "default", "low", "medium", "high"]


class ReasoningEffortConfig(ContractModel):
    specialist: ReasoningEffort
    judge: ReasoningEffort
    red_team: ReasoningEffort
    chair: ReasoningEffort


class TokenCaps(ContractModel):
    specialist: int
    judge: int
    red_team: int
    chair: int


class ChairReserve(ContractModel):
    tokens: int
    seconds: int
    calls: int


class BudgetConfig(ContractModel):
    max_total_tokens: int
    max_calls: int
    max_seconds_total: int
    chair_reserve: ChairReserve
    max_tokens_per_call: TokenCaps


class RetryConfig(ContractModel):
    max_repair_retries_per_turn: int
    max_api_attempts: int
    api_retry_wait_seconds: float


class RetrievalConfig(ContractModel):
    top_k: int
    case_sections: list[str]


class GroundingConfig(ContractModel):
    quote_words_min: int
    quote_words_max: int


class JudgingConfig(ContractModel):
    disagreement_gap: int
    feedback_max_notes: int
    feedback_max_words: int


class PathsConfig(ContractModel):
    cases: str
    runs: str
    prompts: str


class RoleConfig(ContractModel):
    name: str
    kb: str
    keywords: list[str]
    persona_prompt: str | None = None


class PrivacyConfig(ContractModel):
    synthetic_marker: str
    approved_providers: list[str]


class Config(ContractModel):
    """Shape of the human-owned config.yaml; loading/policy validation is T2."""

    paths: PathsConfig
    models: ModelChoices
    temperature: RoleValues
    reasoning_effort: ReasoningEffortConfig
    budget: BudgetConfig
    retries: RetryConfig
    retrieval: RetrievalConfig
    grounding: GroundingConfig
    judging: JudgingConfig
    roles: dict[Role, RoleConfig]
    privacy: PrivacyConfig


class Source(ContractModel):
    source_type: SourceType
    source_title: str
    text: str


class RunBundle(ContractModel):
    run_id: str
    case_id: str
    created_at: datetime
    config_snapshot: dict[str, JsonValue]
    case_context: CaseContext
    retrievals: list[RetrievalResult]
    arguments: list[Argument]
    scorecard: Scorecard
    red_team: RedTeamReport | None
    report: Report
    sources: dict[str, Source]
