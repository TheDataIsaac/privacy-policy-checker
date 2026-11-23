"""An MCP server, so any MCP client (Claude Desktop, Claude Code, Cursor...) can use the checker.

MCP is a standard way for an AI app to find and call tools that live in another program. This
file offers one tool, check_privacy_policy. The client starts this program (`policy mcp`) and
talks to it over stdin and stdout.
"""

from mcp.server import MCPServer

from policy_checker.agent import Settings, check_policy
from policy_checker.schema import Report

# WARNING keeps the log quiet: at INFO it prints a line for every web request.
server = MCPServer("privacy-policy-checker", log_level="WARNING")


@server.tool()
def check_privacy_policy(website: str) -> Report:
    """Check a company's privacy policy for the disclosures GDPR Article 13 requires.

    Give a website (like example.com) or the address of the privacy policy itself. Returns one
    finding per checklist item (present, unclear, missing or not_read) with a quote and
    whether code found that quote on the page. It takes about a minute. It is a checklist, not
    legal advice.
    """
    # Returning the Pydantic model (not text) lets the client read the report as typed data.
    return check_policy(website, Settings())
