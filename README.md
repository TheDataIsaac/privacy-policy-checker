# privacy-policy-checker

An agent that reads a company's privacy policy and checks it for the disclosures GDPR Article 13
requires: who the company is, how to reach its data protection officer, why it uses the data and
on what legal basis, who gets the data, transfers outside the EU, how long data is kept, people's
rights and the right to complain to a regulator.

Give it a website. It finds the privacy policy, decides which sections and linked pages to read,
and reports each item as present, unclear, missing or not read, with a quote from the policy.
Plain Python then checks that every quote is really on the page.

It is a checklist, not legal advice.

```
$ uv run policy check monzo.com

https://monzo.com  ->  https://monzo.com/legal/privacy-notice
Stopped: submitted after 4 steps, 17,610 tokens

 yes  dpo_contact               quote checked
      The notice provides a DPO email address.
      "You can also reach our Data Protection Officer (DPO) at dpo@monzo.com ."
 yes  complaint_right           quote checked
      ...
```

## How it works

```
website --> agent loop -----------------------------> findings --> quote check --> report
              |  model picks a tool                                (plain Python)
              |  code runs it, result goes back
              |  repeat until submit_findings
              v
            fetch_page / read_section / search_page
```

The agent is a loop written by hand, with no agent framework. Each turn, the model either asks
for a tool or submits its findings. The code runs the tool, adds the result to the conversation
and calls the model again. Every step is written to a trace file.

| File | What it does |
|---|---|
| `checklist.py` | The eight Article 13 items, with the rule for present, unclear and missing. |
| `schema.py` | The shape of the answer: one finding per item, and the report built from it. |
| `pages.py` | Downloads a page (HTML or PDF) and splits it into headings, sections and links. |
| `tools.py` | The three page tools and the JSON descriptions the model sees for them. |
| `agent.py` | The loop: call the model, run the tools it asks for, stop at an answer or the step limit. |
| `verify.py` | Checks each quote against the pages the agent read. No model call. |
| `trace.py` | Writes every model call and tool call to a JSON Lines file, and shows it as a timeline. |
| `evals.py` | Runs the agent on labelled policies and scores it against the labels. |
| `server.py` | An MCP server, so Claude or any MCP client can call the checker as a tool. |
| `cli.py` | The `policy` command: `check`, `trace`, `evals`, `mcp`. |

## The ideas worth knowing

1. **The model decides the steps.** Policies are spread over different pages on every site, so a
   fixed pipeline can't know what to read. The model looks at the headings and links and chooses.
2. **The model reads; code checks.** A finding needs a quote copied from the page, and
   `verify.py` confirms the quote is there. A quote under four words doesn't count, because a
   phrase like "your rights" appears in almost any policy.
3. **Unknown is not missing.** If a page can't be read (blocked, or built with JavaScript), the
   item is `not_read`, not `missing`. Saying a company leaves something out when you never saw
   the page would be a false accusation.
4. **Tools don't crash the run.** A broken link comes back to the model as an error message it
   can read, and it tries another way, like a person would.
5. **Every run leaves a trace.** When an answer is wrong, the trace shows whether the page, the
   search or the decision went wrong.

## Run it

```bash
uv sync
# put OPENAI_API_KEY=... in a .env file
uv run policy check plausible.io
uv run policy check https://www.spotify.com/uk/legal/privacy-policy/ --json
uv run policy trace traces/<file>.jsonl
```

Settings can be changed in `.env`: `LLM_MODEL`, `REASONING_EFFORT` and `MAX_STEPS`.

## Evaluation

`evals/labels.json` holds reference labels for ten companies' policies: the right status for
each of the eight items (80 labels), with the quote and reason behind every label. They were
written from the full text of each policy, separately from the agent, and follow the same rules
the agent gets in `checklist.py`.

```bash
uv run policy evals            # runs the agent on all ten, about 10 minutes
uv run policy evals --limit 2  # a quick check
```

It prints the accuracy next to a baseline (answering "present" for everything), the accuracy for
each item, the most common mistakes, how often the agent found the right policy page, and how
many of its quotes were really on the page. Each run is saved in `runs/`.

## Use it from Claude (MCP)

`uv run policy mcp` starts an MCP server over stdio with one tool, `check_privacy_policy`. To add
it to Claude Code:

```bash
claude mcp add privacy-policy-checker -- uv run --directory /path/to/privacy-policy-checker policy mcp
```

## Limits

- Pages built with JavaScript can't be read; those items come back as `not_read`.
- It checks what a policy says, not what the company does.
- Eight of Article 13's points, not all of them.
- The labels are one careful reading of each policy. Some calls are borderline, and the label's
  reason says so.
