# PLAN — skill-optimizer (v2, reviewed)

Drafted by Opus 5 (xhigh), reviewed by Fable 5.1 (high), written by Sonnet 5; source facts in `reference_notes.md`.

Discovery for this draft read outside the allowed folder; every path below is generic and discovered at runtime after the user grants access (Phase 0).

---

## 1. Goal and definition of done

### What the user gets
Say "audit my skills" (or `/skill-optimizer`) and get, without further prompting until a single decision gate: a complete inventory of every skill on the machine and account, each classified common / rare / never / unknown with the evidence line that proves it, a proposed `model:` + `effort:` for the keepers, rewritten bodies that pass the lint checklist, and a reversible apply step. Nothing is written until the user says yes; nothing is ever deleted; Anthropic-shipped skills are read but never touched.

### Artifacts (per run, under `skill_optimizer/runs/<run-id>/`)
| Artifact | File | Content |
|---|---|---|
| Inventory | `inventory.json` | every skill found, source, path, writability, frontmatter, L1/L2 token estimate, embedded usage, embedded findings |
| Decisions | `decisions.json` | per skill: class, action, model, effort, justification, user-confirmed flag |
| Diffs | `diffs/<skill-id>.patch` | unified diff, original → rewritten |
| Backups | `backups/<timestamp>/` | byte copy of every file before any write |
| Rewritten account-skill copies | `out/<skill>/` | for skills not writable in place |
| Report | `report.md` | roll-up: evals, token deltas, undo commands |

### Done means
- Every skill has a class and an action, each traceable to a log line, a command output, or a recorded user answer. No skill is classified from impression.
- Every rewritten skill scores ≥ **0.8** on its paired eval and does not score below its own before-score.
- Total always-loaded (L1) token footprint is reported before and after; the run states the number, never claims "reduced" without it.
- Every write is reversible: backup exists, `_disabled/` moves are moves not deletions, `report.md` ends with exact undo commands.
- Anti-fabrication rule (always-loaded): no evidence → `unknown`, never `never`. `unknown` goes to the user.

---

## 2. Architecture

### 2.1 File tree
```
skill-optimizer/
  SKILL.md                              # L2 body, <150 lines
  references/
    audit-checklist.md                  # lint rules, §8-equivalent
    routing-and-rewrite.md              # routing table + rewrite deltas
    evidence-and-apply.md               # usage evidence, apply/rollback
  scripts/
    audit.py                            # subcommands: inventory | usage | lint | tokens
    apply.py                            # backup + write + _disabled/ moves, dry-run default
    pyproject.toml                      # uv project, stdlib + pyyaml only
```
Each `references/*.md` opens with "Load when… / keywords: …" (3–5 keywords). Files >100 lines get a TOC.

### 2.2 Description and complexity contract
Description (third person, what + when + negative trigger, ≤1024 chars):

> Audits, classifies, and rewrites Claude skills across Claude Code (personal and project), plugins, and account/Cowork surfaces, based on real usage evidence, and proposes model/effort routing and reversible fixes. Use when the user asks to audit, clean up, optimize, or route skills, or asks which skills are unused. Not for authoring a new skill from scratch — use skill-creator.

Complexity-contract line (in SKILL.md, always-loaded): expected runtime 10–30 min depending on skill count; needs connected folders for in-place audit; works metadata-only (inventory + links, no findings or rewrite) on surfaces without access.

### 2.3 Scope grant (Phase 0)
The optimizer reads and writes only folders the user has connected. Before Phase 1 it lists the folders it needs (personal skills, each project's `.claude/skills`, plugin cache read-only, `~/.claude/projects` read-only) and asks once. A surface that is not granted is reported as `not audited: no access`, never probed by another route.

Scope-grant message (ready to paste):
> To audit your skills I need read/write access to: (1) `~/.claude/skills/` (personal skills), (2) each project's `.claude/skills/` you want audited, (3) `~/.claude/plugins/` (read-only, for inventory), (4) `~/.claude/projects/` and `~/.claude/history.jsonl` (read-only, for usage evidence). Connect these folders, or tell me which to skip — skipped surfaces are inventoried by name only, never edited.

Scripts are invoked only as `uv run scripts/audit.py <cmd>` / `uv run scripts/apply.py` — no shell-specific syntax.

### 2.4 The optimizer's own routing
Orchestrator: `model: claude-opus-5`, `effort: high` (planning/judgment row of its own rubric). Subagents `auditor` and `evaluator`: `claude-sonnet-5`, `medium`. No self-check instructions in the orchestrator prompt — verification is the eval gate (fresh-context evaluator), not self-critique.

### 2.5 Subagents (two only)
| Subagent | Input | Returns (≤2k tokens) |
|---|---|---|
| `auditor` | one skill path + decision record | lint findings + routing decision + rewrite + diff, one skill per call |
| `evaluator` | before/after skill, 3 scenarios | score before, score after, verdict — fresh context, paired run |

`auditor` invokes the user's existing `modernize-prompt` skill for the 7 core rules and layers only the model-specific deltas from `references/routing-and-rewrite.md` on top. The optimizer's SKILL.md must not restate the 7 rules.

---

## 3. Runtime workflow — five phases

### Phase 0/1 — Scope grant, inventory, evidence
1. Scope-grant message (§2.3); proceed only on granted surfaces.
2. Walk surfaces:

| Surface | Path |
|---|---|
| Personal Claude Code skills | `~/.claude/skills/` |
| Project Claude Code skills | `<project>/.claude/skills/`; discover project roots from `~/.claude/history.jsonl` |
| Plugin skills | `~/.claude/plugins/marketplaces/<mp>/plugins/<plugin>/skills/` — read-only |
| Cowork / account skills | source folder `C:/ProgramData/uv_envs/skill_optimizer/<skill>/` (user-confirmed) — writable root; cross-check names against the in-session skill list; an account skill with no folder there is metadata-only |
| Anthropic official | any Anthropic-shipped skill or Cowork built-in with no user source — inventory + link only |

Record per skill: `id` (surface-qualified), path, source, `writable`, `readonly_reason`, frontmatter, body line count, L1/L2 token estimate.

3. Usage evidence:
- Session transcripts `~/.claude/projects/**/*.jsonl` — `tool_use` blocks with `name: "Skill"`.
- `~/.claude/history.jsonl` — slash-command invocations and project roots. Low coverage but real.
- `~/.claude/stats-cache.json` — activity denominator only, no per-skill breakdown.
- `/context` (user pastes output): used only to measure the live L1 footprint of loaded skills before/after. `/usage` (user pastes output): activity denominator only. Neither is per-skill evidence and neither can move a skill out of `unknown`.
- User confirmation for every skill with zero machine evidence and all account-only skills; one batched, grouped question.
- Optional: a `PostToolUse` hook (Skill tool → append `{ts, skill, project}` to `skill_optimizer/usage-log.jsonl`) offered in the final report as a way to get real evidence next run. Installing it is a user action, never done automatically.

```json
{"hooks": {"PostToolUse": [{"matcher": "Skill", "hooks": [{"type": "command", "command": "uv run scripts/audit.py log-usage"}]}]}}
```

### Phase 2 — Classify + single decision gate
Window default 90 days, stated in report.
- **common** — ≥5 invocations, or ≥2 in last 30 days (recency matters as much as count), or user-confirmed regular → optimize
- **rare** — 1–4 invocations → ask: optimize or disable
- **never** — 0 invocations and the evidence source covering it is intact → recommend disable
- **unknown** — 0 invocations, no usable evidence → ask; never auto-classified

Defaults, user-adjustable; with empty transcripts expect mostly `unknown`.

`unknown`, `rare`, and `never` are all asked in the **same single gate**: one table (skill, class, evidence line, proposed action), one user answer. Written to `decisions.json` with `user_confirmed: true`.

### Phase 3 — Audit, route, rewrite
`scripts/audit.py lint` runs deterministic checks (name ≤64 = dir name; description ≤1024, third person, ≥20 tokens; body <500 lines/<5k tokens; refs one level deep; refs >100 lines have TOC; no backslash paths; no README/CHANGELOG; no `budget_tokens`/`temperature`/prefill; `effort:` present on a Haiku-routed skill → finding; every reference file starts with "Load when… / keywords:" → finding if missing). `auditor` subagent judges description quality, core-vs-background split, example canonicality, and applies the routing table below, then rewrites.

**Routing table**
| Task type | Signals | `model:` | `effort:` | Body notes |
|---|---|---|---|---|
| Planning / architecture / judgment | produces plan/design/decision; "decide", "design", "trade-off" | `claude-opus-5` | `high` (`xhigh` for 30+ min long-horizon) | state scope explicitly, bound subagent use, remove self-checks, state expected length |
| Same, where Opus 5 unavailable, or benign cyber/bio fallback | — | `claude-opus-4-8` | `xhigh` | as above |
| Plan-then-execute in one skill | distinct plan stage then mechanical apply | `opusplan` | per-stage default | plan stage as above; execution stage as Sonnet row |
| Routine execution, subagent workers, file transforms | "run", "generate", "apply", "for each"; bounded | `claude-sonnet-5` | `medium` (docs default `high`; `medium` is the after-evals cost step) | literal, explicit, no scope inference |
| Trivial: lookup, formatting, extraction, fixed-list classification | single-step, deterministic shape, high volume | `claude-haiku-4-5` | omit — no `effort:` field | more guidance than for larger models; body explicit |
| Hardest long-horizon reasoning, or review of a plan produced by another model | user opts in, or the skill explicitly names Fable — never triggered by the word "audit" alone | `claude-fable-5-1` | `high` (`xhigh` if capability-sensitive) | no caps/ALWAYS/NEVER, no enumerations where a sentence works, never ask it to reproduce its reasoning |

Escalation: +1 level if >30 min, >20 tool calls, or observed under-thinking; −1 if high-volume and eval holds. `inherit: true` for thin wrappers. Every decision carries a one-sentence justification naming the signal.

**Rewrite deltas (body-level only)**
- Opus 5 → state scope, bound subagent use, remove self-verification instructions, state expected length.
- Sonnet 5 → shorter, more literal, explicit; no scope inference left implicit.
- Haiku 4.5 → more guidance than other models need; no `effort:` field.
- Fable 5.1 → strip caps/ALWAYS/NEVER; checkpoints only for irreversible actions; never instruct it to "show your reasoning" (triggers `reasoning_extraction` refusal).
- Universal → purge `budget_tokens`, `temperature`, prefill, "think step by step", "show your reasoning".
- Cyber/bio-adjacent skills → recommend a `fallbackModel` in Claude Code settings (e.g. `claude-opus-4-8`) in the report; this is a settings suggestion, not a skill-file edit.

**Graph:** links derived from description-keyword overlap + shared reference files + user confirmation (no co-occurrence data exists to mine). Same tree → relative path; other surface → link by skill name. Links to `anthropic-skills:*` are one-directional (referenced, not referencing back). Cap 2–3 linked skills per task.

### Phase 4 — Eval gate
3 scenarios per skill, generated from the skill's own description: 2 positive triggers + 1 negative trigger. Paired runs (original vs rewritten), 1 trial each, graded by a fresh-context `evaluator` subagent (no self-grading), rubric 0–1. Gate: after-score ≥ 0.8 AND after ≥ before. Else not applied; report the failing scenario. `smoke-5` (5 trials) is opt-in for higher confidence, not default. No 15/30-trial tiers. Record `*_tokens_est` delta (L1 and L2, before/after).

### Phase 5 — Apply and report
Apply path depends on surface:
- **Claude Code personal/project** — write in place; backup first; disable = move to sibling `_disabled/`.
- **Account/Cowork skills** — write rewritten copy to `skill_optimizer/out/<skill>/`; report instructs the user to re-upload it and, to disable the original, toggle it off in claude.ai skill settings.
- **Plugin skills** — write in place only if the plugin comes from a local marketplace; otherwise create a shadow personal skill of the same name and instruct the user to disable the plugin skill via `enabledPlugins`.
- **Anthropic-official** — inventory and links only; no findings, no recommendation, never written.

`readonly_reason` values: `anthropic-official | plugin-remote | account-not-on-disk`.

1. Backup to `backups/<timestamp>/`, verify byte counts.
2. `apply.py` dry-run by default; real write needs an explicit flag plus recorded confirmation.
3. `report.md`: what changed / what needs the user first, decisions table, token totals, eval table, undo section last.

---

## 4. Data contracts (field lists)

**`inventory.json`** — per skill: `id`, `source` (`claude-code-project|claude-code-personal|plugin|account|anthropic-official`), `path`, `name`, `dir_name_matches`, `description_chars`, `description_tokens_est`, `body_lines`, `l1_tokens_est`, `l2_tokens_est`, `references[]`, `scripts[]`, `frontmatter{description, model, effort, inherit}`, `writable`, `readonly_reason`, embedded `usage{invocations, last_used, confidence, evidence[], coverage_gap}`, embedded `findings[]{rule_id, severity, line, evidence, suggested_fix}`.

**`decisions.json`** — per skill: `id`, `class`, `class_basis` (pointer into `inventory.json`), `action` (`optimize|disable|leave|recommend-only`), `user_confirmed`, `confirmed_at`, `model`, `effort`, `inherit`, `routing_signal`, `routing_justification`, `readonly_block`.

**Evals + token deltas** live in `report.md`: per skill, scenarios with before/after score, verdict, `l1_tokens_est`/`l2_tokens_est` before/after.

Token fields: `*_tokens_est` = chars/4, upgraded to Anthropic's `count_tokens` if an API key is available; the report states which method was used.

---

## 5. Decisions (open questions resolved by the user, 2026-09-16)
1. **Usage evidence** — all three: install the `PostToolUse` usage-log hook (§3, Phase 0/1; the report shows the snippet and the user confirms before it is written to `~/.claude/settings.json`); accept a mostly user-confirmed first pass; and recommend lengthening transcript retention (`cleanupPeriodDays`) as a settings suggestion in the report.
2. **Account/Cowork skill source folder** — `C:/ProgramData/uv_envs/skill_optimizer` (already connected). Treated as a writable skills root: in-place rewrite with backup; `_disabled/` sibling for disable; report reminds the user to re-upload changed skills to their account. Plugin sources authored by the user live there too and are treated the same way.
3. **Eval cost** — 3 scenarios × 1 trial × 2 arms = 6 runs per skill; `smoke-5` opt-in.
4. **"Rare" threshold** — 1–4 uses in 90 days; common ≥5 or ≥2 in last 30 days. Defaults, user-adjustable per run.
5. **Plugin skills from remote marketplaces** — shadow with a personal skill of the same name under `~/.claude/skills/`; the plugin cache is never edited; the report lists each shadow created.
8. **Routing policy (user-confirmed 2026-09-16)** — project reference skills (fact sheets the caller reads) get `inherit: true` and no `effort:`; only skills that perform an action get a pinned model + effort. In-body "If you are a Haiku-class model" branches are resolved: new content folded into the main text, the rest deleted, contract in frontmatter.
7. **Example project usage (user-confirmed 2026-09-16)** — in `example_skills/cuniformNPX`: common = grepping, movement, sleap, spikeinterface, bombcell; rare = the other six. Recorded in `runs/cuniform-demo/decisions.json`.
6. **Folder scope** — the four categories in §2.3 plus the `skill_optimizer` folder are the scope-grant set; anything not granted is `not audited: no access`.

---

## 6. Implementation steps
| # | Step | Deliverable |
|---|---|---|
| 1 | ~~Resolve open questions §5~~ — done, see §5 | decisions recorded in PLAN.md §5 |
| 2 | ~~`scripts/audit.py` (inventory/usage/lint/tokens/log-usage) + `references/evidence-and-apply.md`~~ — done; verified on `example_skills/cuniformNPX` (11 skills; no-evidence → `unknown`; hook line → `rare` with pointer) | `runs/cuniform-demo/inventory.json` |
| 3 | ~~`references/audit-checklist.md`~~ — done; validated by a sonnet auditor on `modernize-prompt`, `sleap`, `bombcell` (report: `runs/cuniform-demo/step3-validation-report.md`); 10 gaps found, 4 fixed in `audit.py` (code-span caps, `ALWAYS/NEVER` mentions, file:line + year numbers, quoted BODY-007), 6 folded into the checklist | checklist + report |
| 4 | ~~`references/routing-and-rewrite.md`~~ — done (Opus 5, high); proved on the 5 common example skills + `modernize-prompt` (`runs/cuniform-demo/routing-worked-examples.md`). Adds a *project reference* row → `inherit: true` (user-confirmed) and the rule that in-body "Haiku-class" branches are folded into the main text and deleted (user-confirmed) | reference + worked examples |
| 5 | ~~`SKILL.md`~~ — done (Opus 5, high; 65 lines, ~2.2k tokens est.); self-lint clean except one info | SKILL.md + `runs/cuniform-demo/SKILL-self-check.md` |
| 6 | ~~`scripts/apply.py` + Phase 3/4/5 on the example project + self-evals~~ — done 2026-09-17. apply.py tested (unconfirmed → refused; write + `_disabled/` move + backup; `--undo`; relative-path manifest; per-backup undo.txt; re-run-safe skip of an already-disabled skill). `audit.py inventory` records `description` in the `frontmatter` block; tooling dirs (`.venv`, `__pycache__`, …) are skipped. Phase 3/4: 5 common (1.0→1.0) + 4 rare (catgt-tuner opus-5/high, consolidate-dreams opus-5/high, infographics sonnet-5/medium, dream inherit) all pass; two round-1 fails fixed and re-evaluated fresh. Applied in two backups (`20260917T081132Z`, `20260917T082826Z`); fable5-migration + opus5-migration disabled per user. L2 for the nine rewritten skills 28.9k→20.0k est. Optimizer self-evals: 3 slots pass (negative slot failed round 1 → scope-check paragraph added → pass); self-lint 0e/0w. Report: `runs/cuniform-demo/report.md` | apply.py, report.md, evals/, self-evals/ |
| 7 | Package `skill-optimizer/` as an account-skill proposal (`propose_skills`, full SKILL.md) | proposal card |

---

## 7. Lint checklist (reference content)
Frontmatter: `name` ≤64 chars = dir name, lowercase-hyphen; `description` ≤1024 chars, third person, what + when + negative trigger + unique identifiers, ≥20 tokens; `model:`/`effort:` present and justified; `effort:` on a Haiku-routed skill is a finding.
Body: <500 lines / <5k tokens; core rules are the majority of the body; background/examples/templates moved to refs with a "Load when… / keywords:" line (missing line = finding); numbered steps only where order matters; no caps/ALWAYS/NEVER shouting; no "show your reasoning"; no prefill/`budget_tokens`/`temperature` references; no time-sensitive info in main flow; no magic numbers without a comment; forward slashes only; consistent terminology; MCP tools referenced as `Server:tool`; scripts solve, don't defer; refs one level deep; refs >100 lines have a TOC; no README/CHANGELOG inside a skill.
Graph: related skills cross-linked by description-keyword overlap + shared refs + user confirmation; ≤2–3 skills active per task; Anthropic-official skills read-only, linked one-way.
Model routing: matches §3 Phase 3 table exactly; Fable row only on explicit opt-in or explicit naming, never on the word "audit".
Evals: 3 scenarios (2 positive + 1 negative from the skill's own description), paired before/after, 1 trial default, rubric 0–1, threshold 0.8, `smoke-5` opt-in.
