import pytest

from murray3d.mcp_health import (
    McpAuthError,
    ensure_magnific_auth,
    magnific_status,
)

CONNECTED = "claude.ai Magnific: https://mcp.magnific.com - ✔ Connected"
NEEDS = "claude.ai Magnific: https://mcp.magnific.com - ! Needs authentication"
OTHER = "claude.ai Gmail: https://gmailmcp.googleapis.com/mcp/v1 - ✔ Connected"


def test_status_connected():
    ok, detail = magnific_status(runner=lambda: f"{OTHER}\n{CONNECTED}")
    assert ok is True
    assert "magnific" in detail.lower()


def test_status_needs_auth():
    ok, detail = magnific_status(runner=lambda: NEEDS)
    assert ok is False
    assert "Needs authentication" in detail


def test_status_absent_when_not_listed():
    ok, detail = magnific_status(runner=lambda: OTHER)
    assert ok is False
    assert "no está configurado" in detail


def test_ensure_raises_with_reauth_hint():
    with pytest.raises(McpAuthError) as exc:
        ensure_magnific_auth(runner=lambda: NEEDS)
    msg = str(exc.value)
    assert "/mcp" in msg and "claude mcp add" in msg


def test_ensure_ok_when_connected():
    ensure_magnific_auth(runner=lambda: CONNECTED)  # no debe lanzar
