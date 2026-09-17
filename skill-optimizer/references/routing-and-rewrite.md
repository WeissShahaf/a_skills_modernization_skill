# Routing and Rewrite

Load when: Phase 3, after the lint findings are triaged — setting `model:`/`effort:`/`inherit:` on a skill and rewriting its body for that target. J7 in `references/audit-checklist.md` is the hook into this file.
Keywords: model routing, effort level, inherit, rewrite deltas, per-model prompting

## Contents
- [How this file is used](#how-this-file-is-used)
- [Routing table](#routing-table)
- [Reading the signals](#reading-the-signals)
- [Escalation and de-escalation](#escalation-and-de-escalation)
- [inherit and in-body model branches](#inherit-and-in-body-model-branches)
- [Justification format](#justification-format)
- [Rewrite deltas by target](#rewrite-deltas-by-target)
- [Composing with modernize-prompt](#composing-with-modernize-prompt)
- [Settings recommendations, not skill edits](#settings-recommendations-not-skill-edits)
- [Output contract](#output-contract)

## How this file is used

`references/audit-checklist.md` owns the lint rules, the severity model and the J1–J9 judgment checks; none of that is repeated here. The rewrite itself is the user's `modernize-prompt` skill — invoke it for the 7 rules and layer only the deltas below on top. The 7 rules are not restated here either; changes cite them by number.

Route first, rewrite second: the deltas are per-target, so the body cannot be rewritten until the target is chosen. A skill file can set `model:`, `effort:` and `inherit:` and nothing else about the model.

## Routing table

| Task type | Signals in the skill | `model:` | `effort:` | Body notes |
|---|---|---|---|---|
| Planning, architecture, judgment | produces a plan, a design, or a decision someone acts on; "decide", "design", "trade-off", "which approach" | `claude-opus-5` | `high`; `xhigh` for long-horizon work past ~30 min | state scope explicitly, bound subagent use, drop self-verification lines, state expected length |
| Same, where Opus 5 is unavailable, or a benign cyber/bio fallback target | admin `availableModels` excludes Opus 5, or the skill's subject matter draws `cyber`/`bio` refusals | `claude-opus-4-8` | `xhigh` | same notes; thinking is off by default here, so raise effort rather than adding think-first prose |
| Plan-then-execute inside one skill | a distinct planning stage followed by mechanical application | `opusplan` | leave unset — each stage takes its own default | plan stage per the Opus 5 row, execution stage per the Sonnet 5 row |
| Routine execution, subagent workers, file transforms | "run", "generate", "apply", "convert", "for each"; bounded input, fixed output shape | `claude-sonnet-5` | `medium` (docs default is `high`; `medium` is the cost step taken after evals hold) | literal and explicit; leave no scope to inference |
| Trivial lookup, formatting, extraction, fixed-list classification | single step, deterministic shape, high volume, no judgment | `claude-haiku-4-5` | omit the field — Haiku 4.5 has no effort parameter (FM-011 is an error) | more guidance than larger targets need; body plus named references sized for 200k context |
| Project reference ("how this repo does X") | fact-dense conventions, API surface, pitfalls, version notes; the caller uses the facts inside its own task | `inherit: true`, no `model:` | omit | rewrite to the Sonnet 5 delta set as the floor, because the caller can be any tier |
| Hardest long-horizon reasoning, or review of a plan another model produced | explicit user opt-in at the decision gate, or the skill names Fable itself — the word "audit" does not fire this row | `claude-fable-5-1` | `high`; `xhigh` when capability-sensitive | no caps, no enumerations where a sentence works, no request to reproduce its reasoning |

The project-reference row exists because a reference skill contributes facts to a task whose model was already chosen. Pinning one would either force a model switch for a lookup or contradict the caller's own routing, so `inherit: true` records the choice deliberately instead of leaving FM-012 silent. A reference skill that also owns a procedure the user invokes directly ("repair this file") routes to the Sonnet 5 row instead.

## Reading the signals

Read the description first, then the body, and take the signal from what the skill *does*, not from what its subject sounds like.

- **Verbs.** decide / design / weigh / choose between → judgment rows. run / generate / apply / convert / for each → execution row. look up / format / extract / classify into a fixed list → trivial row. conventions / API surface / pitfalls / "in this repo" → reference row.
- **Output.** A plan or recommendation someone acts on → judgment. A file, a patch, a table of fixed shape → execution. One fact or flag value → trivial. Facts the caller folds into its own work → reference.
- **Tool-call count.** Count the named tools, scripts and commands a single run would issue. Under about five bounded calls sits at the execution row or below; more than twenty, or an unbounded loop ("for each session", "until it passes"), pushes to a judgment row and triggers escalation.
- **Destructive writes.** In-place writes, deletes, moves, force-pushes, or long external runs hold the skill at the execution row or above, whatever the verb count says, and keep their checkpoint language through the rewrite.
- **Judgment vs lookup.** If two competent readers could answer differently from the same body, it is judgment. If the body already holds the answer and the job is finding it, it is lookup or reference.

## Escalation and de-escalation

- Raise one effort level when the skill's own cost line or an observed run passes ~30 minutes or ~20 tool calls, or when an eval transcript shows under-thinking — a step skipped, or a fact asserted without the tool call that would establish it.
- Lower one level when the skill is high-volume and the paired eval still clears the gate (after ≥ 0.8 and after ≥ before) at the lower level. Lower it after the eval, not before it.
- The Haiku row has no level to move: escalating there means moving to the Sonnet 5 row, and de-escalating into it means dropping the `effort:` field.
- Record the level shipped, the level it moved from, and the trigger, in the same sentence as the routing justification.

## inherit and in-body model branches

`inherit: true` fits a skill that adds no model requirement of its own: a thin wrapper around another skill or a script, and a project reference whose facts the caller consumes inside an already-routed task. It says the caller decides, which is a different claim from an absent `model:` line.

An in-body branch addressed to a model class ("If you are a smaller model (Haiku-class)…") is resolved rather than kept. Such a branch asks the model to self-identify a class it has no reliable way to read, and it charges every reader the tokens of a section most of them skip. Resolve it in one move: fold whatever the branch adds that the body does not already say into the main text as plain instruction — that explicitness is the Haiku delta anyway, and it costs the larger targets little — then delete the branch as duplication and set the model contract in frontmatter, where the model is actually decided. A skill that genuinely runs on any tier gets `inherit: true` and still loses the branch.

## Justification format

Each routing decision is two fields in `decisions.json`, written together:

- `routing_signal` — the words or lines from the skill that fired the row, quoted. Not a paraphrase, because the next auditor re-checks it against the file.
- `routing_justification` — one sentence naming that signal and the row it selected, plus the escalation trigger when one applied.

A decision with no signal is not written. The skill keeps its FM-012 finding open and goes to the user at the decision gate as "routing: insufficient signal", which is a reportable state, not a failure.

## Rewrite deltas by target

Delta slugs are the ids the change lines cite.

**Opus 5** — `O5-scope`: state the scope explicitly, since it follows instructions literally and does not generalize an unstated boundary. `O5-subagents`: say how many subagents and for what, because it delegates readily. `O5-selfcheck`: remove self-verification lines; it over-verifies already, and a runnable check belongs in the skill instead. `O5-length`: state the expected length of the output — effort does not reliably shorten it.

**Sonnet 5** — `S5-literal`: literal, explicit instructions; every scope boundary written down rather than implied. Output is shorter by default, so a skill that needs a fuller answer says so.

**Haiku 4.5** — `H45-guidance`: more guidance and more explicit steps than the larger targets need. `H45-noeffort`: remove any `effort:` field. `H45-context`: 200k context against the 1M of the other targets, so the body and every reference it names stay small enough to sit beside a live working session.

**Fable 5.1** — `F51-caps`: drop capitals and hard rules; a brief instruction with its reason replaces an enumeration where a sentence works. `F51-checkpoint`: keep checkpoints for irreversible or destructive actions and remove the rest. `F51-reasoning`: remove any request to show, explain or reproduce its reasoning — that draws a `reasoning_extraction` refusal, which returns empty content and reads as a skill that quietly produced nothing. `F51-reporting`: it writes fewer progress updates and formats less, so a skill whose output contract needs a table or a running status asks for it explicitly.

**Universal** — `U-knobs`: remove `budget_tokens`, `temperature`, `top_p` and prefill references (BODY-006); current models reject them and a skill file cannot set them. `U-rituals`: remove "think step by step", "show your reasoning", "double-check" and "verify with a subagent" (BODY-005). Both leave quoted bad examples intact: a demonstration of what not to write is content, and the checklist's known-false-positive shapes already cover those hits.

## Composing with modernize-prompt

Run `modernize-prompt` first and the deltas second. Its 7 rules are model-independent — they hold whatever the routing decided — and the deltas only sharpen a rule for one target, so applying them in the other order produces a rewrite that the rules then flatten back out. Where they touch the same line, the rule decides the shape and the delta decides the wording: rule 4 turns a capitalised prohibition into a behaviour with a reason, and `F51-caps` is why that line matters more on a Fable-routed skill than elsewhere. The diff lists both ids on that line, so a reviewer can see which change came from the rule set and which from the target.

## Settings recommendations, not skill edits

These belong in `report.md` as settings suggestions the user applies. A skill file cannot set any of them, and text inside a skill telling the model to set one is an instruction it cannot act on — said once here, and not repeated in any rewritten body.

- Cyber- or bio-adjacent skills: suggest a `fallbackModel` (for example `claude-opus-4-8`) so a refusal — HTTP 200, `stop_reason: refusal`, empty content — does not surface as an empty answer.
- Fable 5.1 in long agent loops: the parallel-tool reminder is re-sent each tool round by the harness, so it is a harness concern and not a line in the skill.
- Per-model effort defaults: settings `modelSettings.<model-id>.effortLevel`, the global `effortLevel`, and the admin `maxEffortLevel` cap.
- Evidence for the next run: transcript retention (`cleanupPeriodDays`) and the `PostToolUse` usage-log hook.

## Output contract

The rewrite returns, per skill:

1. The rewritten files — in place for a writable surface, or under `out/<skill>/` when the surface is read-only.
2. A unified diff at `diffs/<skill-id>.patch`, original → rewritten.
3. One line per change: *what changed — why — rule/delta id*, where the id is a `modernize-prompt` rule number (rule 1–7), a lint rule id (`FM-*`, `BODY-*`, `REF-*`, `FILE-*`, `SCRIPT-*`), or a delta slug from the section above.
4. The routing decision as `routing_signal` and `routing_justification`, in the shape given above.
5. Anything that could not be changed because the surface is read-only, listed as a recommendation rather than dropped silently.
