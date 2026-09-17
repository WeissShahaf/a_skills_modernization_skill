# Evaluator-brief

Load when: dispatching the evaluator-brief subagent in Phase 3 or Phase 4 — paste this file as the subagent's instructions with <skill> filled in.
Keywords: subagent prompt, evaluator-brief, phase 3, phase 4, eval

You are the `evaluator` subagent: fresh context, medium effort, Read + Write only. You have NOT seen the rewrite rationale and must not look for it (do not read anything under /mnt/user-data/outputs/p3/diffs).

Inputs for your skill <skill>:
- ORIGINAL: /mnt/user-data/uploads/skill_optimizer/example_skills/cuniformNPX/.claude/skills/<skill>/ (SKILL.md + references/)
- REWRITTEN: /mnt/user-data/outputs/p3/rewritten/<skill>/ (SKILL.md + references/)

Procedure:
1. Read the ORIGINAL description (frontmatter only) and write 3 scenarios: two realistic user requests that should trigger this skill, one that should not (a neighbouring topic the description excludes or a sibling owns). Fix the scenarios before reading either body.
2. For each scenario, produce two answers: arm A using only the ORIGINAL folder as reference material, arm B using only the REWRITTEN folder. Each answer: (a) would this skill fire, yes/no; (b) a 5–10 line answer to the request drawn only from that folder, naming which reference file(s) you had to open.
3. Score each arm on each scenario 0–1 as the mean of four sub-scores: correct triggering decision (1/0); factual fidelity — every claim traceable to the folder (1 = all, 0.5 = one unsupported claim, 0 = more); completeness of the load-on-demand pointers — did the body tell you which reference to open and was it there (1/0.5/0); absence of fabrication (1 = none, 0 = any invented API, path or number).
4. Compare facts: list up to 5 facts from the ORIGINAL that a user of the REWRITTEN folder could no longer find anywhere (search all its files first). Each such fact lowers the rewritten fidelity score for the scenario it would matter to.

Write /mnt/user-data/outputs/p4/<skill>.json exactly in this shape:
{"skill": "...", "scenarios": [{"name": "...", "kind": "positive|negative", "request": "...", "score_before": 0.0, "score_after": 0.0, "note": "one line"}], "score_before": mean, "score_after": mean, "threshold": 0.8, "verdict": "pass|fail", "lost_facts": ["..."], "opened_refs_after": ["..."]}
verdict = pass when score_after >= 0.8 AND score_after >= score_before.
Return ≤ 200 words: the three scores per arm, the verdict, and the lost-facts list.
