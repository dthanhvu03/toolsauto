"""Vân tay trình duyệt của PlatformSessionManager.launch: headless chạy Chromium đầy đủ, UA kiểu Chrome thật."""
from unittest.mock import MagicMock, patch

import pytest

from app.adapters.common import session as session_mod
from app.adapters.common.session import PlatformSessionManager

REDUCED_UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36"
)


@pytest.fixture
def pw():
    mock_pw = MagicMock()
    mock_pw.chromium.launch.return_value.version = "145.0.7632.6"
    with patch.object(session_mod, "_CHROMIUM_VERSION", None), patch.object(session_mod, "sync_playwright") as sp:
        sp.return_value.start.return_value = mock_pw
        yield mock_pw


def test_reduced_user_agent_keeps_only_major():
    assert session_mod._reduced_user_agent("145.0.7632.6") == REDUCED_UA


def test_headless_uses_full_chromium_and_reduced_ua(pw):
    bundle = PlatformSessionManager.launch("/fake/profile", headless=True)

    assert bundle is not None
    kwargs = pw.chromium.launch_persistent_context.call_args.kwargs
    assert kwargs["channel"] == "chromium"
    assert kwargs["user_agent"] == REDUCED_UA
    assert "HeadlessChrome" not in kwargs["user_agent"]
    assert "--disable-blink-features=AutomationControlled" in kwargs["args"]
    pw.chromium.launch.assert_called_once_with(channel="chromium")


def test_no_fake_fingerprint_init_scripts(pw):
    _, context, _ = PlatformSessionManager.launch("/fake/profile", headless=True)

    context.add_init_script.assert_not_called()


def test_headless_falls_back_to_shell_when_full_chromium_fails(pw):
    good_context = MagicMock()
    pw.chromium.launch_persistent_context.side_effect = [RuntimeError("no chromium"), good_context]

    bundle = PlatformSessionManager.launch("/fake/profile", headless=True)

    assert bundle is not None and bundle[1] is good_context
    first, second = pw.chromium.launch_persistent_context.call_args_list
    assert first.kwargs["channel"] == "chromium"
    assert "channel" not in second.kwargs


def test_headful_keeps_native_ua_and_no_channel(pw):
    PlatformSessionManager.launch("/fake/profile", headless=False)

    kwargs = pw.chromium.launch_persistent_context.call_args.kwargs
    assert "channel" not in kwargs
    assert "user_agent" not in kwargs


def test_explicit_user_agent_wins(pw):
    PlatformSessionManager.launch("/fake/profile", headless=True, user_agent="UA-X")

    assert pw.chromium.launch_persistent_context.call_args.kwargs["user_agent"] == "UA-X"
    pw.chromium.launch.assert_not_called()
