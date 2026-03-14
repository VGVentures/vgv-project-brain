import pytest


@pytest.mark.asyncio
async def test_validate_jwt_returns_email_for_valid_token(mocker):
    mock_client = mocker.MagicMock()
    mock_client.auth.get_user.return_value = mocker.MagicMock(
        user=mocker.MagicMock(email="alice@verygood.ventures"), error=None
    )
    mocker.patch("vgv_rag.server.auth.get_client", return_value=mock_client)

    from vgv_rag.server.auth import validate_jwt
    email = await validate_jwt("valid-token")
    assert email == "alice@verygood.ventures"


@pytest.mark.asyncio
async def test_validate_jwt_raises_for_invalid_token(mocker):
    mock_client = mocker.MagicMock()
    mock_client.auth.get_user.return_value = mocker.MagicMock(
        user=None, error=mocker.MagicMock(message="Invalid JWT")
    )
    mocker.patch("vgv_rag.server.auth.get_client", return_value=mock_client)

    from vgv_rag.server.auth import validate_jwt
    with pytest.raises(PermissionError, match="Unauthorized"):
        await validate_jwt("bad-token")


@pytest.mark.asyncio
async def test_validate_jwt_raises_for_non_vgv_email(mocker):
    mock_client = mocker.MagicMock()
    mock_client.auth.get_user.return_value = mocker.MagicMock(
        user=mocker.MagicMock(email="hacker@evil.com"), error=None
    )
    mocker.patch("vgv_rag.server.auth.get_client", return_value=mock_client)

    from vgv_rag.server.auth import validate_jwt
    with pytest.raises(PermissionError, match="Unauthorized"):
        await validate_jwt("valid-token")
