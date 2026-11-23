"""The shape of the agent's answer, and of the report built from it."""

from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict

# Must match the ids in checklist.py. Written out here so the model can only use these.
ItemId = Literal[
    "controller_identity",
    "dpo_contact",
    "purposes_and_legal_basis",
    "recipients",
    "international_transfers",
    "retention",
    "user_rights",
    "complaint_right",
]


class Status(str, Enum):
    PRESENT = "present"  # the policy clearly gives this information
    UNCLEAR = "unclear"  # it mentions the topic but leaves out what the law asks for
    MISSING = "missing"  # the agent read the policy and the information isn't there
    NOT_READ = "not_read"  # the page that should hold it couldn't be read (an error, a
    # page built with JavaScript). Unknown is not the same as missing.


class Finding(BaseModel):
    """What the model says about one checklist item."""

    # extra="forbid" makes the JSON schema say additionalProperties: false, which OpenAI's
    # strict mode requires.
    model_config = ConfigDict(extra="forbid")

    item: ItemId
    status: Status
    quote: str  # copied exactly from the page; empty for missing and not_read
    page_url: str  # the page the quote comes from; empty for missing and not_read
    note: str  # one short sentence explaining the decision


class Findings(BaseModel):
    """The arguments of the submit_findings tool: one finding per checklist item."""

    model_config = ConfigDict(extra="forbid")

    policy_url: str  # the main privacy policy page the agent found
    findings: list[Finding]


class CheckedFinding(Finding):
    """A finding after the code has looked for its quote on the pages the agent read."""

    model_config = ConfigDict(extra="ignore")

    quote_found: bool | None  # None when there is no quote to check (missing, not_read)


class Report(BaseModel):
    website: str
    policy_url: str
    findings: list[CheckedFinding]
    pages_read: list[str]
    steps: int
    input_tokens: int
    output_tokens: int
    stopped: str  # "submitted", or why the agent stopped without an answer
    trace_file: str
