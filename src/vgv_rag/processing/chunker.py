import re
from dataclasses import dataclass

CHARS_PER_TOKEN = 4


@dataclass
class ChunkConfig:
    strategy: str
    target_size: int
    overlap: int


CHUNKING_CONFIG: dict[str, ChunkConfig] = {
    "meeting_note": ChunkConfig("by_heading",     500, 50),
    "prd":          ChunkConfig("by_section",     600, 50),
    "story":        ChunkConfig("whole_document", 800,  0),
    "slack_thread": ChunkConfig("whole_document",1000,  0),
    "pr":           ChunkConfig("by_section",     500,  0),
    "design_spec":  ChunkConfig("by_component",   400,  0),
    "issue":        ChunkConfig("whole_document", 800,  0),
    "presentation": ChunkConfig("by_section",     500,  0),
}
DEFAULT_CONFIG = ChunkConfig("recursive_split", 500, 50)


def chunk(text: str, artifact_type: str) -> list[str]:
    config = CHUNKING_CONFIG.get(artifact_type, DEFAULT_CONFIG)

    if config.strategy == "whole_document":
        return [text.strip()]
    elif config.strategy == "by_heading":
        return _split_by_heading(text, r"^#{2,3}\s", config)
    elif config.strategy in ("by_section", "by_component"):
        return _split_by_heading(text, r"^#{1,2}\s", config)
    else:
        return _recursive_split(
            text,
            config.target_size * CHARS_PER_TOKEN,
            config.overlap * CHARS_PER_TOKEN,
        )


def _split_by_heading(text: str, pattern: str, config: ChunkConfig) -> list[str]:
    regex = re.compile(pattern, re.MULTILINE)
    lines = text.split("\n")
    sections: list[str] = []
    current: list[str] = []

    for line in lines:
        if regex.match(line) and current:
            sections.append("\n".join(current).strip())
            current = []
        current.append(line)

    if current:
        sections.append("\n".join(current).strip())

    target_chars = config.target_size * CHARS_PER_TOKEN
    overlap_chars = config.overlap * CHARS_PER_TOKEN

    result = []
    for section in sections:
        if len(section) <= target_chars:
            result.append(section)
        else:
            result.extend(_recursive_split(section, target_chars, overlap_chars))

    return [s for s in result if s.strip()]


def _recursive_split(text: str, target_chars: int, overlap_chars: int) -> list[str]:
    if len(text) <= target_chars:
        return [text]

    for sep in ["\n\n", "\n", ". ", " "]:
        parts = text.split(sep)
        if len(parts) <= 1:
            continue

        chunks: list[str] = []
        current = ""

        for part in parts:
            candidate = current + sep + part if current else part
            if len(candidate) > target_chars and current:
                chunks.append(current)
                tail = current[-overlap_chars:] if overlap_chars else ""
                current = tail + sep + part if tail else part
            else:
                current = candidate

        if current:
            chunks.append(current)

        return [c.strip() for c in chunks if c.strip()]

    return [text]
