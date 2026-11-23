"""Check that each quote really appears on a page the agent read (string matching, no model)."""

import re
import unicodedata

from policy_checker.pages import Page
from policy_checker.schema import CheckedFinding, Finding, Status

MIN_QUOTE_WORDS = 4  # a quote like "your rights" would match almost any policy

# Web pages and models write the same punctuation in different ways: curly or straight quotes,
# long or short dashes, non-breaking spaces. These are made the same before comparing, so a
# correct quote isn't rejected over a typographic detail.
SAME_CHARACTER = str.maketrans(
    {
        "\u2018": "'",  # left single quote
        "\u2019": "'",  # right single quote (also the curly apostrophe)
        "\u201c": '"',  # left double quote
        "\u201d": '"',  # right double quote
        "\u2013": "-",  # en dash
        "\u2014": "-",  # em dash
        "\u00a0": " ",  # non-breaking space
    }
)


def normalise(text: str) -> str:
    # NFKC turns look-alike characters into plain ones. The one that matters here: PDFs often
    # store "fi" and "ffi" as single ligature characters, so "Officer" on the page wouldn't
    # match "Officer" typed by the model. N26's policy PDF does exactly that.
    text = unicodedata.normalize("NFKC", text)
    text = text.translate(SAME_CHARACTER).replace("\u200b", "")
    text = re.sub(r"\s+", " ", text)
    # A link inside a sentence often leaves a space before the next full stop or comma
    # ("dpo@monzo.com ."), which a model copying the sentence leaves out.
    text = re.sub(r" ([.,;:])", r"\1", text)
    return text.lower().strip()


def quote_found(quote: str, pages: list[Page]) -> bool:
    quote = normalise(quote)
    if len(quote.split()) < MIN_QUOTE_WORDS:
        return False
    return any(quote in normalise(page.text) for page in pages)


def check(finding: Finding, pages: dict[str, Page]) -> CheckedFinding:
    if finding.status in (Status.MISSING, Status.NOT_READ):
        found = None  # nothing was claimed, so there is nothing to check
    else:
        # Look on the page the model named first. Models sometimes name the wrong page for a
        # quote that is real, so the other pages it read count too.
        cited = pages.get(finding.page_url)
        ordered = ([cited] if cited else []) + list(pages.values())
        found = quote_found(finding.quote, ordered)
    return CheckedFinding(**finding.model_dump(), quote_found=found)
