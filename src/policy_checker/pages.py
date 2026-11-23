"""Download a web page (or PDF) and split it into sections (a heading and its text) and links."""

import io
import unicodedata
from dataclasses import dataclass, field
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup
from pypdf import PdfReader
from pypdf.errors import PyPdfError

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; privacy-policy-checker/0.1)",
    "Accept-Language": "en",
}
HEADINGS = ["h1", "h2", "h3", "h4"]
BLOCKS = ["p", "li", "td"]


class PageError(Exception):
    """The page could not be downloaded or read. The message is passed on to the model."""


@dataclass
class Section:
    heading: str
    text: str


@dataclass
class Link:
    text: str
    url: str


@dataclass
class Page:
    url: str  # the address after any redirects
    title: str
    sections: list[Section] = field(default_factory=list)
    links: list[Link] = field(default_factory=list)

    @property
    def text(self) -> str:
        return "\n".join(f"{s.heading}\n{s.text}" for s in self.sections)


def fetch(url: str) -> Page:
    """Download one page. Raises PageError with a plain message when that fails."""
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    try:
        response = httpx.get(url, headers=HEADERS, follow_redirects=True, timeout=20)
    except httpx.HTTPError as error:
        raise PageError(f"could not download the page ({type(error).__name__})") from error
    if response.status_code != 200:
        raise PageError(f"the site answered with status {response.status_code}")
    content_type = response.headers.get("content-type", "")
    if "pdf" in content_type:
        return parse_pdf(response.content, str(response.url))
    if "html" not in content_type:
        raise PageError(f"the page is not HTML or PDF ({content_type or 'unknown type'})")
    return parse(response.text, str(response.url))


def parse_pdf(data: bytes, url: str) -> Page:
    """A PDF has no headings to find, so each page of the document becomes one section.

    PDF text comes out with a line break at the end of every printed line, which splits phrases
    like "Data Protection / Officer" in two. Joining each page into one paragraph keeps them
    whole for search and for the quote check.
    """
    try:
        reader = PdfReader(io.BytesIO(data))
        sections = [
            Section(heading=f"PDF page {number}", text=_pdf_text(page))
            for number, page in enumerate(reader.pages, start=1)
        ]
    except PyPdfError as error:
        raise PageError("the PDF could not be read") from error
    title = (reader.metadata.title if reader.metadata else None) or "PDF document"
    return Page(url=url, title=title, sections=sections)


def _pdf_text(page) -> str:
    # NFKC turns ligature characters (a single character for "fi" or "ffi") back into plain
    # letters, so a search for "officer" finds "Officer" in the PDF.
    text = unicodedata.normalize("NFKC", page.extract_text() or "")
    return " ".join(text.split())


def parse(html: str, url: str) -> Page:
    soup = BeautifulSoup(html, "html.parser")
    title = soup.title.get_text(strip=True) if soup.title else ""
    links = _links(soup, url)

    for tag in soup(["script", "style", "noscript", "svg", "template"]):
        tag.decompose()
    return Page(url=url, title=title, sections=_sections(soup), links=links)


def _links(soup: BeautifulSoup, base_url: str) -> list[Link]:
    seen = set()
    links = []
    for a in soup.find_all("a", href=True):
        url = urljoin(base_url, a["href"]).split("#")[0]
        if urlparse(url).scheme not in ("http", "https") or url in seen:
            continue
        seen.add(url)
        links.append(Link(text=a.get_text(" ", strip=True)[:80], url=url))
    return links


def _sections(soup: BeautifulSoup) -> list[Section]:
    """Walk headings and text blocks in page order. Each heading starts a new section."""
    sections = [Section(heading="(top of page)", text="")]
    for element in soup.find_all(HEADINGS + BLOCKS):
        # A paragraph inside a list item would be counted twice, once on its own and once
        # inside the list item's text, so blocks nested in other blocks are skipped.
        if element.name in BLOCKS and element.find_parent(BLOCKS):
            continue
        text = element.get_text(" ", strip=True)
        if not text:
            continue
        if element.name in HEADINGS:
            sections.append(Section(heading=text, text=""))
        else:
            sections[-1].text += text + "\n"

    sections = [s for s in sections if s.text or s.heading != "(top of page)"]
    # Some sites put text straight into <div>s with no paragraphs. Then the walk above finds
    # almost nothing, so fall back to the whole page as one section.
    if sum(len(s.text) for s in sections) < 500:
        body = soup.body or soup
        sections = [Section(heading="(whole page)", text=body.get_text("\n", strip=True))]
    return sections
