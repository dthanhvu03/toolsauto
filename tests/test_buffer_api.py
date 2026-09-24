"""Buffer GraphQL client + adapter. HTTP bị mock, không gọi api.buffer.com."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.features.buffer.adapter import BufferAdapter, public_media_url, schedule_mode
from app.features.buffer.client import BufferClient, BufferError, asset_kind


def _response(payload: dict, status: int = 200):
    resp = MagicMock()
    resp.status_code = status
    resp.json.return_value = payload
    return resp


def test_asset_kind_image_and_video():
    assert asset_kind("https://cdn.example/a.JPG?x=1") == "image"
    assert asset_kind("https://cdn.example/clip.mp4") == "video"


def test_create_post_success_and_does_not_send_key_in_body(monkeypatch):
    seen = {}

    def fake_post(url, headers, json, timeout):
        seen["url"] = url
        seen["auth"] = headers["Authorization"]
        seen["body"] = json
        return _response(
            {"data": {"createPost": {"post": {"id": "post_1", "text": "hi", "dueAt": None}}}}
        )

    monkeypatch.setattr("app.features.buffer.client.requests.post", fake_post)
    post = BufferClient("secret-key").create_post(
        text='hello "world"',
        channel_id="chan_1",
        media_url="https://cdn.example/clip.mp4",
    )
    assert post["id"] == "post_1"
    assert seen["auth"] == "Bearer secret-key"
    assert "secret-key" not in seen["body"]["query"]
    assert "https://cdn.example/clip.mp4" in seen["body"]["query"]
    assert "metadata: { facebook: { type: post } }" in seen["body"]["query"]
    assert '\\"world\\"' in seen["body"]["query"] or '"hello \\"world\\""' in seen["body"]["query"]


def test_dang_ngay_gui_lai_chu_video_va_type(monkeypatch):
    seen = {}

    def fake_post(url, headers, json, timeout):
        seen["body"] = json
        return _response({"data": {"editPost": {"post": {"id": "p1", "dueAt": None, "status": "sent"}}}})

    monkeypatch.setattr("app.features.buffer.client.requests.post", fake_post)
    monkeypatch.setattr(
        BufferClient,
        "post_snapshot",
        lambda self, post_id: {
            "id": post_id,
            "text": "caption",
            "assets": [{"source": "https://cdn.example/clip.mp4"}],
            "metadata": {"type": "post"},
        },
    )
    BufferClient("k").edit_post("p1", mode="shareNow")
    query = seen["body"]["query"]
    assert "mode: shareNow" in query
    assert "caption" in query
    assert "https://cdn.example/clip.mp4" in query
    assert "type: post" in query


def test_khong_dang_them_khi_video_da_len(monkeypatch):
    calls = []
    client = BufferClient("k")
    monkeypatch.setattr(
        BufferClient,
        "post_snapshot",
        lambda self, post_id: {
            "id": post_id,
            "status": "error",
            "channelId": "ch",
            "text": "hello video",
            "assets": [{"source": "https://cdn.example/a.mp4"}],
        },
    )
    monkeypatch.setattr(BufferClient, "organizations", lambda self: [{"id": "org"}])
    monkeypatch.setattr(
        BufferClient,
        "execute",
        lambda self, query, variables=None: {
            "posts": {
                "edges": [
                    {
                        "node": {
                            "id": "sent1",
                            "text": "hello video",
                            "sentAt": "2026-09-23T10:39:46.000Z",
                            "externalLink": "https://www.facebook.com/reel/1/",
                            "assets": [{"source": "https://cdn.example/a.mp4"}],
                        }
                    }
                ]
            }
        },
    )

    def edit(self, post_id, *, mode=None, save_to_draft=False):
        calls.append(("edit", mode, save_to_draft))
        return {"id": post_id, "status": "draft"}

    def delete(self, post_id):
        calls.append(("delete", post_id))
        return {"id": post_id}

    monkeypatch.setattr(BufferClient, "edit_post", edit)
    monkeypatch.setattr(BufferClient, "delete_post", delete)
    out = client.publish_now("old")
    assert out["externalLink"] == "https://www.facebook.com/reel/1/"
    assert calls == [("delete", "old")]


def test_create_post_mutation_error(monkeypatch):
    monkeypatch.setattr(
        "app.features.buffer.client.requests.post",
        lambda *a, **k: _response(
            {"data": {"createPost": {"message": "Failed to fetch image dimensions: Not Found"}}}
        ),
    )
    with pytest.raises(BufferError, match="Not Found"):
        BufferClient("k").create_post(text="x", channel_id="c", media_url="https://cdn.example/a.jpg")


def test_http_401(monkeypatch):
    monkeypatch.setattr(
        "app.features.buffer.client.requests.post",
        lambda *a, **k: _response({}, status=401),
    )
    with pytest.raises(BufferError, match="401"):
        BufferClient("k").organizations()


def test_public_media_rejects_local_file():
    job = SimpleNamespace(media_path="/tmp/clip.mp4", processed_media_path=None)
    with pytest.raises(BufferError, match="file local"):
        public_media_url(job)


def test_schedule_future_is_custom():
    mode, due = schedule_mode(SimpleNamespace(schedule_ts=2_000_000_000))
    assert mode == "customScheduled"
    assert due.endswith("Z")


def test_adapter_queues_text_post(monkeypatch):
    client = MagicMock()
    client.create_post.return_value = {"id": "p9", "dueAt": None}
    adapter = BufferAdapter(client)
    job = SimpleNamespace(
        id=9,
        caption="xin chao",
        target_page="chan_9",
        media_path="",
        processed_media_path=None,
        schedule_ts=0,
        account=None,
    )
    monkeypatch.setattr("app.features.buffer.adapter.SAFE_MODE", False)
    result = adapter.publish(job)
    assert result.ok is True
    assert result.external_post_id == "p9"
    client.create_post.assert_called_once()
    kwargs = client.create_post.call_args.kwargs
    assert kwargs["channel_id"] == "chan_9"
    assert kwargs["mode"] == "addToQueue"
    assert kwargs["media_url"] is None


def test_chi_tiet_phan_biet_anh_chu_va_video():
    from app.features.buffer.client import describe_post

    video = describe_post(
        {
            "status": "sent",
            "sentAt": "2026-09-23T10:39:46.000Z",
            "text": "Câu cá",
            "assets": [{"source": "https://cdn.example/a.mp4"}],
            "metrics": [
                {"type": "impressions", "value": 10},
                {"type": "reactions", "value": 1},
                {"type": "comments", "value": 0},
                {"type": "shares", "value": 0},
                {"type": "clicks", "value": 2},
            ],
        },
        page="Mê Câu Cá",
    )
    image = describe_post({"text": "ảnh", "assets": [{"source": "https://cdn.example/a.jpg"}]})
    text = describe_post({"text": "chỉ chữ", "assets": []})
    assert "Video" in video and "1, cảm xúc" not in video
    assert "1 cảm xúc" in video and "2 bấm" in video
    assert image.startswith("<b>Ảnh</b>")
    assert "Chưa có số" in image
    assert text.startswith("<b>Chữ</b>")


def _ban(text, sent, channel="ch"):
    return {
        "text": text,
        "sentAt": sent,
        "channelId": channel,
        "status": "sent",
        "assets": [{"source": "https://cdn.example/a.mp4"}],
        "metrics": [{"type": "impressions", "value": 1}],
    }


def test_nam_ban_cung_ngay_thanh_mot_nhom():
    from app.features.buffer.client import group_sent_posts

    ban = [
        _ban("Câu cá", f"2026-09-23T10:{phut}:00.000Z")
        for phut in ("39", "45", "51", "54", "56")
    ]
    groups = group_sent_posts(ban)
    assert len(groups) == 1
    assert groups[0]["count"] == 5
    assert groups[0]["representative"]["sentAt"].startswith("2026-09-23T10:56")


def test_hai_chu_va_hai_ngay_khong_gop():
    from app.features.buffer.client import group_sent_posts

    hai_chu = [
        _ban("Câu cá", "2026-09-23T10:39:00.000Z"),
        _ban("Nội dung khác", "2026-09-23T11:00:00.000Z"),
    ]
    hai_ngay = [
        _ban("Câu cá", "2026-09-23T10:00:00.000Z"),
        _ban("Câu cá", "2026-09-24T10:00:00.000Z"),
    ]
    assert len(group_sent_posts(hai_chu)) == 2
    assert len(group_sent_posts(hai_ngay)) == 2


def test_tom_tat_mot_noi_dung_nam_ban():
    from app.features.buffer.client import BufferClient, content_count_line

    assert content_count_line(1, 5) == "1 nội dung · 5 bản lịch sử"
    assert "5 nội dung" not in content_count_line(1, 5)
    client = BufferClient.__new__(BufferClient)
    ban = [_ban("Câu cá", f"2026-09-23T10:{phut}:00.000Z") for phut in ("39", "45", "51", "54", "56")]
    text, _channels = client._insights_text(9, {"ch": "Mê Câu Cá"}, ban, False, posts=False)
    assert "1 nội dung" in text
    assert "5 bản lịch sử" in text
    assert "5 nội dung" not in text


def test_adapter_missing_channel_is_fatal():
    adapter = BufferAdapter(MagicMock())
    job = SimpleNamespace(
        id=1,
        caption="x",
        target_page="",
        media_path="",
        processed_media_path=None,
        schedule_ts=0,
        account=SimpleNamespace(target_page=""),
    )
    result = adapter.publish(job)
    assert result.ok is False
    assert result.is_fatal is True
