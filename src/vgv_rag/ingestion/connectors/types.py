import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol


@dataclass
class RawDocument:
    source_url: str
    content: str
    title: str
    date: datetime
    artifact_type: str
    source_tool: str
    author: str | None = None


@dataclass
class Source:
    id: str
    project_id: str | None  # None for program-level sources
    connector: str
    source_url: str
    source_id: str
    last_synced_at: datetime | None = None
    program_id: str | None = None  # Set for program-level sources


@dataclass
class ProgramConfig:
    project_hub_urls: list[str] = field(default_factory=list)
    quick_links: list[str] = field(default_factory=list)
    communication_channels: list[str] = field(default_factory=list)


@dataclass
class ProjectConfig:
    slack_channels: list[str] = field(default_factory=list)
    github_repos: list[str] = field(default_factory=list)
    figma_files: list[str] = field(default_factory=list)
    jira_projects: list[str] = field(default_factory=list)
    notion_pages: list[str] = field(default_factory=list)
    google_drive_folders: list[str] = field(default_factory=list)
    google_drive_docs: list[str] = field(default_factory=list)


ARTIFACT_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"meeting|sync|standup|retro|demo|kickoff", re.I), "meeting_note"),
    (re.compile(r"prd|product requirement|spec|brief", re.I), "prd"),
    (re.compile(r"adr|decision|architecture", re.I), "adr"),
    (re.compile(r"story|ticket|task|feature", re.I), "story"),
    (re.compile(r"design|figma|ui|ux", re.I), "design_spec"),
]


def detect_artifact_type(title: str) -> str:
    for pattern, artifact_type in ARTIFACT_PATTERNS:
        if pattern.search(title):
            return artifact_type
    return "document"


class Connector(Protocol):
    async def discover_sources(self, config: ProjectConfig) -> list[dict]:
        ...

    async def fetch_documents(self, source: Source, since: datetime | None = None) -> list[RawDocument]:
        ...
