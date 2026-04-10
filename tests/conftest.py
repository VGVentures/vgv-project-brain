import pytest
from unittest.mock import MagicMock
from dotenv import load_dotenv


@pytest.fixture(autouse=True)
def load_env():
    load_dotenv(override=False)


@pytest.fixture
def mock_supabase(mocker):
    mock = MagicMock()
    mocker.patch("vgv_rag.storage.supabase_queries.get_client", return_value=mock)
    return mock
