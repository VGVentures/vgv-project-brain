import pytest
import httpx
import respx

JIRA_RESPONSE = {
    "issues": [{
        "key": "PROJ-1",
        "fields": {
            "summary": "Implement auth middleware",
            "description": {
                "type": "doc",
                "content": [{
                    "type": "paragraph",
                    "content": [{"type": "text", "text": "We need JWT validation."}]
                }],
            },
            "status": {"name": "In Progress"},
            "assignee": {"displayName": "Alice"},
            "updated": "2026-02-01T00:00:00.000+0000",
            "comment": {"comments": []},
        },
    }],
    "total": 1,
}


@pytest.mark.asyncio
@respx.mock
async def test_atlassian_fetches_issues():
    respx.get("https://verygoodventures.atlassian.net/rest/api/3/search").mock(
        return_value=httpx.Response(200, json=JIRA_RESPONSE)
    )

    from vgv_rag.ingestion.connectors.atlassian import AtlassianConnector
    from vgv_rag.ingestion.connectors.types import Source

    connector = AtlassianConnector(
        token="t", email="u@vgv.com", domain="verygoodventures.atlassian.net"
    )
    source = Source(
        id="s1", project_id="p1", connector="atlassian",
        source_url="https://verygoodventures.atlassian.net/jira/software/projects/PROJ",
        source_id="PROJ",
    )

    docs = await connector.fetch_documents(source)
    assert len(docs) == 1
    assert docs[0].artifact_type == "issue"
    assert "auth middleware" in docs[0].content
    assert "JWT validation" in docs[0].content
