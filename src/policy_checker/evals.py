"""Score the agent against reference labels for real privacy policies.

Each labelled company has the right status for all eight items. The agent runs on every
company, and its statuses are compared with the labels. Two numbers matter most:

- accuracy: how many statuses match the labels.
- quote check rate: how many quotes the agent gave are really on the page.

A baseline is printed next to the accuracy. "Present for everything" needs no AI at all, so the
agent is only useful if it beats that.
"""

import json
from collections import Counter
from datetime import datetime
from pathlib import Path

from policy_checker.agent import Settings, check_policy
from policy_checker.checklist import ITEM_IDS


def run(labels_path: Path, out_folder: Path, limit: int | None = None) -> dict:
    companies = json.loads(labels_path.read_text(encoding="utf-8"))[:limit]
    settings = Settings()
    rows = []
    runs = []

    for company in companies:
        print(f"Checking {company['company']} ...", flush=True)
        report = check_policy(company["website"], settings)
        got = {f.item: f for f in report.findings}
        runs.append(
            {
                "company": company["company"],
                "stopped": report.stopped,
                "found_policy": same_page(report.policy_url, company["policy_url"]),
                "steps": report.steps,
                "tokens": report.input_tokens + report.output_tokens,
                "trace_file": report.trace_file,
            }
        )
        for item in ITEM_IDS:
            expected = company["labels"][item]["status"]
            finding = got.get(item)
            rows.append(
                {
                    "company": company["company"],
                    "item": item,
                    "expected": expected,
                    "got": finding.status.value if finding else "no answer",
                    "quote_found": finding.quote_found if finding else None,
                }
            )

    summary = summarise(rows, runs)
    # Saved before printing, so a long paid run is never lost to a printing problem.
    out_folder.mkdir(parents=True, exist_ok=True)
    out_file = out_folder / f"eval-{datetime.now():%Y%m%d-%H%M}.json"
    out_file.write_text(
        json.dumps({"summary": summary, "runs": runs, "rows": rows}, indent=2), encoding="utf-8"
    )
    print_summary(summary)
    print(f"\nSaved {out_file}")
    return summary


def same_page(a: str, b: str) -> bool:
    """Compare two addresses, ignoring http/https, www and a trailing slash."""

    def simple(url: str) -> str:
        return url.lower().split("://")[-1].removeprefix("www.").rstrip("/")

    return simple(a) == simple(b)


def summarise(rows: list[dict], runs: list[dict]) -> dict:
    def accuracy(subset: list[dict]) -> float:
        return round(sum(r["expected"] == r["got"] for r in subset) / len(subset), 3)

    checked = [r["quote_found"] for r in rows if r["quote_found"] is not None]
    return {
        "companies": len(runs),
        "labels": len(rows),
        "accuracy": accuracy(rows),
        "baseline_all_present": round(sum(r["expected"] == "present" for r in rows) / len(rows), 3),
        "accuracy_by_item": {
            item: accuracy([r for r in rows if r["item"] == item]) for item in ITEM_IDS
        },
        # (label, agent's answer) pairs that didn't match, most common first
        "mistakes": Counter(
            f"{r['expected']} -> {r['got']}" for r in rows if r["expected"] != r["got"]
        ).most_common(),
        "quote_check_rate": round(sum(checked) / len(checked), 3) if checked else None,
        "found_policy": sum(r["found_policy"] for r in runs),
        "runs_without_answer": sum(r["stopped"] != "submitted" for r in runs),
        "average_steps": round(sum(r["steps"] for r in runs) / len(runs), 1),
        "average_tokens": round(sum(r["tokens"] for r in runs) / len(runs)),
    }


def print_summary(summary: dict) -> None:
    print(f"\n{summary['companies']} companies, {summary['labels']} labels")
    print(f"Accuracy:            {summary['accuracy']:.0%}")
    print(f"Baseline (present):  {summary['baseline_all_present']:.0%}")
    rate = summary["quote_check_rate"]  # None when no finding had a quote to check
    print(f"Quotes found:        {'n/a' if rate is None else f'{rate:.0%}'}")
    print(f"Found the policy:    {summary['found_policy']} of {summary['companies']}")
    print(f"Runs with no answer: {summary['runs_without_answer']}")
    print(
        f"Average per company: {summary['average_steps']} steps, "
        f"{summary['average_tokens']:,} tokens"
    )
    print("\nAccuracy by item:")
    for item, value in summary["accuracy_by_item"].items():
        print(f"  {item:<26} {value:.0%}")
    print("\nMistakes (label -> agent):")
    for pair, count in summary["mistakes"]:
        print(f"  {pair:<22} {count}")
