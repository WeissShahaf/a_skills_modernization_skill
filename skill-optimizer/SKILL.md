---
name: skill-optimizer
description: Audits, classifies, and rewrites Claude skills across Claude Code (personal and project), plugin, and account/Cowork surfaces, using real usage evidence from session transcripts, history, and user confirmation, then proposes model/effort routing and applies reversible fixes. Use when the user asks to audit, clean up, optimize, slim down, or route their skills, asks which skills are unused or worth disabling, or asks what a skill costs in always-loaded tokens. Not for authoring a new skill from scratch — use skill-creator.
model: claude-opus-5
effort: high
---

# Skill Optimizer

This skill inventories every skill on the machine and account, classifies each one against real usage evidence, proposes a `model:`/`effort:` routing per skill, rewrites the keepers, proves the rewrite with a paired eval, and applies the result reversibly. One decision gate sits between evidence and action; nothing is written before it.

Complexity contract: expect 10–30 minutes depending on skill count, since every rewritten skill costs six eval runs. It needs connected folders for an in-place audit; on a surface without access it still works metadata-only — inventory and links, no findings and no rewrite.

Scope check before Phase 0: a request to write a new skill from scratch, or to improve one skill the user is drafting rather than one already installed, belongs to `skill-creator` — say so and stop, since this skill's evidence and eval machinery has nothing to measure until the skill is installed and used.

## Invariants

- Anthropic-shipped skills are inventoried and linked to, and are not edited, disabled, or given findings — they are not the user's to change and a rewrite would be lost on their next update.
- Disable means moving a skill folder to a sibling `_disabled/`. Nothing is deleted, so every action in the run has a one-line undo.
- No evidence means `unknown`, not `never`. A skill earns `never` only when the source that would have seen it was running for the whole window being judged; anything else is missing data, and missing data goes to the user.
- Every class and every routing decision traces to a log line, a command output, or a recorded user answer, quoted. A decision with no signal is reported as "insufficient signal" rather than guessed.
- Every write is preceded by a byte-verified backup, and `apply.py` is dry-run unless told otherwise, so a wrong call costs a re-run rather than a file.
- The optimizer's own files live in `C:/ProgramData/uv_envs/skill_optimizer/skill-optimizer/` — every `references/…` and `scripts/…` path in this file is relative to that folder, and the account copy of this skill carries only this file, so connect that folder before Phase 0. Runs and backups go to `C:/ProgramData/uv_envs/skill_optimizer/runs/`. Scripts run only as `uv run scripts/audit.py <cmd>` or `uv run scripts/apply.py` from the skill folder — one invocation form that holds on every shell.

## Phases

| Phase | What happens | Commands | Load | Artifact |
|---|---|---|---|---|
| 0 — Scope | Ask once for the folders to read and write: personal skills, each project's `.claude/skills`, the plugin cache and `~/.claude/projects` read-only, and the skill_optimizer folder. A surface not granted is reported as `not audited: no access` and is not reached by another route. The ready-to-paste ask is in `references/evidence-and-apply.md`. | — | `references/evidence-and-apply.md` | granted-surface list |
| 1 — Inventory + evidence | Walk the granted surfaces, record each skill's path, writability, frontmatter, size, and token estimates, then attach invocation evidence and a deterministic class proposal. | `uv run scripts/audit.py inventory`, then `uv run scripts/audit.py usage --inventory <path>` | same file | `runs/<run-id>/inventory.json` |
| 2 — Decision gate | Put common, rare, never, and unknown in one table — skill, class, evidence line quoted, proposed action — and take one answer for the whole table. One gate per run keeps a machine with dozens of skills from becoming dozens of questions. When the user is describing skills or asking what is wrong with them, this is where the run ends: deliver the assessment and stop. Applying anything needs the recorded yes. | — | same file | `decisions.json`, `user_confirmed: true` |
| 3 — Audit, route, rewrite | Deterministic rules run first; an `auditor` subagent per skill triages the findings, picks the routing row, and rewrites the body for that target. | `uv run scripts/audit.py lint --inventory <path>`, `uv run scripts/audit.py tokens --inventory <path> --api` | `references/audit-checklist.md`, then `references/routing-and-rewrite.md` | `diffs/<skill-id>.patch` |
| 4 — Eval gate | An `evaluator` subagent scores each skill before and after on the same scenarios. A rewrite ships at 0.8 or above and no lower than its own before-score — the threshold the skillgrade convention uses, and the second half is what stops a rewrite that scores well in the abstract but worse than what it replaced. | — | — | eval rows for `report.md` |
| 5 — Apply and report | Back up, dry-run, apply on the recorded yes, then write the report. `apply.py` defaults to a dry run, takes `--apply` only with a recorded confirmation, copies each file to `backups/<timestamp>/` and checks the byte count before touching anything, moves disabled skills to a sibling `_disabled/`, and prints the undo commands it just made necessary, including `--undo <backup-dir>`. | `uv run scripts/apply.py` (dry run), `uv run scripts/apply.py --apply` | `references/evidence-and-apply.md` | `report.md`, `backups/<timestamp>/` |

## Subagents

Two, both `claude-sonnet-5` at `medium` — their work is bounded and mechanical, and the routing table puts that shape on Sonnet. Their ready-to-paste instructions are `references/auditor-brief.md` and `references/evaluator-brief.md`; fill in the skill name and the run's paths, and keep the routing already decided for that skill in the brief rather than leaving it to the subagent. After editing this skill itself, `references/self-eval-brief.md` re-runs its three-slot regression the same way.

**auditor** — one call per skill. It receives the skill path, that skill's decision record, and the `name` plus `description` of every sibling skill, because graph links are derived from description overlap and cannot be inferred from a skill read alone. It loads `references/audit-checklist.md` for the severity model and the J1–J9 judgment checks, then `references/routing-and-rewrite.md` for the routing row and the per-target rewrite deltas, and invokes the user's `modernize-prompt` skill for the seven core rewrite rules, which are not restated here or in either reference. It returns 2k tokens or less: findings triage, one routing line with its quoted signal, and a diff summary — enough to decide on, small enough that a machine full of skills still fits in one orchestrating context.

**evaluator** — fresh context, no sight of the rewrite's rationale. It builds three scenarios from the skill's own description, two that should trigger it and one that should not, runs the original and the rewritten skill on each, scores 0–1 against a rubric, and returns 2k tokens or less. Three scenarios times two arms times one trial is six runs per skill, which is the cost the gate is worth; `smoke-5` is available when the user wants more confidence on one skill.

This orchestrator runs on Opus 5 at high effort because its own job is the planning/judgment row of the rubric it applies: it reads evidence, picks routing, and decides what reaches a user's files. It carries no self-verification instructions, for the reason the Opus 5 rewrite delta gives — the model already over-verifies, and the real check here is the fresh-context evaluator rather than a second look by the same context.

## Report

`report.md` opens with what changed and what needs the user before any table, so consequences are read before mechanism, and ends with the exact undo commands, so the way back is easy to find without reading everything above it. Between those: the confirmed decisions table, L1 and L2 token totals before and after, the eval table, and the settings suggestions (the usage-log hook, transcript retention, a `fallbackModel` for cyber- or bio-adjacent skills), each offered and none applied.

Token numbers are estimates: chars/4, labelled as estimates. With an API key present, `audit.py tokens --api` replaces them with `count_tokens` figures. The report states which method produced the numbers it shows, since the two are not interchangeable and a reader comparing runs needs to know which they have.

## Done

- Every skill has a class and an action, each traceable to a log line, command output, or recorded user answer.
- Every rewritten skill scores 0.8 or better on its paired eval and no lower than its own before-score.
- Total always-loaded (L1) footprint is stated as a number before and after, rather than described as reduced.
- Every write is reversible: the backup exists, `_disabled/` moves are moves, and `report.md` ends with the commands that undo the run.

## Surfaces and apply paths

| Surface | Apply path |
|---|---|
| Claude Code personal and project | write in place after backup; disable by moving to a sibling `_disabled/` |
| Account/Cowork skills in the skill_optimizer folder | write in place after backup; the report reminds the user to re-upload the changed skill and to toggle a disabled one off in claude.ai settings, since the folder does not sync on its own |
| Plugin skills, local marketplace | write in place after backup, same as personal |
| Plugin skills, remote marketplace | create a shadow personal skill of the same name under `~/.claude/skills/`; the plugin cache itself is left alone and the plugin skill is disabled through `enabledPlugins` |
| Anthropic-official | inventory and one-way links only |
