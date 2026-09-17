# The 7 rules (Opus 5 / Fable 5)

Source: the video "I studied every Claude Prompting rule so you don't have to" and the Anthropic guidance it cites (Opus 5 guide, Fable 5 and Fable 5.1 guide, prompting best practices, Claude Code best practices, context engineering post), plus the GPT-Astra comparison.

1. **Give it the whole job, not the steps.** Give the complete task specification up front and let it run. Remove step lists where order does not matter. Opus 5 performs best given the complete task and left to run; skills written for prior models are often too prescriptive and can degrade output. For a genuinely short task, drop the effort setting to low or medium and save high effort for jobs that need it.

2. **Say why, not just what.** The model performs better when it understands the intent. Template: "I'm working on [the larger task] for [who it is for]. They need [what the output enables]. With that in mind: [request]."

3. **Say what done looks like.** State the definition of done and the length the task needs, because these models expand scope and add steps you did not ask for. For a larger build, do not try to write a better prompt: have Claude interview you with the AskUserQuestion tool (goal, who it is for, what done looks like, edge cases, tradeoffs) and write the brief itself.

4. **Swap hard rules and capitals for reasons.** These models are responsive enough that IMPORTANT / CRITICAL / MUST / ALWAYS / NEVER and CAPS over-trigger. Replace the rule with the behaviour you want and the reason for it, and tell it what to do instead of what not to do. Remove anti-formatting rules the model already follows: Fable 5.1 already uses fewer bullets, less bold, and fewer tables, so "never use bullet points" is fighting a model that already stopped.

5. **Take out the rituals.** Remove "think step by step", "show your reasoning", "double-check", and "use a subagent to verify". Opus 5 thinks before it answers by default, so "think carefully" asks for what it already does; on Fable 5, asking the model to explain its internal reasoning can trigger a refusal; the model already checks its own work, so "double-check" buys a second pass that changes nothing. If you want a check, give it one it can run: a script, a test, or a checklist file, and put it in the skill.

6. **Tell it whether you want an answer or an action.** Claude 5 models are quicker to act. Default boundary, placed in the file that always loads: when the user is describing a problem, asking a question, or thinking out loud, the deliverable is your assessment; report your findings and stop, and do not apply a fix until they ask for one. Scheduled tasks get the opposite paragraph in their own prompt: you are operating autonomously, proceed on reversible actions.

7. **Fix the voice once, in the file that always loads.** Voice and "no jargon" lines are true of everything Claude writes for you, so move them out of every skill and into the always-loaded file. Fable: remove all mannered prose. Opus: keep responses focused, brief, and concise, and spend most of the response on the main answer.

**The golden rule:** show your prompt to a colleague with no context. If they would be confused, Claude will be too.

## Where each rule lands
- Job, why, done, runnable check: the prompt or the skill for that task.
- Assess-and-stop boundary (rule 6) and voice (rule 7): the CLAUDE.md / always-loaded instructions.
- Autonomous paragraph: only in a scheduled task's own prompt.

## How Claude differs from GPT-Astra (context, not rules to apply)
- Both want the goal and intent over the steps, both want plain paragraphs, and both over-verify small changes with the same fix: only re-run tests or checks when a new failure justifies it.
- Rule 6 is opposite: Astra stops and asks, so OpenAI add "bias towards action"; Claude 5 keeps going, so Anthropic add a boundary. Same slot in the always-loaded file, opposite paragraph.
- Rule 4 differs: OpenAI ship a blocklist of words, which is the kind of "never" list Anthropic tell you to stop writing. On Claude, the positive version with a reason works better.
