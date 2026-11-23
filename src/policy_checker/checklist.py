"""The GDPR Article 13 disclosures the agent looks for in a privacy policy.

Article 13 lists what a company must tell people when it collects their data. These are eight
of its points, picked because almost every policy should cover them. The ids must match the
`ItemId` list in schema.py.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Item:
    id: str
    article: str
    requirement: str  # what the law asks for, in plain words
    look_for: str  # words a policy usually uses for it


CHECKLIST = [
    Item(
        id="controller_identity",
        article="13(1)(a)",
        requirement="The legal name of the company responsible for the data, plus a way to "
        "contact it (postal address, email or form). A name with no contact is unclear.",
        look_for="'who we are', 'data controller', company name with a postal or email address",
    ),
    Item(
        id="dpo_contact",
        article="13(1)(b)",
        requirement="Contact details for a data protection officer. A DPO mentioned with no "
        "way to reach them is unclear.",
        look_for="'data protection officer', 'DPO', a dedicated privacy contact",
    ),
    Item(
        id="purposes_and_legal_basis",
        article="13(1)(c)",
        requirement="What the data is used for and the legal basis (consent, contract, "
        "legitimate interests, legal obligation). Purposes with no legal basis are unclear.",
        look_for="'legal basis', 'lawful basis', 'consent', 'legitimate interests', 'contract'",
    ),
    Item(
        id="recipients",
        article="13(1)(e)",
        requirement="Who the data is shared with: named companies or kinds of recipients.",
        look_for="'who we share', 'third parties', 'service providers', 'recipients'",
    ),
    Item(
        id="international_transfers",
        article="13(1)(f)",
        requirement="Whether data goes outside the EU/EEA (or the UK, for UK companies) "
        "and the safeguard used (standard contractual clauses, an adequacy decision). "
        "Transfers with no safeguard named are unclear.",
        look_for="'international transfers', 'outside the EEA', 'standard contractual clauses'",
    ),
    Item(
        id="retention",
        article="13(2)(a)",
        requirement="How long data is kept: real periods, or the criteria used to decide. "
        "Only 'as long as necessary' is unclear.",
        look_for="'retention', 'how long we keep', 'we keep your data for'",
    ),
    Item(
        id="user_rights",
        article="13(2)(b)",
        requirement="The person's rights: access, correction, deletion, restriction, "
        "objection, portability. Four or more of these named is present; fewer is unclear.",
        look_for="'your rights', 'right to access', 'right to erasure', 'portability'",
    ),
    Item(
        id="complaint_right",
        article="13(2)(d)",
        requirement="The right to complain to a data protection authority.",
        look_for="'supervisory authority', 'lodge a complaint', 'data protection authority', "
        "a named regulator such as the ICO or CNIL",
    ),
]

ITEM_IDS = [item.id for item in CHECKLIST]


def as_text() -> str:
    """The checklist written out for the system prompt."""
    lines = []
    for item in CHECKLIST:
        lines.append(f"- {item.id} (Article {item.article}): {item.requirement}")
        lines.append(f"  Usually found under: {item.look_for}")
    return "\n".join(lines)
