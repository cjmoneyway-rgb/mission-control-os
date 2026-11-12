# Proposed `AGENTS.md` — Do Not Treat as Installed Policy

> **Status: PROPOSED / NOT APPROVED.** No repository `AGENTS.md` existed on 2026-07-28. If approved, review and install separately at repository root.

## Purpose

Mission Control OS™ is a governance-first executive-workflow prototype. Preserve truthful capability boundaries and support human leadership; do not portray planned integrations or demonstrations as production operation.

## Brand and governance principles

Accuracy before speed; context before automation; human approval before representation; systems before scale; governance first. Keep CURRENT, PARTIAL, PLANNED, CONCEPTUAL, BLOCKED, and UNKNOWN distinct. Label recommendations as unapproved.

## Repository structure

- `main.py`: CLI.
- `mission_control/`: configuration, routing/execution, governance, models, providers, audit.
- `tests/`: local unit/contract tests.
- `examples/`: demonstration input only.
- `docs/`: architecture and working materials; source material belongs in `docs/source-materials/` only when sanitized and authorized.

## Protected files/assets

Do not modify Devpost/submission materials, demo/public links, public-facing assets, production systems, external services, credentials, or private exports without explicit authorization. Ask the CEO to identify additional protected paths before work.

## Naming and code conventions

Use clear Python 3.10+ typing, dataclasses for current contracts, snake_case identifiers, and configured display names. Do not merge departments because names resemble one another. Never wrap imports in broad `try/except`; optional dependency handling may catch `ImportError` at the point of use.

## Tests

Run `python -m unittest discover -s tests -v`. For safe local smoke testing use `python main.py --demo --no-log`. Validate department JSON with `python -m json.tool mission_control/departments.json`.

## Documentation requirements

Cite evidence, date audits, state scope, identify sample data, preserve conflicts, list missing inputs, and record test results. Mermaid diagrams must distinguish confirmed (solid) and planned (dashed) links.

## Data handling

Never commit secrets, `.env`, private CRM/guest exports, confidential contacts, or unsanitized logs. Minimize payloads; use approved secret management; do not send private data to AI/external tools without an approved classification, purpose, consent/legal basis, retention, and access policy.

## Approval boundaries

Humans—and the CEO where required—retain final authority for external representation, guest approval/release, sensitive relationships, factual conflicts, sponsorship, compensation, legal/public commitments, brand decisions, and governance exceptions.

## Definition of done

Claims match evidence; statuses are explicit; tests pass or limitations are recorded; no protected assets/secrets changed; approvals are recorded; documentation and rollback/operating notes are current; human review is complete.

## Known quirks and current architecture

The prototype routes to exactly one context. Mock routing is substring-based and order-sensitive on ties. Governance checks only required headings and two secret patterns. One revision is attempted; a second failure is not technically blocked. JSONL stores full records without access/retention controls. OpenAI live mode is adapter-level, not live-validated. CRM/Drive/Sheets writeback and enterprise dashboard are roadmap.
