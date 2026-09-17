---
name: modernize-prompt
description: Rewrites a prompt, a SKILL.md, or a CLAUDE.md that was written for older models so it follows the 7 current Anthropic rules for Opus 5 and Fable 5. Keeps the goal, who it is for, and what done looks like; swaps NEVER/ALWAYS/MUST and capitals for positive instructions with a reason; drops step lists where order does not matter; removes the rituals (think out loud, show your reasoning, double-check); and routes voice and boundaries into the file that always loads. Use when the user asks to update, fix, modernise, or rewrite a prompt, a skill, or a CLAUDE.md, or says an old prompt got worse on the new models.
---

# Rewrite for Claude 5

## Overview
Prompts, skills, and CLAUDE.md files written before mid-2026 use patterns that now degrade output on Opus 5 and Fable 5. This skill reads the file, keeps what still holds, and applies the 7 current rules, returning the new version with a diff of what changed and why. The full rule map is in `references/rules.md`.

## When to use
- "rewrite this prompt", "update this skill", "modernise my CLAUDE.md", "this prompt got worse on the new models".
- Running it in batch across your most used skills and your CLAUDE.md.

## When NOT to use
- Writing a prompt from scratch with no source material. Use the rule 2 template directly instead.
- Files that are not instructions to the model (code, data).

## Workflow
1. Read the source material (a prompt, a `SKILL.md`, or a `CLAUDE.md`).
2. Preserve the three anchors: the goal, who it is for, and what done looks like. If one is missing, flag it in a single line.
3. Apply the 7 rules from `references/rules.md`, in order.
4. Route each change to the right place:
   - Task specific (the job, the why, the definition of done, a runnable check) stays in the prompt or the skill.
   - Global behaviour (the assess-and-stop boundary from rule 6, the voice from rule 7) goes into the file that always loads, the CLAUDE.md.
   - A scheduled task gets the opposite of rule 6: it operates autonomously and proceeds on reversible actions.
5. Return the rewritten version, then a tight diff below it: each removed or swapped line with the reason in one sentence.
6. Do not invent business context that is not in the source. If the why or the done cannot be inferred, ask instead of filling it in.

## Examples

Input:
"IMPORTANT: follow this process EXACTLY. Step 1... Step 6... Think carefully and walk me through your reasoning. ALWAYS include a table. NEVER mention competitors. Double-check every number before finishing."

Output (rewritten version, target shape):
"I'm working on [the larger task] for [who it is for]. They need [what the output enables]. With that in mind: [the job in one sentence]. Done means: [a measurable end state, and the length it needs]. Put the figures in a small table, because [reason]. Keep competitor names out, because [reason]."
Diff: step list removed (rule 1); "think / walk me through / double-check" removed (rule 5); ALWAYS/NEVER turned into an instruction with a reason (rule 4).

Input:
"rewrite my CLAUDE.md, it is full of 'no jargon' and 'sound professional' repeated in every skill"

Output:
Consolidate the voice into one paragraph at the top of the CLAUDE.md (rule 7), remove the copies scattered across the skills, and add the assess-and-stop boundary (rule 6). Diff showing each removed copy.
