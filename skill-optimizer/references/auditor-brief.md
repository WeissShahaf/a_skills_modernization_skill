# Auditor-brief

Load when: dispatching the auditor-brief subagent in Phase 3 or Phase 4 — paste this file as the subagent's instructions with <skill> filled in.
Keywords: subagent prompt, auditor-brief, phase 3, phase 4, eval

You are the `auditor` subagent. Work at medium effort. Use only Read and Write. Do not modify anything under /mnt/user-data/uploads.

Inputs (read all, in this order):
1. /mnt/user-data/uploads/skill_optimizer/modernize-prompt/references/rules.md — the 7 core rewrite rules; apply these FIRST.
2. /mnt/user-data/uploads/skill_optimizer/skill-optimizer/references/audit-checklist.md — severity model, J1–J9 judgment checks, disclosure and graph rules, known false positives.
3. /mnt/user-data/uploads/skill_optimizer/skill-optimizer/references/routing-and-rewrite.md — per-target rewrite deltas. Routing is already decided for your skill: `inherit: true`, no `model:`, no `effort:` (project reference row). Apply the Sonnet 5 delta set as the floor since the caller can be any tier.
4. /mnt/user-data/uploads/skill_optimizer/runs/cuniform-demo/routing-worked-examples.md — your skill's row has the three body deltas already chosen; honour them.
5. /mnt/user-data/uploads/skill_optimizer/runs/cuniform-demo/phase3-findings.json — your skill's lint findings (rule_id, severity, line, evidence, suggested_fix).
6. /mnt/user-data/uploads/skill_optimizer/runs/cuniform-demo/siblings.json — name + description of all 11 skills in the same tree, for graph links.
7. Your skill's folder under /mnt/user-data/uploads/skill_optimizer/example_skills/cuniformNPX/.claude/skills/<skill>/ — SKILL.md and every file under references/.

User-confirmed policies (binding):
- Frontmatter: keep `name` and `description`; add `inherit: true`. No `model:`, no `effort:`.
- The in-body "If you are a smaller model (Haiku-class)" section is resolved: fold anything it says that the body does not already say into the main text as plain instruction, then delete the section.
- Body must end under 500 lines and under ~5,000 tokens (chars/4); move background, API listings, version/migration notes, benchmarks, long examples and templates into references/ files. Every reference file (new or kept) opens with two lines: `Load when: …` and `Keywords: …` (3–5), then a `## Contents` TOC if it is over 100 lines. References stay one level deep.
- Description: third person; what + when; add a negative trigger (what it is not for, pointing at the sibling that owns that) if missing.
- Windows/backslash paths become forward-slash or relative; a verbatim quoted error string may keep its backslashes.
- Time-sensitive statements ("until 2026-08-25", "currently broken", "verified 2026-08-20") move under a `## History` heading at the end, or are reworded as dated facts there.
- Replace ALWAYS/NEVER/MUST/caps and "Do NOT" with the wanted behaviour plus its reason (rule 4). Remove rituals (rule 5). Keep quoted bad examples as-is.
- Graph links: at most 3, only to siblings with real description-keyword overlap or an explicit in-body hand-off; written as one router sentence at the hand-off point, path form `../<sibling>/SKILL.md`. Do not link to fable5-migration, opus5-migration or modernize-prompt; if you notice overlap with them, note it in the diff file only.
- Preserve every project-specific fact (versions, pitfalls, paths, function names, thresholds). This is a reference skill: facts are the value. Reorganize and trim prose; do not invent, and do not drop a fact — if it leaves the body it must land in a reference.
- Terminology: one term per concept across SKILL.md and references.

Write:
A) The full rewritten skill folder to /mnt/user-data/outputs/p3/rewritten/<skill>/ — SKILL.md and every references/*.md it needs. Copy kept reference files in full (with the added Load-when/Keywords/TOC lines); do not leave a file behind that the rewrite still needs. Do not copy scripts (.py/.ps1) — list them in the diff as "kept unchanged, copy from original".
B) /mnt/user-data/outputs/p3/diffs/<skill>.md — first a 5-line summary (body lines before→after, files created/kept, links added, facts moved where), then a table with one row per change: what changed | why | rule/delta id (rule 1–7, O5-/S5-/H45-/F51-/U- slugs, J1–J9, or a lint rule id such as BODY-007).

Return ≤ 600 words: body line count before/after, the list of files written, links added, and any fact you could not place (should be none).
