"""Command line entry point: policy check, trace, evals, mcp."""

from pathlib import Path
from typing import Annotated

import typer

app = typer.Typer(
    help="Check a privacy policy for GDPR Article 13 disclosures.", no_args_is_help=True
)

SYMBOLS = {"present": "yes", "unclear": "?", "missing": "no", "not_read": "n/a"}
LABELS = Path("evals/labels.json")
RUNS = Path("runs")


@app.command()
def check(
    website: str,
    as_json: Annotated[bool, typer.Option("--json", help="Print the full report as JSON.")] = False,
) -> None:
    """Run the agent on one website or privacy policy address."""
    from policy_checker.agent import Settings, check_policy

    report = check_policy(website, Settings())
    if as_json:
        typer.echo(report.model_dump_json(indent=2))
        return

    typer.echo(f"\n{report.website}  ->  {report.policy_url or 'no policy found'}")
    typer.echo(
        f"Stopped: {report.stopped} after {report.steps} steps, "
        f"{report.input_tokens + report.output_tokens:,} tokens\n"
    )
    for f in report.findings:
        check_mark = {True: "quote checked", False: "QUOTE NOT FOUND", None: ""}[f.quote_found]
        typer.echo(f"{SYMBOLS[f.status.value]:>4}  {f.item:<25} {check_mark}")
        typer.echo(f"      {f.note}")
        if f.quote:
            typer.echo(f'      "{f.quote[:160]}"')
    typer.echo(f"\nTrace: {report.trace_file}")
    typer.echo("This is a checklist, not legal advice.")


@app.command()
def trace(file: Path) -> None:
    """Show a trace file as a timeline of model and tool calls."""
    from policy_checker.trace import show

    typer.echo(show(file))


@app.command()
def evals(
    labels: Annotated[Path, typer.Option(help="The labelled policies.")] = LABELS,
    limit: Annotated[int | None, typer.Option(help="Only run the first N companies.")] = None,
) -> None:
    """Run the agent on every labelled policy and score it."""
    from policy_checker.evals import run

    run(labels, RUNS, limit)


@app.command()
def mcp() -> None:
    """Start the MCP server (stdio), so an MCP client such as Claude can call the checker."""
    from policy_checker.server import server

    server.run()
