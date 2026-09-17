# Self-eval brief

Load when: running Phase 4 on the optimizer itself after editing its SKILL.md, references or scripts — one fresh-context evaluator per slot, three slots, no before-arm.
Keywords: self-eval, regression, skill-optimizer, evaluator, slot

You are the `evaluator` subagent: fresh context, medium effort, Read only plus one Write. You have not built this skill and must not read its plan (`PLAN*.md`), `reference_notes.md`, or anything under `runs/` except where this brief names a file.

Skill under test: /mnt/user-data/uploads/skill_optimizer/skill-optimizer/ — `SKILL.md`, `references/*.md`, `scripts/audit.py`, `scripts/apply.py`. There is no "before" arm: the skill is new, so you score a single arm against the threshold.

Your scenario slot is <slot>:
- `positive-no-evidence` — a user with Claude Code skills on a Windows machine asks which of their skills are unused and should be disabled, and their `~/.claude/projects` transcripts folder is empty (retention cleaned it).
- `positive-anthropic-and-apply` — a user asks the optimizer to slim down a bloated Anthropic-shipped skill (say `anthropic-skills:docx`) and one of their own project skills, and to "just apply it".
- `negative-authoring` — a user asks for a brand-new skill to be written from scratch for a library they use.

Procedure:
1. Read only the frontmatter `description` of SKILL.md. Write the concrete user request for your slot (2–4 sentences, realistic) and decide, from the description alone, whether the skill should fire. Fix that before reading the body.
2. Read the body and every reference the body points you to for this request. Then write, in 8–15 lines, what the skill would do for this request: which phases run, which commands are issued (quote them from the skill), what is asked of the user and when, what is written to disk and what is not, and how the run ends.
3. Score 0–1 as the mean of five sub-scores:
   - triggering: the description gives the right fire/no-fire decision for this request (1/0);
   - invariant fidelity: your step-2 account respects the skill's own invariants as the body states them — for your slot the ones that matter are: no evidence → `unknown`, never `never`, and `unknown` goes to the user; Anthropic-official skills are inventoried and linked, never edited or given findings; nothing is written before the recorded yes at the single decision gate, and `apply.py` is dry-run unless `--apply` is given (1 = every applicable invariant is what the body would make you do; 0.5 = one is ambiguous or you had to infer it; 0 = the body would let you break one);
   - pointer completeness: the body told you which reference or script to open for each step you needed, and it was there and said what the body promised (1/0.5/0);
   - script agreement: the commands the body quotes exist with those subcommands and flags in `scripts/audit.py` / `scripts/apply.py` (check `argparse` definitions by reading the files; 1 = all, 0.5 = one mismatch, 0 = more);
   - absence of fabrication: nothing in your account was invented beyond the folder (1/0).
   For the negative slot, sub-scores 2–4 are scored on whether the body tells you where to hand off instead (a named sibling skill counts as 1) rather than on phases.
4. List up to 5 concrete defects you found (a command that does not exist, a reference the body promises but that lacks the content, an invariant the body states but a reference contradicts, a missing negative trigger). Empty list if none.

Write /mnt/user-data/outputs/p5/<slot>.json exactly in this shape:
{"skill": "skill-optimizer", "slot": "<slot>", "kind": "positive|negative", "request": "...", "should_fire": true|false, "fires": true|false, "subscores": {"triggering": x, "invariant_fidelity": x, "pointer_completeness": x, "script_agreement": x, "no_fabrication": x}, "score": mean, "threshold": 0.8, "verdict": "pass|fail", "account": "your 8–15 line step-2 text", "defects": ["..."]}

Return ≤ 200 words: the five sub-scores, the score, the verdict, and the defects list.
