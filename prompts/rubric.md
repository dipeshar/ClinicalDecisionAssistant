# Judging rubric

Score each criterion 1 to 5. Use 2 or 4 for a case that falls between the anchors below. Write one short justification per criterion, quoting or pointing at the specific claim it's about.

## Groundedness

Does every claim trace to a real source, and does that source actually support what the claim says? This is not the same check the code already runs. Code confirms a cited quote exists in the passage. You judge whether the passage actually backs up the claim being made — a claim can cite a real quote and still overstate or misuse it.

**Capping rule:** if even one claim cites something real but that source does not actually support what the claim asserts, the argument cannot score above 2 for groundedness, no matter how well-grounded the other claims are. Don't average it away.

- **5**: Every claim is grounded, and every citation clearly supports it. No claim goes further than its source.
- **3**: Every claim is honestly grounded, but one or two citations are only loosely related to the claim, or support it weakly rather than clearly. No claim is actually false or misused, just under-supported.
- **2 (capped)**: At least one claim cites something real that does not actually support what the claim says. Apply this score regardless of how strong the rest of the argument is.
- **1**: Multiple claims are uncited, or multiple claims misuse their sources, or the argument asserts things no source says at all.

## Logic

Does the reasoning hold together? Does the stance follow from the claims, and are the claims consistent with each other?

- **5**: The stance follows clearly from the claims. Every claim supports the direction taken. No contradictions.
- **3**: The reasoning mostly holds, but there's a gap, or one claim doesn't clearly support the stance.
- **1**: The stance doesn't follow from the claims, claims contradict each other, or the argument reasons past its own evidence.

## Honesty about uncertainty

Does the specialist say what it doesn't know, rather than writing as if everything is settled?

- **5**: Uncertainties are clearly stated, and confidence is calibrated to what the case and knowledge base actually establish.
- **3**: Some uncertainty is acknowledged, but vaguely, or without saying what would resolve it.
- **1**: The argument reads as fully certain, with no uncertainty named, even though real gaps exist in the case or the evidence.

## Counterarguments addressed (Round 2 only)

Does the rebuttal engage the strongest opposing claim, or does it talk past it? This field is required even when it doesn't apply — set it to `null` in Round 1, don't omit it.

- **5**: The rebuttal engages the opposing claim directly, with a grounded, substantive response. Not a restatement of the specialist's own Round 1 position.
- **3**: The rebuttal responds, but only partially or generically, without engaging the substance.
- **1**: The rebuttal ignores the opposing claim, misstates it, or just repeats the Round 1 position.

## Untraceable claims

List any claim whose citation, even if it passed the code's exists-and-matches check, does not actually support what the claim asserts — the same distinction the groundedness section above describes, applied here as its own list. Every claim listed here also triggers the groundedness capping rule — the two should always agree.
