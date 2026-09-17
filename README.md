# a_skills_modernization_skill

A Claude Agent Skill that audits, classifies, and rewrites other Claude skills
(Claude Code personal/project, plugin, and account/Cowork) against real usage
evidence, optimizes for token usage, identifies the appropriate model and
effort level per skill, and rewrites each skill with that model in mind —
applying the result reversibly.

## Contents

- `skill-optimizer/` — the skill itself (`SKILL.md`, references, `scripts/audit.py` and `scripts/apply.py`).
- `modernize-prompt/` — companion skill holding the core per-model rewrite rules that `skill-optimizer` invokes rather than duplicates.
- `PLAN.md` — the design/implementation plan this skill was built from (phases, data contracts, and the binding policy decisions in §5).

## Workflow

1. **Inventory + evidence** (`audit.py inventory`, `audit.py usage`) — walk granted skill surfaces, record frontmatter/size/tokens, attach usage evidence.
2. **Decision gate** — one confirmed yes/no per skill: optimize, disable, or leave as-is. Nothing is written before this.
3. **Audit, route, rewrite** (`audit.py lint`, `audit.py tokens`) — deterministic lint plus a routing/rewrite pass per skill.
4. **Eval gate** — before/after scenario scoring; a rewrite ships only at ≥0.8 and ≥ its own before-score.
5. **Apply and report** (`apply.py`, dry-run by default) — backup, write/disable on confirmed decisions only, report with exact undo commands.

Invariants: Anthropic-shipped skills are never edited; disabling means moving
a skill to a sibling `_disabled/`, never deleting; missing usage evidence
yields `unknown`, never `never`; every write is backed up first.

See `skill-optimizer/SKILL.md` for the full spec.
