import asyncio
import re
from datetime import datetime, timezone
from slack_sdk import WebClient
from vgv_rag.ingestion.connectors.types import RawDocument, Source, ProjectConfig

FILTERED_SUBTYPES = {"channel_join", "channel_leave", "channel_topic", "bot_message"}
PURE_EMOJI_RE = re.compile(r"^<:.+:>$")


class SlackConnector:
    def __init__(self, token: str):
        self._client = WebClient(token=token)

    async def discover_sources(self, config: ProjectConfig) -> list[dict]:
        sources = []
        for url in config.slack_channels:
            channel_id = _extract_channel_id(url)
            if channel_id:
                sources.append({"connector": "slack", "source_url": url, "source_id": channel_id})
        return sources

    async def fetch_documents(self, source: Source, since: datetime | None = None) -> list[RawDocument]:
        oldest = str(since.timestamp()) if since else None

        info = await asyncio.to_thread(
            lambda: self._client.conversations_info(channel=source.source_id)
        )
        channel_name = info.get("channel", {}).get("name", source.source_id)

        history = await asyncio.to_thread(
            lambda: self._client.conversations_history(
                channel=source.source_id,
                oldest=oldest,
                limit=200,
            )
        )

        docs = []
        for msg in history.get("messages", []):
            text = msg.get("text", "").strip()
            subtype = msg.get("subtype")

            if (not text
                    or subtype in FILTERED_SUBTYPES
                    or msg.get("bot_id")
                    or PURE_EMOJI_RE.match(text)):
                continue

            if msg.get("thread_ts") and msg["thread_ts"] != msg["ts"]:
                continue  # Reply — fetched below as part of parent thread

            author = None
            if user_id := msg.get("user"):
                try:
                    user_info = await asyncio.to_thread(
                        lambda uid=user_id: self._client.users_info(user=uid)
                    )
                    author = user_info.get("user", {}).get("real_name")
                except Exception:
                    pass

            content = text
            if msg.get("reply_count", 0) > 0:
                replies = await asyncio.to_thread(
                    lambda ts=msg["ts"]: self._client.conversations_replies(
                        channel=source.source_id, ts=ts
                    )
                )
                reply_texts = [
                    f"> {r['text']}"
                    for r in replies.get("messages", [])[1:]
                    if r.get("text", "").strip()
                ]
                if reply_texts:
                    content += "\n" + "\n".join(reply_texts)

            ts_float = float(msg["ts"])
            p_ts = msg["ts"].replace(".", "")
            docs.append(RawDocument(
                source_url=f"https://slack.com/archives/{source.source_id}/p{p_ts}",
                content=content,
                title=f"#{channel_name} thread",
                author=author,
                date=datetime.fromtimestamp(ts_float, tz=timezone.utc),
                artifact_type="slack_thread",
                source_tool="slack",
            ))

        return docs


def _extract_channel_id(url: str) -> str | None:
    match = re.search(r"/([CG][A-Z0-9]+)", url)
    return match.group(1) if match else None
