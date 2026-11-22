"""Offline delivery guards for PLAN189; never opens browser or production storage."""
import copy
import importlib.util
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location("conversation_agent", Path(__file__).resolve().parents[1] / "reports/threads-conversation-20261121/agent.py")
agent = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(agent)
AT = datetime(2026, 11, 21, 16, tzinfo=timezone.utc)


def state():
    return {"enabled": True, "deadline": (AT + timedelta(days=3)).isoformat(), "history": []}


def event(age, author="someone", code="abc", status="posted"):
    return {"at": (AT - timedelta(seconds=age)).isoformat(), "status": status, "author": author, "code": code}


def target():
    text = "Mang cơm đi làm, một câu chuyện cụ thể"
    return {"text": text, "author": "someone", "url": "https://www.threads.com/@someone/post/abc", "sha256": agent.digest(text),
            "taken_at": (AT - timedelta(hours=1)).timestamp(), "likes": 51, "replies": 0, "is_reply": False,
            "can_reply": True, "already_replied": False}


def proposal():
    return {"text": "Bộ hộp này nhìn xong chỉ muốn tới giờ ăn trưa luôn á =)))", "reason": "A relevant observation about the pictured lunchbox.",
            "context_read_at": AT.isoformat(), "url": target()["url"], "parent_sha256": target()["sha256"]}


def test_deadline_and_disabled():
    s = state()
    assert agent.policy_blocks(s, AT + timedelta(days=3)) == ["complete"]
    s["enabled"] = False
    assert agent.policy_blocks(s, AT) == ["disabled"]


def test_unknown_and_attempt_cap():
    s = state()
    s["history"] = [event(9000, status="unknown")]
    assert "paused_or_unknown" in agent.policy_blocks(s, AT)
    s["history"] = [event(9000 + i * 3000, code=str(i)) for i in range(3)]
    assert "daily_cap" in agent.policy_blocks(s, AT)


def test_cooldown_target_author_and_boundary():
    s = state()
    s["history"] = [event(2699)]
    assert "comment_spacing" in agent.policy_blocks(s, AT)
    s["history"] = [event(2700)]
    assert agent.policy_blocks(s, AT) == []
    assert "author_cooldown" in agent.policy_blocks(s, AT, "someone")
    assert "target_attempted" in agent.policy_blocks(s, AT, code="abc")


def test_momentum_age_reply_and_language():
    p = target()
    assert agent.eligible(p, AT)
    for changes in ({"taken_at": (AT - timedelta(hours=49)).timestamp()}, {"likes": 49, "replies": 14}, {"is_reply": True}, {"text": "ordinary English post"}):
        q = {**p, **changes}
        assert not agent.eligible(q, AT)


@pytest.mark.parametrize("change", [{"sha256": "stale"}, {"already_replied": True}, {"can_reply": False}])
def test_stale_parent_cannot_submit(change):
    with pytest.raises(ValueError):
        agent.validate_proposal(proposal(), {**target(), **change}, AT)


@pytest.mark.parametrize("change", [{"text": "Mua ngay https://example.com"}, {"context_read_at": (AT - timedelta(minutes=16)).isoformat()}, {"url": "https://evil.example/@someone/post/abc"}, {"reason": ""}])
def test_bad_draft_cannot_submit(change):
    with pytest.raises(ValueError):
        agent.validate_proposal({**proposal(), **change}, target(), AT)


def test_valid_proposal_and_atomic_state(tmp_path):
    s = state()
    original = copy.deepcopy(s)
    agent.validate_proposal(proposal(), target(), AT)
    agent.save(tmp_path / "state.json", s)
    assert s == original
    assert not (tmp_path / "state.json.tmp").exists()