import html
import re
from typing import List, Tuple

BLOCK_RE = re.compile(
    r"<!--\s+wp:([a-zA-Z0-9_/:-]+)(?:\s+\{.*?\})?\s+-->(.*?)<!--\s+/wp:\1\s+-->",
    re.DOTALL,
)
PARAGRAPH_RE = re.compile(r"<p\b[^>]*>.*?</p>", re.DOTALL | re.IGNORECASE)
TAG_RE = re.compile(r"<[^>]+>")
TIME_RE = re.compile(r"^\s*(\d{1,2}):([0-5]\d)\b(.*)$", re.DOTALL)


def extract_blocks(post_content: str) -> List[Tuple[str, str]]:
    return BLOCK_RE.findall(post_content)


def strip_tags(text: str) -> str:
    no_tags = TAG_RE.sub("", text)
    return html.unescape(no_tags).strip()


def paragraph_from_block(block_body: str) -> str | None:
    match = PARAGRAPH_RE.search(block_body)
    return match.group(0).strip() if match else None
