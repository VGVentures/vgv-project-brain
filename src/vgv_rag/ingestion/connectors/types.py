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
    project_id: str
    connector: str
    source_url: str
    source_id: str
    last_synced_at: datetime | None = None


@dataclass
class ProjectConfig:
    slack_channels: list[str] = field(default_factory=list)
    github_repos: list[str] = field(default_factory=list)
    figma_files: list[str] = field(default_factory=list)
    jira_projects: list[str] = field(default_factory=list)
    notion_pages: list[str] = field(default_factory=list)
    google_drive_folders: list[str] = field(default_factory=list)
    google_drive_docs: list[str] = field(default_factory=list)


class Connector(Protocol):
    async def discover_sources(self, config: ProjectConfig) -> list[dict]:
        ...

    async def fetch_documents(self, source: Source, since: datetime | None = None) -> list[RawDocument]:
        ...
