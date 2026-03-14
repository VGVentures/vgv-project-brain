import pytest
import httpx
import respx

FIGMA_RESPONSE = {
    "name": "Design System",
    "document": {
        "name": "Document",
        "children": [{
            "name": "Components",
            "type": "FRAME",
            "children": [
                {
                    "id": "1:1",
                    "name": "Button",
                    "type": "COMPONENT",
                    "description": "Primary CTA button",
                    "children": [],
                },
                {
                    "id": "1:2",
                    "name": "Input",
                    "type": "COMPONENT",
                    "description": "Text input field",
                    "children": [],
                },
            ],
        }],
    },
}


@pytest.mark.asyncio
@respx.mock
async def test_figma_extracts_components():
    respx.get("https://api.figma.com/v1/files/ABC123").mock(
        return_value=httpx.Response(200, json=FIGMA_RESPONSE)
    )

    from vgv_rag.ingestion.connectors.figma import FigmaConnector
    from vgv_rag.ingestion.connectors.types import Source

    connector = FigmaConnector("fake-token")
    source = Source(
        id="s1", project_id="p1", connector="figma",
        source_url="https://figma.com/file/ABC123/Design-System", source_id="ABC123"
    )

    docs = await connector.fetch_documents(source)
    assert len(docs) == 2
    assert all(d.artifact_type == "design_spec" for d in docs)
    assert any("Button" in d.content for d in docs)
    assert any("Primary CTA" in d.content for d in docs)
