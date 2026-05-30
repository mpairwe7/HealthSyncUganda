# Maintainers

This file lists the people with merge rights on `main` and binding-vote authority under [ADR 0000 — Open-source governance model](docs/adr/0000-governance.md).

**Format note for showcase reviewers:** lines below the heading are populated by the project lead before submission. Placeholders are written as `[Role to populate]` with no fake names — fabricating maintainer identities for a government submission would be misrepresentation. The maintainer roster is verifiable against GitHub commit history once populated.

---

## Current maintainers

| GitHub handle           | Name                       | Role                       | Primary areas                                                                                                | Contact                                |
| ----------------------- | -------------------------- | -------------------------- | ----------------------------------------------------------------------------------------------------------- | -------------------------------------- |
| `[github-handle]`       | [Project lead to populate] | Lead maintainer            | Architecture (ARCHITECTURE.md), security (SECURITY.md), governance (ADR 0000)                                | `[email]`                              |
| `[github-handle]`       | [Backend maintainer]       | Maintainer                 | Backend (`backend/app/`), FHIR conformance (INTEROPERABILITY.md), data model (DATA_MODEL.md)                  | `[email]`                              |
| `[github-handle]`       | [Frontend maintainer]      | Maintainer                 | Frontend (`frontend/`), PWA / offline contract (ADR 0003), design system (DESIGN_SYSTEM.md)                  | `[email]`                              |
| `[github-handle]`       | [SRE / DevOps maintainer]  | Maintainer                 | CI/CD (`.github/workflows/`), deployment (DEPLOYMENT.md), observability (OBSERVABILITY.md)                   | `[email]`                              |

## Reviewers

Reviewers can approve PRs in their declared areas of expertise but cannot single-handedly merge them. Promotion criteria in [ADR 0000](docs/adr/0000-governance.md).

| GitHub handle           | Name                       | Declared expertise                                                       |
| ----------------------- | -------------------------- | ------------------------------------------------------------------------ |
| `[github-handle]`       | [Reviewer to populate]     | [Area, e.g. "supply ledger", "interop adapters", "design tokens"]         |

## Security contacts

For coordinated disclosure of vulnerabilities use the path documented in the repository-root [`SECURITY.md`](SECURITY.md). The contact below is the **non-technical** escalation path (e.g. legal / press); the technical contact is the lead maintainer above.

| Role                                | Person                     | Contact                          |
| ----------------------------------- | -------------------------- | -------------------------------- |
| Data Protection Officer (DPO)        | [DPO to populate]          | `[email + PGP key fingerprint]`  |
| MoH liaison                          | [MoH liaison to populate]  | `[email]`                        |

## Honorary / emeritus

Maintainers who have stepped back retain attribution on past commits and are listed here for the project record. Empty at present.

---

## How to reach the maintainers

- **For routine technical questions:** open a GitHub issue.
- **For governance, ADR proposals, or maintainer promotion:** open a PR per [ADR 0000](docs/adr/0000-governance.md).
- **For security disclosures:** use [`SECURITY.md`](SECURITY.md). Do *not* open a public issue.
- **For Showcase panel queries:** use the contact rows in [`docs/TEAM.md` §"Contact for the showcase panel"](docs/TEAM.md#6-contact-for-the-showcase-panel).

## How this file is kept current

- A PR adding or removing a maintainer follows the lazy-consensus procedure in [ADR 0000](docs/adr/0000-governance.md).
- An inactive maintainer (six consecutive months) is moved to **Honorary / emeritus** via the same procedure.
- This file is reviewed in every quarterly Security & Privacy Review meeting.
