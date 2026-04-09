import pytest
from vgv_rag.processing.chunker import chunk

MEETING_NOTE = """# Team Sync

## Action Items
Alice will review the PR by Friday.
Bob will update the design doc.

## Decisions
We decided to use Supabase for auth.
The team agreed to skip the staging environment.

## Next Steps
Schedule a follow-up for next week.""".strip()


def test_meeting_note_split_by_heading():
    chunks = chunk(MEETING_NOTE, "meeting_note")
    assert len(chunks) > 1
    assert any("Action Items" in c for c in chunks)


def test_slack_thread_is_whole_document():
    text = "Short slack thread about the deploy."
    chunks = chunk(text, "slack_thread")
    assert chunks == [text]


def test_story_is_whole_document():
    text = "As a user I want to search project knowledge."
    chunks = chunk(text, "story")
    assert len(chunks) == 1


def test_unknown_type_uses_recursive_split():
    long_text = "word " * 2000
    chunks = chunk(long_text, "unknown_type")
    assert len(chunks) > 1


def test_all_chunks_nonempty():
    chunks = chunk(MEETING_NOTE, "prd")
    assert all(c.strip() for c in chunks)


def test_presentation_config_exists():
    from vgv_rag.processing.chunker import CHUNKING_CONFIG
    assert "presentation" in CHUNKING_CONFIG


def test_presentation_chunks_by_section():
    text = "# Slide 1\nIntro content\n\n# Slide 2\nMore content here"
    chunks = chunk(text, "presentation")
    assert len(chunks) >= 2
