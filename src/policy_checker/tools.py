"""The tools the agent can call, and the JSON descriptions the model sees for them.

Each tool returns a small dict. The agent loop turns it into JSON and hands it back to the model.
A tool never raises: problems come back as {"error": "..."} so the model can read them and try
something else, like a human would after a broken link.
"""

from urllib.parse import urlparse

from policy_checker.pages import Page, PageError, fetch
from policy_checker.schema import Findings

MAX_LINKS = 40
MAX_SECTION_CHARS = 6000
MAX_SEARCH_HITS = 8
LINK_WORDS = ["privacy", "cookie", "data", "gdpr", "rights", "legal", "policy", "protection"]


class Browser:
    """Runs the page tools and remembers every page it has read.

    Keeping the pages means read_section and search_page don't download again, and the quote
    check at the end can look at exactly the text the model saw.
    """

    def __init__(self) -> None:
        self.pages: dict[str, Page] = {}

    def fetch_page(self, url: str) -> dict:
        try:
            page = fetch(url)
        except PageError as error:
            return {"error": str(error), "url": url}
        self.pages[page.url] = page
        if url != page.url:
            self.pages[url] = page  # so the model can keep using the address it asked for

        result = {
            "url": page.url,
            "title": page.title,
            "words": len(page.text.split()),
            "headings": [s.heading for s in page.sections],
            "links": _useful_links(page),
        }
        if result["words"] < 300:
            result["warning"] = (
                "Very little text on this page. It may be built with JavaScript, which this "
                "tool can't run. Try another link, or treat its contents as unknown."
            )
        return result

    def read_section(self, url: str, heading: str) -> dict:
        page = self.pages.get(url)
        if page is None:
            return {"error": "Fetch this page with fetch_page first.", "url": url}
        wanted = heading.strip().lower()
        matches = [s for s in page.sections if s.heading.strip().lower() == wanted]
        if not matches:
            return {"error": f"No heading called {heading!r} on this page.", "url": page.url}
        # A page can use the same heading twice (say "Your rights" once for the EU and once
        # for the US), so the text of every section with this heading comes back.
        text = "\n".join(s.text for s in matches)
        result = {"url": page.url, "heading": matches[0].heading, "text": text}
        if len(text) > MAX_SECTION_CHARS:
            result["text"] = text[:MAX_SECTION_CHARS]
            result["note"] = "Section cut short. Use search_page to find the rest."
        return result

    def search_page(self, url: str, words: list[str]) -> dict:
        page = self.pages.get(url)
        if page is None:
            return {"error": "Fetch this page with fetch_page first.", "url": url}
        wanted = [w.lower() for w in words if w.strip()]
        hits = []
        for section in page.sections:
            if any(w in section.heading.lower() for w in wanted):
                # The heading itself matches, so one result with the start of the section is
                # enough. The model can read the rest with read_section.
                hits.append({"heading": section.heading, "text": section.text[:1000]})
                continue
            for paragraph in section.text.splitlines():
                positions = [paragraph.lower().find(w) for w in wanted if w in paragraph.lower()]
                if positions:
                    # A long paragraph is cut to 1,000 characters starting a little before the
                    # first match, so the match itself is never cut off.
                    start = max(0, min(positions) - 200)
                    hits.append(
                        {"heading": section.heading, "text": paragraph[start : start + 1000]}
                    )
        return {"url": page.url, "matches": len(hits), "results": hits[:MAX_SEARCH_HITS]}


def _useful_links(page: Page) -> list[dict]:
    """Links on the same site that look related to privacy come first; the rest are cut."""
    site = urlparse(page.url).netloc.removeprefix("www.")

    def score(link) -> int:
        text = (link.text + " " + link.url).lower()
        same_site = site in urlparse(link.url).netloc
        return sum(word in text for word in LINK_WORDS) * 2 + same_site

    ranked = sorted(page.links, key=score, reverse=True)
    return [{"text": link.text, "url": link.url} for link in ranked[:MAX_LINKS]]


# What the model sees. The descriptions matter: they are how the model decides which tool to
# use, so they say what each tool returns and when to use it.
TOOLS = [
    {
        "type": "function",
        "name": "fetch_page",
        "description": "Download a web page. Returns its title, word count, the list of "
        "headings on it and up to 40 links (privacy-related links first). Use it on the "
        "website you were given, then on the privacy policy and any page it points to.",
        "parameters": {
            "type": "object",
            "properties": {"url": {"type": "string", "description": "Full address of the page"}},
            "required": ["url"],
            "additionalProperties": False,
        },
        "strict": True,
    },
    {
        "type": "function",
        "name": "read_section",
        "description": "Read the text under one heading of a page you have already fetched. "
        "Use a heading exactly as fetch_page listed it.",
        "parameters": {
            "type": "object",
            "properties": {
                "url": {"type": "string"},
                "heading": {"type": "string"},
            },
            "required": ["url", "heading"],
            "additionalProperties": False,
        },
        "strict": True,
    },
    {
        "type": "function",
        "name": "search_page",
        "description": "Find paragraphs on a page you have already fetched that contain any "
        "of the given words. Use it when the headings don't show where something is.",
        "parameters": {
            "type": "object",
            "properties": {
                "url": {"type": "string"},
                "words": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["url", "words"],
            "additionalProperties": False,
        },
        "strict": True,
    },
    {
        "type": "function",
        "name": "submit_findings",
        "description": "Give your final answer: exactly one finding for each checklist item. "
        "Call this once, when you have looked for every item.",
        "parameters": Findings.model_json_schema(),
        "strict": True,
    },
]
