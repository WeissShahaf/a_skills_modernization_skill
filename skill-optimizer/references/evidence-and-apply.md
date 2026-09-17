# Evidence and Apply

Load when: gathering usage evidence, classifying skills, or applying/undoing changes.
Keywords: usage evidence, classification, decision gate, apply, rollback, _disabled

## Contents
- [Evidence sources](#evidence-sources)
- [Coverage and the anti-fabrication rule](#coverage-and-the-anti-fabrication-rule)
- [Classification](#classification)
- [The single decision gate](#the-single-decision-gate)
- [Getting real evidence next time](#getting-real-evidence-next-time)
- [Apply paths by surface](#apply-paths-by-surface)
- [Backup, dry-run, undo](#backup-dry-run-undo)
- [Report skeleton](#report-skeleton)

## Evidence sources

| Source | Proves | Cannot prove | How to obtain it | audit.py flag |
|---|---|---|---|---|
| Claude Code transcripts (`~/.claude/projects/**/*.jsonl`) | a Skill tool call happened, with a timestamp and a project cwd | Cowork/account usage, or anything from before transcript retention purged the file | point `usage` at the projects directory | `usage --projects DIR` |
| `~/.claude/history.jsonl` | a typed slash-command invocation, with a timestamp and a project | a skill invoked through the Skill tool rather than typed as a slash command; coverage here is thin by design | point `usage` at the file | `usage --history FILE` |
| `~/.claude/stats-cache.json` | overall session activity existed in the window | which skill any of that activity belongs to | read it yourself; audit.py does not parse it | none — a denominator only |
| the optimizer's own usage log (a PostToolUse hook) | a Skill invocation after the hook was installed | anything from before the hook was installed | install the hook (below), then point `usage` at the log | `usage --usage-log FILE` |
| a pasted `/context` output | the live L1 token footprint of skills loaded in the current session | how often a skill gets used | ask the user to paste it | none — feeds the report's token section only |
| a pasted `/usage` output | aggregate account activity or cost | which skill produced it | ask the user to paste it | none — a denominator only |
| user confirmation | whatever the user states about their own usage | nothing beyond what they say | ask, in the single decision gate | none — recorded in `decisions.json`, not `inventory.json` |

Matching evidence to an inventory skill is case-insensitive on the skill's directory name or its frontmatter `name`, and also accepts a `plugin:name` or `anthropic-skills:name` form by matching the part after the last colon. Evidence that names a skill outside the inventory is never dropped silently — it is collected under `coverage.unmatched_skills` (name to count) so a mismatch stays visible instead of vanishing.

State this plainly when reporting evidence: a `/context` or `/usage` paste never moves a skill out of `unknown` by itself, since neither is per-skill history, and account/Cowork skills are invisible to every machine source above — only user confirmation can classify them.

## Coverage and the anti-fabrication rule

"Covers the window" is a specific, checkable claim, not an impression: `usage` treats a source as covering the window when it is present and its earliest recorded timestamp falls on or before the window's start (`window_start` = now minus `--window-days`). Anything short of that is a partial view, and the run records exactly how many days it did cover, so the gap is visible instead of assumed away.

On a first run this partial view is the normal case, not a bug. Claude Code's own transcript retention (`cleanupPeriodDays`) defaults to keeping roughly the last 30 days, while the classification window defaults to 90 days, so a fresh 90-day window is usually only partly covered by transcripts — most skills land in `unknown` rather than `never`, and that is the correct outcome, not a shortfall to work around.

The rule that follows: no evidence means `unknown`, never `never`. A skill only earns `never` once the source that would have seen it — transcripts, for surfaces they can see at all — was both present and running for the whole window it is being judged against.

## Classification

`usage` computes a deterministic `class_proposal` per skill from the invocation counts inside its window; the orchestrator and the user still own the final `class`, decided at the gate below.

| Class | Rule | Why |
|---|---|---|
| common | invocations ≥ `--common-min` (default 5) in the window, or invocations_recent ≥ `--recent-min` (default 2) in the last `--recent-days` (default 30) | a skill used recently counts even when its lifetime total is small — recency predicts continued use better than a stale total does |
| rare | at least one invocation, below the common threshold | used, but too infrequently for an automatic yes; worth a judgment call |
| never | no invocations in the window, on a surface transcripts can see (`claude-code-personal`, `claude-code-project`, `plugin`), with transcripts present and covering the window | absence is only informative once the sensor that would have caught use was actually running for the whole period being judged |
| unknown | everything else — no invocations on `account`/`anthropic-official` surfaces, or no invocations with no transcripts at all, or transcripts that do not cover the window | the machine sources cannot see this surface, or cannot see far back enough, so the honest answer is "no data", not "no use" |

These defaults come from `usage --window-days 90 --recent-days 30 --common-min 5 --recent-min 2`, are user-adjustable per run, and whatever values were actually used are recorded in `coverage.thresholds` so the report can quote them rather than assume them.

Alongside the window count, each skill also carries `invocations_all_time` (every match, regardless of window) and up to 20 evidence items, most recent first, in `usage.evidence[]` — capped at 20 so the JSON stays bounded without losing the lines most likely to matter, the most recent ones.

Each skill's `class_basis` is one sentence naming the real numbers and the source, in the shape the script writes it — as a hypothetical illustration only, not a real measurement: "7 transcript invocations in 90 days, 3 in last 30 days (transcripts: 42 files, 61 days covered)". Quote a skill's actual `class_basis` verbatim at the decision gate rather than paraphrasing it. The lint findings that inform whether a skill is worth optimizing come from a separate pass — see `references/audit-checklist.md` for the rule ids — and stand apart from the usage evidence classified here.

## The single decision gate

`rare`, `never`, and `unknown` skills are never auto-classified past a proposal. They go to the user in one batched table, grouped common → rare → never → unknown, with one answer covering the whole table:

| Skill | Class | Evidence line | Proposed action | Your call |
|---|---|---|---|---|
| skill id | `class_proposal` | `class_basis`, quoted | optimize / disable / leave | user fills in or confirms |

Ready to paste for the question itself:

> Here is what the evidence shows for each skill. Common skills move straight to optimize; the rest need your call — reply "optimize", "disable", or "leave" per row (or "all optimize except the last two"), and I'll record it.

The confirmed table is written to `decisions.json` with `user_confirmed: true` and `confirmed_at` set to when that answer came in; nothing downstream reads a class that was not confirmed this way.

Keep this to one gate per run. Grouping common first and unknown last, rather than asking skill by skill, is what keeps a machine with dozens of skills from turning into dozens of separate questions.

## Getting real evidence next time

The most reliable fix for a mostly-`unknown` first run is real usage evidence at the source: a `PostToolUse` hook that appends one line per Skill invocation to the optimizer's own usage log, so the next run has `usage --usage-log FILE` evidence that never depended on transcript retention. Offer the exact snippet below, with an absolute, forward-slashed path to the script — a relative path breaks as soon as the hook runs from a different working directory:

```json
{"hooks": {"PostToolUse": [{"matcher": "Skill", "hooks": [{"type": "command", "command": "uv run <skill-root>/scripts/audit.py log-usage"}]}]}}
```

Installing this is a user action: show the snippet in the report, get a yes, and only then write it into `~/.claude/settings.json` — never as a silent edit alongside everything else that changed.

The second, complementary suggestion is lengthening transcript retention so a future window is actually covered by transcripts too:

```json
{"cleanupPeriodDays": 90}
```

90 is suggested because it matches the classification window's own default, so the two numbers agree instead of one silently trailing the other. Like the hook, this is a settings suggestion in the report, never a change the optimizer makes on its own.

## Apply paths by surface

| Surface | In place? | Disable | Notes |
|---|---|---|---|
| `claude-code-personal` / `claude-code-project` | yes, write in place after backup | move to a sibling `_disabled/` folder | ordinary reversible edit |
| `account` | yes — the user's account-skill source folder is itself a writable root | move to a sibling `_disabled/` folder | the report reminds the user to re-upload the changed skill, since the account surface does not sync on its own, and to toggle a disabled skill off in claude.ai skill settings, since the folder move alone leaves the live copy active |
| `plugin`, local marketplace | yes, write in place | move to a sibling `_disabled/` folder | only when the marketplace itself lives on disk under the user's control |
| `plugin`, remote marketplace | no | disable through `enabledPlugins`, not a file move | create a shadow personal skill of the same name under `~/.claude/skills/<name>/` instead; the plugin cache itself is never edited |
| `anthropic-official` | never | never | inventory and links only — no findings, no rewrite, no write of any kind |

`readonly_reason` takes one of: `anthropic-official`, `plugin-remote`, `account-not-on-disk`, `filesystem` — the last covers a nominally writable skill whose `SKILL.md` the filesystem itself denies write access to. The model/effort routing a writable skill's rewrite gets lives in `references/routing-and-rewrite.md`; the rewrite itself starts from the `modernize-prompt` skill's core rules before layering the model-specific deltas on top.

## Backup, dry-run, undo

Every write is preceded by a byte copy under `backups/<timestamp>/<id>/…`, and the copy's size is checked against the original before anything else is touched — a mismatched copy blocks the write rather than proceeding on faith.

`apply.py` (built in step 6; its own flags belong to that step, not this file) is the tool the orchestrator relies on for the write itself, on this contract: dry-run is the default action, a real write needs an explicit `--apply` flag, and reverting a run needs an explicit `--undo <backup-dir>`. Nothing the optimizer does skips the dry-run step silently.

`report.md` ends with an undo section built on that same contract: the preferred form is a single `uv run scripts/apply.py --undo <backup-dir>` line, with an equivalent copy-back command per changed file and a move-back command per `_disabled/` move given for both a POSIX shell and PowerShell, in case `apply.py` itself is unavailable. The invariant underneath all of it: nothing is ever deleted, so every one of these commands is a copy or a move, never a removal.

## Report skeleton

`report.md` follows this order, so the user reads consequences before mechanism:

1. What changed / what needs you first — the short version, ahead of any table.
2. Decisions table — the confirmed rows from the single decision gate.
3. Token totals — L1 and L2, before and after, with the method stated (`chars/4` or `api:count_tokens`).
4. Eval table — before/after score and verdict per rewritten skill.
5. Settings suggestions — the usage-log hook, the `cleanupPeriodDays` value, and a `fallbackModel` (for example `claude-opus-4-8`) for any cyber- or bio-adjacent skill, each offered, none applied silently.
6. Undo — last, so it stays easy to find without reading everything above it.
