# Audit Checklist

Load when: auditing a skill in Phase 3 — reading lint findings, judging what the script cannot, deciding what to change.
Keywords: lint rules, severity, description quality, core rules vs background, progressive disclosure, graph links

## Contents
- [How to use this file](#how-to-use-this-file)
- [Severity and what it means for apply](#severity-and-what-it-means-for-apply)
- [Deterministic rules (audit.py lint)](#deterministic-rules-auditpy-lint)
- [Judgment checks (the auditor, not the script)](#judgment-checks-the-auditor-not-the-script)
- [Progressive-disclosure split rules](#progressive-disclosure-split-rules)
- [Graph rules](#graph-rules)
- [Known false-positive shapes](#known-false-positive-shapes)
- [Sources](#sources)

## How to use this file

`audit.py lint` has already run and every finding sits in `inventory.json` under the skill's `findings[]` with a `rule_id`, `severity`, `line` and `evidence`. Do not re-derive those. Your job is the second column: read the body once, apply the judgment checks below, and for each finding (script or yours) write one line — keep / fix / not-applicable — with the reason. A finding you cannot trace to a line in the skill is dropped, not kept "to be safe". Whole-skill findings (`line: null` by construction — BODY-001, BODY-002, BODY-003, REF-*) trace to the file, not a line, and are kept.

Anthropic-shipped skills (`readonly_reason: anthropic-official`) are never audited: no findings, no suggestions, inventory and links only.

## Severity and what it means for apply

| Severity | Meaning | Effect |
|---|---|---|
| error | breaks discovery, loading or the model contract | the rewrite must clear it; `apply.py` refuses a writable skill that still has one |
| warn | measurable token or reliability cost | fix in the rewrite when it is cheap (a one-line edit, no restructuring); otherwise list it in the report |
| info | worth knowing, no action required | report only |

A skill with zero errors and zero warns after rewrite is "clean". Cleanliness is not the goal on its own — the eval gate (after ≥ 0.8 and ≥ before) decides whether the rewrite ships.

## Deterministic rules (audit.py lint)

Rule ids here are the ids `audit.py lint --list-rules` prints; keep the two lists identical when either changes.

| Rule | Sev | What it catches | Why (source) |
|---|---|---|---|
| FM-001 | error | no valid YAML frontmatter | name+description are the only routing surface (best-practices) |
| FM-002 | error | name missing, >64 chars, not `[a-z0-9-]`, or a reserved word (`anthropic`, `claude`) | best-practices frontmatter limits |
| FM-003 | error | name ≠ directory name | skills-best-practices: routing and loading key off the dir |
| FM-004 | error | description missing, >1024 chars, or contains XML tags | best-practices |
| FM-005 | warn | description under ~20 tokens | SkillReducer: 44% of wild skills fail routing on this alone |
| FM-006 | warn | description in first/second person | best-practices: third person only |
| FM-007 | info | no "use when" cue | description must say what AND when |
| FM-008 | info | no negative trigger | skills-best-practices: say what it is not for |
| FM-009 | warn | `model:` not a known id/alias | model-config: `fable`, `opus`, `sonnet`, `haiku`, `opusplan`, or a `claude-*` id |
| FM-010 | warn | `effort:` not low/medium/high/xhigh/max | effort docs |
| FM-011 | error | `effort:` on a Haiku-routed skill | Haiku 4.5 has no effort parameter |
| FM-012 | info | no `model:`/`effort:`/`inherit:` | actionable in Phase 3: J7 sets it; it is info only because it is not a defect of the skill text |
| BODY-001 | error | body ≥ 500 lines | best-practices hard limit |
| BODY-002 | warn | body ≥ 5,000 tokens (est.) | overview: L2 target < 5k tokens |
| BODY-003 | info | body ≥ 3,500 tokens (est.) | approaching the limit |
| BODY-004 | warn | ALWAYS / NEVER / MUST / CRITICAL / IMPORTANT / shouted caps | Fable & Opus guidance: over-emphasis over-triggers; modernize-prompt rule 4 |
| BODY-005 | error | ritual phrases: "think step by step", "double-check", "show your reasoning", "verify with a subagent" | Opus 5 over-verifies; Fable refuses reasoning extraction; rule 5 |
| BODY-006 | error | API knobs in a skill: `budget_tokens`, `temperature`, `top_p`, prefill | rejected with 400 on current models; a skill file cannot set them anyway |
| BODY-007 | warn | Windows/backslash path | best-practices anti-pattern; breaks on other surfaces |
| BODY-008 | warn | time-sensitive phrase ("until 2026-08-25", "currently broken") outside an *Old patterns* / history section | best-practices: keep it out of the main flow |
| BODY-009 | info | bare magic number with no stated reason | best-practices: comment the why |
| BODY-010 | warn | `mcp__server__tool` instead of `Server:tool` | best-practices MCP naming |
| REF-001 | error / warn | a `references/…` or `scripts/…` mention that does not exist (warn when the skill has no such folder at all — probably prose) | broken just-in-time load |
| REF-002 | error | reference nested >1 level under `references/` | best-practices: one level deep |
| REF-003 | warn | reference >100 lines with no table of contents | best-practices |
| REF-004 | warn | reference has no `Load when: … / Keywords: …` opening lines | SkillReducer: annotate when-to-load + keywords |
| REF-005 | info | reference never mentioned in SKILL.md | unreachable content |
| FILE-001 | warn | README / CHANGELOG / INSTALL inside the skill | skills-best-practices: no meta-docs in a skill |
| FILE-002 | info | file outside SKILL.md, scripts/, references/, templates/, assets/ | directory convention |
| SCRIPT-001 | info | `scripts/*.py` with no `main` / `__main__` guard | scripts should be runnable, single-purpose |

## Judgment checks (the auditor, not the script)

Answer each with a one-line verdict and, when the answer is no, a one-line fix.

**J1 — Would the description alone route correctly?** Cover the frontmatter's neighbours: name three requests the skill *should* fire on and one it should not. If the description would misfire on any, rewrite it as capability + trigger condition + unique identifiers (library names, file types, commands), roughly 20–40 tokens each (SkillReducer), third person, with the negative trigger.

**J2 — What share of the body is core rules?** Tag each paragraph (a fenced block or table counts as one paragraph) and weight by its `tokens_est` (chars/4) so two auditors land on the same number: core rule / background / example / template / redundant. Wild average is 38% core (SkillReducer); comprehensive bodies add +0.7 pp vs +21.5 pp for standard-length ones (SkillsBench). Everything that is not a core rule is a candidate for `references/` with a Load-when line, or for deletion if it restates what the model already knows.

**J3 — Are the examples canonical or exhaustive?** Two or three diverse, correct examples beat a catalogue. Examples that show a *bad* prompt on purpose are fine — mark them so BODY-004/005 hits inside them are not "fixed".

**J4 — Are the steps really ordered?** Numbered steps only where skipping or reordering breaks the result. Otherwise state the whole job and the definition of done (modernize-prompt rules 1 and 3).

**J5 — Is the terminology consistent?** One term per concept across SKILL.md and references (best-practices). List the drift pairs.

**J6 — Does the body say why?** Constraints without a reason are the ones that over-trigger or get ignored; add the reason or drop the constraint (rule 2, rule 4).

**J7 — Is the model contract right for the target?** After routing (see `routing-and-rewrite.md`): Opus 5 needs explicit scope and length and no self-check lines; Sonnet 5 needs literal, explicit instructions; Haiku 4.5 needs more guidance and no `effort:`; Fable needs no caps and no reasoning-extraction asks.

**J8 — Does anything here belong in CLAUDE.md instead?** Voice, "no jargon", the answer-vs-action boundary — once, in the always-loaded file, not in every skill (rules 6 and 7).

**J9 — Does the skill have a cost/fallback line?** Expected runtime or tool count, what it needs (env vars, connected folders, API keys), and what it does without them (SkillsBench "complexity contract"). Missing → add one line under the title, in this shape: *"Needs: a SortingAnalyzer with quality_metrics computed; UnitRefine downloads ~5 MB of models on first run. Without internet, BombCell-only path still works."*

## Progressive-disclosure split rules

- L1 = frontmatter only; aim ≈100 tokens. L2 = body; < 500 lines and < 5,000 tokens, ideally well under. L3 = `references/`, `scripts/`, `templates/`, `assets/`, one level deep, loaded only when named.
- Move out of the body: background and theory, API surface listings, migration notes, benchmarks, long examples, templates, anything conditional ("if using X…"). Keep in the body: the job, the definition of done, the invariants, the branch points, and the *when to load* pointer for each reference.
- Every reference opens with `Load when: …` then `Keywords: …` (3–5), then a TOC if it is over 100 lines.
- Scripts replace prose for anything mechanical or fragile (best-practices "solve, don't defer"); say "Run scripts/x.py to …", not "see scripts/x.py".
- Mutually exclusive contexts (two libraries, two OSes) go in separate references, never interleaved in the body.

## Graph rules

- Link candidates come from three signals only: description-keyword overlap, shared reference files, and the user's confirmation at the decision gate. No co-occurrence mining unless transcripts exist.
- The overlap signal needs the sibling descriptions: the orchestrator passes the auditor the `name` + `description` of every skill in the same tree (from `inventory.json`), not just the skill under audit. If they were not passed, link only on explicit in-body mentions and write "graph: insufficient signal" rather than guessing from names.
- Same skill tree → relative path (`../other-skill/SKILL.md`). Different surface → by skill name (`/name`, `plugin:name`). Anthropic-shipped skills are linked *to*, never edited to link back.
- A router line is one sentence at the point of hand-off: "For X, use `/other-skill` — it owns Y." Cap the set a single task pulls in at 2–3 skills (SkillsBench: 2–3 peaks at +19 pp, 4+ drops to +10 pp).
- Two skills that cover the same job on the same surface are a merge candidate, not a link candidate; propose the merge in the report and let the user decide.

## Known false-positive shapes

- BODY-004 / BODY-005 inside a quoted *bad* example — the script tags `[quoted example]` and lowers to info; do not fix.
- BODY-004 on caps joined by a slash (`ALWAYS/NEVER`) in a sentence *about* those words (a diff note, a rule description) — the script tags `[mentioned as words]`; do not fix.
- BODY-004 on an ALL-CAPS identifier in inline code or a fenced block (`` `EXTENSION_COMPUTE_DICT` ``) — the script strips code spans, so a hit here means the identifier is bare; wrap it in backticks rather than rewording.
- BODY-007 on a verbatim error string quoted for diagnosis (`'A:\\'`) — the script lowers it to info when the quote is on the same line; inside a multi-line code span it still fires as warn. Mark not-applicable; never "fix" a quoted error message.
- BODY-009 on `file.py:67` source citations and on years (`Nature Neuroscience 2024`) — the script skips both; if one still fires, not-applicable.
- REF-001 on prose that looks like a path (`scripts/servers`) in a skill with no `scripts/` folder — already downgraded to warn; reword or ignore.
- BODY-008 on a dated *verified on* line under an explicit history section — allowed.
- BODY-009 on a number that is a real constant of the domain (sample rate, channel count) — allowed if the reason is obvious from the noun next to it.

## Sources

Anthropic Agent Skills best practices and overview; skills-best-practices (mgechev); SkillReducer (arXiv 2603.29919); SkillsBench (arXiv 2602.12670); Prompting Claude Fable 5, Opus 5 migration guide, effort docs, Claude Code model-config. Full notes with links: `reference_notes.md` in the skill_optimizer folder.
