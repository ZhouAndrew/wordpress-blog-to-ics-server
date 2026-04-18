from __future__ import annotations

from dataclasses import dataclass

from .extractor import extract_blocks, paragraph_from_block, strip_tags


@dataclass
class WordPressBlock:
    index: int
    block_type: str
    raw_paragraph_html: str | None
    visible_text: str


def iter_blocks(post_content: str) -> list[WordPressBlock]:
    blocks: list[WordPressBlock] = []
    for index, (block_type, block_body) in enumerate(extract_blocks(post_content), start=1):
        raw_p = paragraph_from_block(block_body)
        visible = strip_tags(raw_p) if raw_p else ""
        blocks.append(
            WordPressBlock(
                index=index,
                block_type=block_type,
                raw_paragraph_html=raw_p,
                visible_text=visible,
            )
        )
    return blocks
