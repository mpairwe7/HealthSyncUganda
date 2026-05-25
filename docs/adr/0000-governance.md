# ADR 0000: Open-source governance model

- **Status:** Accepted
- **Date:** 2026-05-25
- **Deciders:** Project lead + initial core engineering group
- **Supersedes:** —
- **Superseded by:** —

## Context

HealthSync Uganda is licensed under Apache-2.0 and is engineered to be **donated to the Government of Uganda** once it has been accepted into the National Innovator Registry and proven through the pilot. After donation, the platform needs to:

- Continue accepting contributions from Ugandan engineers, MoH internal staff, NITA-U operators, and the wider open-source community.
- Maintain consistent technical direction across multiple contributing entities.
- Protect data-protection guarantees (DPPA 2019) that depend on architectural invariants — guarantees that a poorly-governed project would erode through ad-hoc patching.

This ADR establishes the governance model that makes those three goals durable. It is intentionally lightweight (a small project does not need ASF-scale governance) but explicit (a government-adopted project cannot rely on tacit norms).

## Decision

The project adopts a **consensus-seeking maintainer model** with three tiers of contributor authority, a clear escalation path, and an architecture-review function backed by [ADRs](./).

### Tiers

| Tier            | Authority                                                                 | Promotion criteria                                                                                                   |
| --------------- | ------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------- |
| **Contributor** | Open PRs; comment on issues.                                              | Anyone with a GitHub account.                                                                                          |
| **Reviewer**    | Approve PRs in declared areas of expertise.                               | Three substantive merged PRs + nomination by a maintainer + lazy-consensus approval by the maintainer group (5 working days). |
| **Maintainer**  | Merge PRs; cut releases; cast binding votes on ADRs.                       | Six months as Reviewer + nomination + lazy-consensus approval of the maintainer group.                                |

The current maintainer list is in [`MAINTAINERS.md`](../../MAINTAINERS.md) at the repository root. Maintainer additions and removals are themselves merge-able PRs.

### Decision-making

1. **Routine code changes** follow the PR workflow in [CONTRIBUTING.md](../../CONTRIBUTING.md): two reviewer approvals; CI green; merged by a maintainer.
2. **Architecturally significant decisions** require an ADR. "Architecturally significant" means: changes the data model, the role hierarchy, the wire format on `/fhir/*` or `/api/v1/*`, the audit-log shape, the resilience contract, the deployment topology, or the governance model itself.
3. **ADRs are proposed as PRs** under `docs/adr/NNNN-slug.md`. The PR is open for **10 working days** for community review. During that window:
   - Any Reviewer or Maintainer may raise a concern. Concerns are tracked as PR comments and must be addressed substantively (not necessarily resolved in the proposer's favour).
   - Two Maintainer approvals are required to mark the ADR `Accepted`. A formal vote is held only if consensus cannot be reached during the open window.
4. **Security and privacy decisions** carry an additional reviewer: the named DPO (see [TEAM.md §1.4 Advisors](../TEAM.md#14-advisors-and-reviewers)). The DPO has a **veto** on changes that affect:
   - The audit log's shape, retention, or append-only invariant.
   - The consent model.
   - The role hierarchy in `app/core/security.py`.
   - The PII inventory in [DATA_MODEL.md](../DATA_MODEL.md).
   The DPO must articulate the veto rationale in writing; the proposer may revise the PR and re-submit.
5. **Architecture Review Board** (ARB) meets **monthly**. Composition: 2 maintainers + 1 external technical advisor + 1 clinical advisor. The ARB:
   - Reviews open ADRs.
   - Reviews the [Roadmap Closure Plan](../THREAT_MODEL.md#7-roadmap-closure-plan) for slippage.
   - Recommends — but does not unilaterally decide — significant trade-offs to the maintainer group.
   - Minutes posted to `docs/governance/arb-YYYY-MM.md` (directory created on first meeting).
6. **Security & Privacy Review** meets **quarterly**. Composition: a maintainer + the DPO + the cybersecurity advisor. Outputs: updates to [THREAT_MODEL.md §6](../THREAT_MODEL.md#6-residual-risk-register), [SECURITY.md](../SECURITY.md), and the [DPIA](../DPIA.md) where new processing activities have entered scope.
7. **Escalation.** A Reviewer or Maintainer who disagrees with a decision may escalate to the ARB. If the disagreement is still unresolved, it goes to a **two-thirds vote of the maintainer group**. Vote outcomes are recorded in the ADR that the disagreement is about.

### Conflict-of-interest rule

A maintainer who has a direct material interest in a decision (e.g. their employer's product is favoured by the choice) **must abstain** from the binding vote and disclose the interest in the PR description.

### Removing a maintainer

A maintainer may be removed by lazy consensus among the other maintainers for:

- Six consecutive months of inactivity (no PR reviews, no ARB attendance), or
- Conduct violations under [CODE_OF_CONDUCT.md](../../CODE_OF_CONDUCT.md), or
- A breach of the conflict-of-interest rule, or
- At their own request.

Removal does not invalidate the maintainer's prior contributions; commit attributions remain.

### Capacity building

The project commits — separately from this governance ADR — to the capacity-building activities in [TEAM.md §5 Capacity building](../TEAM.md#5-capacity-building). These are *project commitments*, not *governance rules*; they are enumerated in TEAM.md so that the showcase panel can score them under *Local Innovation Value*.

## Rationale

We considered three alternative governance models:

1. **Benevolent Dictator (BDFL).** Light overhead but fragile — single point of failure; difficult to defend in a government-donation context where the dictator is also the donor.
2. **ASF-style merit-based PMC.** Robust but heavyweight for a project at this stage. Defer to a later ADR if the maintainer group grows beyond ~7.
3. **CNCF-style consensus-seeking with maintainer tiers.** Adopted here. Proven at scale (Kubernetes, OpenTelemetry, Envoy) and lightweight enough for a project at this stage.

The DPO-veto extension to the CNCF model is unusual but necessary: a national-health platform processing special-category data under DPPA 2019 cannot make privacy decisions by simple majority of engineering staff.

## Consequences

**Positive.**
- Clear path for Ugandan engineers and MoH staff to grow from Contributor to Maintainer.
- Decisions are written down and durable; new maintainers can read the ADRs to understand "why".
- DPO veto is a hard guarantee for the privacy-relevant invariants.

**Negative.**
- ADR overhead can slow architectural decisions. We accept this — the kind of decision that needs an ADR is the kind that benefits from a 10-day public-review window.
- Lazy-consensus promotion can be gamed by a clique. The conflict-of-interest rule + open maintainer list mitigate.

**Neutral.**
- Quarterly review cadence is a commitment to administrative work. The Security & Privacy Review meeting is also where the [Roadmap Closure Plan](../THREAT_MODEL.md#7-roadmap-closure-plan) gets its monthly heartbeat.

## References

- [TEAM.md](../TEAM.md) — named roster, advisors, capacity-building commitments.
- [MAINTAINERS.md](../../MAINTAINERS.md) — current maintainer list and how to reach them.
- [CONTRIBUTING.md](../../CONTRIBUTING.md) — PR workflow that this ADR sits on top of.
- [CODE_OF_CONDUCT.md](../../CODE_OF_CONDUCT.md) — behavioural baseline for the community.
- [THREAT_MODEL.md §7 Roadmap Closure Plan](../THREAT_MODEL.md#7-roadmap-closure-plan) — what the Security & Privacy Review reviews.
- [SECURITY.md](../SECURITY.md) — how vulnerabilities are reported, triaged, and disclosed.
