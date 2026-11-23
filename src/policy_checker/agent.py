"""The agent: a loop where the model picks a tool, the code runs it, and the result goes back.

There is no agent framework here on purpose. The whole loop is in `check_policy`, so every
step is visible: call the model, run the tools it asked for, add the results to the
conversation, repeat until it submits its findings or runs out of steps.
"""

import json
import time
from pathlib import Path

from openai import OpenAI
from pydantic import ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict

from policy_checker import checklist, verify
from policy_checker.schema import Findings, Report
from policy_checker.tools import TOOLS, Browser
from policy_checker.trace import PREVIEW_CHARS, Tracer, ms_since


class Settings(BaseSettings):
    """Read from environment variables or the .env file."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    openai_api_key: str
    llm_model: str = "gpt-5.6-luna"
    reasoning_effort: str = "low"
    max_steps: int = 15  # model calls allowed before the agent has to stop
    trace_folder: Path = Path("traces")


SYSTEM_PROMPT = f"""You check a company's privacy policy for the disclosures that GDPR \
Article 13 requires. You are a careful reviewer, not a lawyer, and you only report what the \
pages say.

How to work:
1. Fetch the website you are given. If it isn't the privacy policy, find the link to the \
privacy policy (often in the footer) and fetch that.
2. Use the headings to decide which sections to read. Use search_page when the headings don't \
show where something is. Follow a link to another page (a cookie policy, a "your rights" page) \
only when the policy sends you there for a checklist item.
3. Decide each checklist item:
   - present: the policy clearly gives the information the law asks for.
   - unclear: it touches the topic but leaves out part of what the law asks for.
   - missing: you read the policy (headings, then search) and it isn't there.
   - not_read: the page that should hold it couldn't be read. Never say missing for a page \
you couldn't read.
4. Call submit_findings once, with exactly one finding for every item.

Rules for quotes:
- For present or unclear, copy one sentence exactly, word for word, from a page you read, \
and give that page's address. Code checks every quote against the page.
- Pick the sentence that holds the information itself (the email address, the time period, \
the list of rights), not a lead-in such as "These include:".
- For missing and not_read, leave quote and page_url empty.
- If a page can't be read (an error, or very little text), say so in the note. Don't guess \
what it contains.

Checklist:
{checklist.as_text()}
"""


def check_policy(website: str, settings: Settings) -> Report:
    client = OpenAI(api_key=settings.openai_api_key, timeout=120)
    browser = Browser()
    tracer = Tracer(settings.trace_folder, website)
    tracer.log("run_start", website=website, model=settings.llm_model)

    # The conversation so far. The model sees all of it on every call: our request, its own
    # tool calls and every tool result.
    conversation = [{"role": "user", "content": f"Website: {website}"}]
    input_tokens = output_tokens = 0

    for step in range(1, settings.max_steps + 1):
        start = time.perf_counter()
        response = client.responses.create(
            model=settings.llm_model,
            instructions=SYSTEM_PROMPT,
            input=conversation,
            tools=TOOLS,
            reasoning={"effort": settings.reasoning_effort},
        )
        input_tokens += response.usage.input_tokens
        output_tokens += response.usage.output_tokens
        calls = [item for item in response.output if item.type == "function_call"]
        tracer.log(
            "model_call",
            step=step,
            ms=ms_since(start),
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            tool_calls=[call.name for call in calls],
        )
        conversation += response.output

        if not calls:
            # The model wrote a reply instead of using a tool. Remind it how to finish.
            conversation.append(
                {"role": "user", "content": "Finish by calling submit_findings for every item."}
            )
            continue

        for call in calls:
            if call.name == "submit_findings":
                findings, problem = read_findings(call.arguments)
                if findings:
                    return finish(
                        website, findings, browser, step, tracer, input_tokens, output_tokens
                    )
                # The answer was incomplete, so it goes back to the model to fix.
                output = {"error": problem}
            else:
                output = run_tool(browser, call.name, call.arguments, step, tracer)
            conversation.append(
                {
                    "type": "function_call_output",
                    "call_id": call.call_id,
                    "output": json.dumps(output),
                }
            )

    tracer.log(
        "run_end",
        stopped="step limit",
        steps=settings.max_steps,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
    )
    return Report(
        website=website,
        policy_url="",
        findings=[],
        pages_read=sorted({page.url for page in browser.pages.values()}),
        steps=settings.max_steps,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        stopped="step limit",
        trace_file=str(tracer.path),
    )


def run_tool(browser: Browser, name: str, arguments: str, step: int, tracer: Tracer) -> dict:
    """Run one page tool and log it. Unknown tools and bad arguments come back as errors."""
    start = time.perf_counter()
    args = {}
    try:
        args = json.loads(arguments)
        if name == "fetch_page":
            output = browser.fetch_page(args["url"])
        elif name == "read_section":
            output = browser.read_section(args["url"], args["heading"])
        elif name == "search_page":
            output = browser.search_page(args["url"], args["words"])
        else:
            output = {"error": f"There is no tool called {name}."}
    except Exception as error:  # noqa: BLE001 (deliberate: see the comment below)
        # The tools already turn the usual problems (a dead link, a wrong heading) into error
        # messages. Anything unexpected, like a malformed address or a broken PDF, is caught
        # here so one bad page can't crash the whole run. The model reads the error and can
        # try another way, and the trace records it.
        output = {"error": f"The tool failed: {type(error).__name__}: {str(error)[:200]}"}
    tracer.log(
        "tool_call",
        step=step,
        name=name,
        args=args,
        ms=ms_since(start),
        error=output.get("error"),
        output=json.dumps(output, ensure_ascii=False)[:PREVIEW_CHARS],
    )
    return output


def read_findings(arguments: str) -> tuple[Findings | None, str]:
    """Parse the final answer and check it covers every item exactly once."""
    try:
        findings = Findings.model_validate_json(arguments)
    except ValidationError as error:
        return None, f"Your findings don't match the format: {error}"
    given = [f.item for f in findings.findings]
    left_out = [item for item in checklist.ITEM_IDS if item not in given]
    repeated = sorted({item for item in given if given.count(item) > 1})
    if left_out or repeated:
        return (
            None,
            f"Give exactly one finding per item. Left out: {left_out}. Repeated: {repeated}.",
        )
    return findings, ""


def finish(website, findings, browser, step, tracer, input_tokens, output_tokens) -> Report:
    checked = [verify.check(f, browser.pages) for f in findings.findings]
    tracer.log(
        "run_end",
        stopped="submitted",
        steps=step,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
    )
    return Report(
        website=website,
        policy_url=findings.policy_url,
        findings=checked,
        pages_read=sorted({page.url for page in browser.pages.values()}),
        steps=step,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        stopped="submitted",
        trace_file=str(tracer.path),
    )
