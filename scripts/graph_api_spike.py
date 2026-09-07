#!/usr/bin/env python
"""
Spike Meta Graph API v25.0 — đăng lên Page bằng tay, KHÔNG đụng code tool.

Script độc lập: chỉ cần `requests` + stdlib. Dùng để chạy checklist 6 bước trong
`docs/research/2026-09-07-tich-hop-mien-phi.md` mục 4 (và runbook
`docs/ops/2026-09-07-runbook-tich-hop.md` mục 5).

THỨ TỰ CHẠY 6 BƯỚC
  1. Tài khoản dev MỚI (KHÔNG dùng tài khoản đã bị khoá 31/07) → developers.facebook.com
     → Create App loại Business.                                   (làm tay, trên web)
  2. App › Settings › Basic: Privacy Policy URL, icon 1024x1024, category. (làm tay)
  3. Graph API Explorer → lấy User token với 4 quyền pages_show_list,
     pages_read_engagement, pages_manage_posts, pages_manage_engagement, rồi:
        python scripts/graph_api_spike.py whoami   --token <user_token> --app-id .. --app-secret ..
        python scripts/graph_api_spike.py exchange --token <user_token> --app-id .. --app-secret .. --save
        python scripts/graph_api_spike.py pages    --save
        python scripts/graph_api_spike.py whoami   --token <page_token> --app-id .. --app-secret ..
     → dòng "expires_at" của Page token phải in "Never". Chưa "Never" thì chưa đi tiếp.
  4. App › chuyển sang LIVE MODE (chỉ cần đủ mục ở bước 2, không nộp review), rồi:
        python scripts/graph_api_spike.py post-feed --page-id <id> --message "spike test"
  5. Mở URL bài in ra bằng cửa sổ ẩn danh / tài khoản KHÔNG có role trên app & Page:
        python scripts/graph_api_spike.py verify-public --post-id <post_id> --app-id .. --app-secret ..
     Thấy bài → ĐẠT → báo Anti viết PLAN. Không thấy → ghi lỗi vào bảng runbook, KHÔNG code.
  6. (Tuỳ chọn, sau khi bước 5 đạt) thử ảnh / Reels / comment / lên lịch:
        post-photo, post-reel, comment, post-feed --schedule ...

CẢNH BÁO
  * Dùng TÀI KHOẢN DEV MỚI. Page phải nằm trong Business Manager có >= 2 admin
    (docs/sales/02-checklist-thiet-lap-an-toan.md).
  * App ở Development mode → bài đăng CÔNG CHÚNG KHÔNG THẤY. Phải Live mode.
  * Giới hạn 30 Reels / 24 giờ mỗi Page. Reels 3–90 s, 9:16, >= 540x960.
  * Token lưu ở storage/db/config/graph_api_tokens.json (ngoài git). Không dán token
    vào chat/issue. Script chỉ in 8 ký tự đầu của token.

TOKEN
  Đọc từ `--token`, nếu không có thì từ storage/db/config/graph_api_tokens.json:
      {"page_tokens": {"<page_id>": "..."}, "user_long_lived": "..."}
  Lệnh theo Page (post-*, comment) ưu tiên page_tokens[page_id]; comment/verify lấy
  page_id từ tiền tố của post_id dạng "<page_id>_<post_id>".

Mọi lệnh có `--dry-run`: in request sẽ gửi (token che), không gọi mạng.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

GRAPH_VERSION = "v25.0"
GRAPH_BASE = f"https://graph.facebook.com/{GRAPH_VERSION}"
RUPLOAD_BASE = f"https://rupload.facebook.com/video-upload/{GRAPH_VERSION}"
REELS_POLL_MAX_SEC = 5 * 60
REELS_POLL_EVERY_SEC = 30  # Page moi: BUC ~0, moi lan poll deu dem (docs/notes/2026-09-07-rate-limit-hai-tang.md)
HTTP_TIMEOUT = 60

_REPO_ROOT = Path(__file__).resolve().parents[1]


def _runtime_config_dir() -> Path:
    """RUNTIME_CONFIG_DIR từ app.config nếu import được; fallback storage/db/config."""
    try:
        if str(_REPO_ROOT) not in sys.path:
            sys.path.insert(0, str(_REPO_ROOT))
        from app.config import RUNTIME_CONFIG_DIR  # type: ignore

        return Path(RUNTIME_CONFIG_DIR)
    except Exception:
        return _REPO_ROOT / "storage" / "db" / "config"


TOKEN_FILE = _runtime_config_dir() / "graph_api_tokens.json"


# ----------------------------------------------------------------------------
# Tiện ích
# ----------------------------------------------------------------------------
def mask(token: str | None) -> str:
    if not token:
        return "<none>"
    return token[:8] + "…" + f"({len(token)} ký tự)"


def fmt_expiry(expires_at: Any) -> str:
    try:
        ts = int(expires_at)
    except (TypeError, ValueError):
        return str(expires_at)
    if ts == 0:
        return "Never"
    return datetime.fromtimestamp(ts, tz=timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M %z")


def die(msg: str, code: int = 1) -> None:
    print(f"LỖI: {msg}", file=sys.stderr)
    sys.exit(code)


def load_token_file() -> dict:
    if not TOKEN_FILE.exists():
        return {"page_tokens": {}, "user_long_lived": ""}
    try:
        data = json.loads(TOKEN_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        die(f"{TOKEN_FILE} không phải JSON hợp lệ: {e}")
    data.setdefault("page_tokens", {})
    data.setdefault("user_long_lived", "")
    return data


def save_token_file(data: dict) -> None:
    TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
    TOKEN_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        os.chmod(TOKEN_FILE, 0o600)  # vô hại trên Windows
    except OSError:
        pass
    print(f"Đã ghi {TOKEN_FILE}")


def page_id_from_post(post_id: str) -> str | None:
    if "_" in post_id:
        return post_id.split("_", 1)[0]
    return None


def resolve_token(args: argparse.Namespace, page_id: str | None = None) -> str:
    """--token > page_tokens[page_id] > user_long_lived. Không có → thoát."""
    if getattr(args, "token", None):
        return args.token
    data = load_token_file()
    if page_id and data["page_tokens"].get(page_id):
        return data["page_tokens"][page_id]
    if data["user_long_lived"]:
        print(f"(dùng user_long_lived từ {TOKEN_FILE.name}; Page token không có cho page {page_id})")
        return data["user_long_lived"]
    die(
        f"Không có token. Truyền --token hoặc chạy `pages --save` trước để ghi {TOKEN_FILE}."
    )
    return ""  # unreachable


def app_token(args: argparse.Namespace) -> str | None:
    if getattr(args, "app_id", None) and getattr(args, "app_secret", None):
        return f"{args.app_id}|{args.app_secret}"
    return None


# ----------------------------------------------------------------------------
# HTTP
# ----------------------------------------------------------------------------
def _print_request(method: str, url: str, params: dict | None, data: dict | None,
                   files: dict | None, headers: dict | None) -> None:
    def scrub(d: dict | None) -> dict:
        out = {}
        for k, v in (d or {}).items():
            if k in ("access_token", "input_token", "client_secret", "fb_exchange_token"):
                out[k] = mask(str(v))
            else:
                out[k] = v
        return out

    print(f"[DRY-RUN] {method} {url}")
    if params:
        print("  params :", json.dumps(scrub(params), ensure_ascii=False))
    if data:
        print("  data   :", json.dumps(scrub(data), ensure_ascii=False))
    if files:
        print("  files  :", {k: getattr(v, "name", str(v)) for k, v in files.items()})
    if headers:
        h = dict(headers)
        if "Authorization" in h:
            h["Authorization"] = "OAuth " + mask(h["Authorization"].replace("OAuth ", ""))
        print("  headers:", json.dumps(h, ensure_ascii=False))


def graph(method: str, path: str, *, token: str | None = None, params: dict | None = None,
          data: dict | None = None, files: dict | None = None, headers: dict | None = None,
          dry_run: bool = False, base: str = GRAPH_BASE, raw: bool = False) -> dict:
    """Gọi Graph API. Lỗi → in error.message/code/error_subcode/fbtrace_id, exit 1."""
    url = path if path.startswith("http") else f"{base}/{path.lstrip('/')}"
    params = dict(params or {})
    data = dict(data or {})
    if token:
        if method == "GET":
            params["access_token"] = token
        else:
            data["access_token"] = token
    if dry_run:
        _print_request(method, url, params, data, files, headers)
        return {"dry_run": True}
    try:
        if method == "GET":
            resp = requests.get(url, params=params, headers=headers, timeout=HTTP_TIMEOUT)
        else:
            resp = requests.post(url, params=params or None, data=data or None, files=files,
                                 headers=headers, timeout=HTTP_TIMEOUT)
    except requests.RequestException as e:
        die(f"Mạng: {e}")
    if raw:
        return {"status": resp.status_code, "text": resp.text}
    try:
        body = resp.json()
    except ValueError:
        die(f"HTTP {resp.status_code}, body không phải JSON: {resp.text[:500]}")
    if not resp.ok or (isinstance(body, dict) and "error" in body):
        err = body.get("error", {}) if isinstance(body, dict) else {}
        print(f"LỖI API HTTP {resp.status_code}", file=sys.stderr)
        print(f"  message       : {err.get('message')}", file=sys.stderr)
        print(f"  type          : {err.get('type')}", file=sys.stderr)
        print(f"  code          : {err.get('code')}", file=sys.stderr)
        print(f"  error_subcode : {err.get('error_subcode')}", file=sys.stderr)
        print(f"  fbtrace_id    : {err.get('fbtrace_id')}", file=sys.stderr)
        if err.get("error_user_msg"):
            print(f"  error_user_msg: {err.get('error_user_msg')}", file=sys.stderr)
        if not err:
            print(f"  body: {json.dumps(body, ensure_ascii=False)[:800]}", file=sys.stderr)
        sys.exit(1)
    return body


# ----------------------------------------------------------------------------
# Subcommand
# ----------------------------------------------------------------------------
def cmd_whoami(args: argparse.Namespace) -> None:
    token = resolve_token(args)
    me = graph("GET", "/me", token=token, params={"fields": "id,name"}, dry_run=args.dry_run)
    if not args.dry_run:
        print(f"/me → id={me.get('id')} name={me.get('name')}")
    apptok = app_token(args)
    if not apptok:
        print("(bỏ qua /debug_token — truyền --app-id --app-secret để xem loại token + hạn)")
        return
    dbg = graph("GET", "/debug_token", token=apptok, params={"input_token": token},
                dry_run=args.dry_run)
    if args.dry_run:
        return
    d = dbg.get("data", {})
    print("/debug_token →")
    print(f"  type        : {d.get('type')}")
    print(f"  is_valid    : {d.get('is_valid')}")
    print(f"  app_id      : {d.get('app_id')}")
    print(f"  expires_at  : {fmt_expiry(d.get('expires_at'))}")
    if "data_access_expires_at" in d:
        print(f"  data_access : {fmt_expiry(d.get('data_access_expires_at'))}")
    print(f"  scopes      : {', '.join(d.get('scopes', []))}")
    if d.get("type") == "PAGE" and int(d.get("expires_at", -1) or 0) == 0:
        print("  ✔ Page token không hết hạn — bước 3 đạt.")


def cmd_pages(args: argparse.Namespace) -> None:
    token = resolve_token(args)
    body = graph("GET", "/me/accounts", token=token,
                 params={"fields": "id,name,access_token,tasks", "limit": 100},
                 dry_run=args.dry_run)
    if args.dry_run:
        return
    pages = body.get("data", [])
    if not pages:
        print("Không có Page nào — user token thiếu pages_show_list, hoặc user chưa là admin Page nào.")
        return
    print(f"{'page_id':<20} {'name':<32} {'token(8)':<12} tasks")
    for p in pages:
        print(f"{p.get('id',''):<20} {p.get('name','')[:31]:<32} "
              f"{p.get('access_token','')[:8]:<12} {','.join(p.get('tasks', []))}")
    if args.save:
        data = load_token_file()
        for p in pages:
            if p.get("access_token"):
                data["page_tokens"][p["id"]] = p["access_token"]
        save_token_file(data)
    else:
        print("(thêm --save để ghi Page token vào file)")


def cmd_exchange(args: argparse.Namespace) -> None:
    token = resolve_token(args)
    body = graph("GET", "/oauth/access_token", params={
        "grant_type": "fb_exchange_token",
        "client_id": args.app_id,
        "client_secret": args.app_secret,
        "fb_exchange_token": token,
    }, dry_run=args.dry_run)
    if args.dry_run:
        return
    ll = body.get("access_token", "")
    exp = body.get("expires_in")
    exp_txt = f"{int(exp) // 86400} ngày" if exp else "không trả expires_in (thường ~60 ngày)"
    print(f"long-lived user token: {mask(ll)}  hạn: {exp_txt}")
    if args.save:
        data = load_token_file()
        data["user_long_lived"] = ll
        save_token_file(data)
    else:
        print("(thêm --save để ghi vào file)")


def _epoch_from_iso(s: str) -> int:
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        die(f"--schedule không đúng ISO 8601: {s!r} (vd 2026-09-08T09:00+07:00)")
    if dt.tzinfo is None:
        dt = dt.astimezone()  # coi là giờ máy
    return int(dt.timestamp())


def _post_url(post_id: str) -> str:
    return f"https://www.facebook.com/{post_id}"


def cmd_post_feed(args: argparse.Namespace) -> None:
    token = resolve_token(args, args.page_id)
    data: dict[str, Any] = {"message": args.message}
    if args.link:
        data["link"] = args.link
    if args.schedule:
        epoch = _epoch_from_iso(args.schedule)
        delta = epoch - int(time.time())
        if not (10 * 60 <= delta <= 30 * 86400):
            die("scheduled_publish_time phải cách hiện tại 10 phút → 30 ngày")
        data["published"] = "false"
        data["scheduled_publish_time"] = epoch
    body = graph("POST", f"/{args.page_id}/feed", token=token, data=data, dry_run=args.dry_run)
    if args.dry_run:
        return
    pid = body.get("id")
    print(f"post id : {pid}")
    print(f"URL     : {_post_url(pid)}")
    if args.schedule:
        print("(bài lên lịch — chỉ admin thấy tới giờ đăng)")


def cmd_post_photo(args: argparse.Namespace) -> None:
    token = resolve_token(args, args.page_id)
    path = Path(args.file)
    if not args.dry_run and not path.is_file():
        die(f"Không thấy file {path}")
    data = {"message": args.message}
    if args.dry_run:
        graph("POST", f"/{args.page_id}/photos", token=token, data=data,
              files={"source": path}, dry_run=True)
        return
    with path.open("rb") as fh:
        body = graph("POST", f"/{args.page_id}/photos", token=token, data=data,
                     files={"source": (path.name, fh)})
    print(f"photo id: {body.get('id')}")
    if body.get("post_id"):
        print(f"post id : {body['post_id']}")
        print(f"URL     : {_post_url(body['post_id'])}")


def cmd_post_reel(args: argparse.Namespace) -> None:
    """3 bước theo Reels Publishing API (developers.facebook.com/docs/video-api/guides/reels-publishing)."""
    token = resolve_token(args, args.page_id)
    path = Path(args.file)
    if not args.dry_run and not path.is_file():
        die(f"Không thấy file {path}")
    size = path.stat().st_size if path.is_file() else 0

    # Bước 1: start
    start = graph("POST", f"/{args.page_id}/video_reels", token=token,
                  data={"upload_phase": "start"}, dry_run=args.dry_run)
    video_id = start.get("video_id", "<video_id>")
    upload_url = start.get("upload_url") or f"{RUPLOAD_BASE}/{video_id}"
    if not args.dry_run:
        print(f"[1/3] start → video_id={video_id}")

    # Bước 2: upload binary
    headers = {"Authorization": f"OAuth {token}", "offset": "0", "file_size": str(size)}
    if args.dry_run:
        _print_request("POST", upload_url, None, None, {"<binary>": path}, headers)
    else:
        with path.open("rb") as fh:
            try:
                resp = requests.post(upload_url, headers=headers, data=fh, timeout=600)
            except requests.RequestException as e:
                die(f"Mạng khi upload: {e}")
        try:
            up = resp.json()
        except ValueError:
            die(f"Upload HTTP {resp.status_code}: {resp.text[:500]}")
        if not resp.ok or not up.get("success"):
            err = up.get("error", {}) if isinstance(up, dict) else {}
            die(f"Upload thất bại HTTP {resp.status_code}: message={err.get('message')} "
                f"code={err.get('code')} error_subcode={err.get('error_subcode')} "
                f"fbtrace_id={err.get('fbtrace_id')} body={json.dumps(up)[:300]}")
        print(f"[2/3] upload {size} bytes → success")

    # Bước 3: finish
    finish_data: dict[str, Any] = {
        "upload_phase": "finish",
        "video_id": video_id,
        "video_state": "PUBLISHED",
        "description": args.description,
    }
    if args.schedule:
        finish_data["video_state"] = "SCHEDULED"
        finish_data["scheduled_publish_time"] = _epoch_from_iso(args.schedule)
    fin = graph("POST", f"/{args.page_id}/video_reels", token=token, data=finish_data,
                dry_run=args.dry_run)
    if args.dry_run:
        _print_request("GET", f"{GRAPH_BASE}/{video_id}", {"fields": "status", "access_token": token},
                       None, None, None)
        print(f"[DRY-RUN] poll mỗi {REELS_POLL_EVERY_SEC}s tới status.video_status=ready, tối đa {REELS_POLL_MAX_SEC}s")
        return
    print(f"[3/3] finish → {json.dumps(fin, ensure_ascii=False)}")

    # Poll
    deadline = time.time() + REELS_POLL_MAX_SEC
    while True:
        st = graph("GET", f"/{video_id}", token=token, params={"fields": "status"})
        status = st.get("status", {})
        vs = status.get("video_status")
        phases = {k: (status.get(k) or {}).get("status") for k in
                  ("uploading_phase", "processing_phase", "publishing_phase")}
        print(f"  video_status={vs} {phases}")
        if vs == "ready":
            print(f"Reel sẵn sàng. video_id={video_id}")
            print(f"URL: https://www.facebook.com/reel/{video_id}")
            return
        if vs == "error" or any(v == "error" for v in phases.values()):
            die(f"Reel lỗi: {json.dumps(status, ensure_ascii=False)}")
        if time.time() > deadline:
            die(f"Quá {REELS_POLL_MAX_SEC}s chưa ready. Kiểm tay: GET /{video_id}?fields=status")
        time.sleep(REELS_POLL_EVERY_SEC)


def cmd_comment(args: argparse.Namespace) -> None:
    token = resolve_token(args, page_id_from_post(args.post_id))
    data = {"message": args.message}
    if args.image:
        path = Path(args.image)
        if not args.dry_run and not path.is_file():
            die(f"Không thấy file {path}")
        if args.dry_run:
            graph("POST", f"/{args.post_id}/comments", token=token, data=data,
                  files={"source": path}, dry_run=True)
            return
        with path.open("rb") as fh:
            body = graph("POST", f"/{args.post_id}/comments", token=token, data=data,
                         files={"source": (path.name, fh)})
    else:
        body = graph("POST", f"/{args.post_id}/comments", token=token, data=data,
                     dry_run=args.dry_run)
        if args.dry_run:
            return
    print(f"comment id: {body.get('id')}")


def cmd_verify_public(args: argparse.Namespace) -> None:
    url = _post_url(args.post_id)
    print("KIỂM CÔNG KHAI — bước 5 của spike")
    print(f"  1. Mở cửa sổ ẩn danh (Ctrl+Shift+N), dán: {url}")
    print("  2. Hoặc đăng nhập tài khoản KHÔNG có role trên app lẫn Page, mở cùng URL.")
    print("  3. Thấy bài → ĐẠT. 'Nội dung không khả dụng' → app còn Development mode hoặc bài chưa published.")
    print("  4. Ghi kết quả + ngày vào bảng cuối docs/ops/2026-09-07-runbook-tich-hop.md")
    apptok = app_token(args)
    if not apptok:
        print("(truyền --app-id --app-secret để đọc is_published/privacy bằng app token)")
        return
    body = graph("GET", f"/{args.post_id}", token=apptok,
                 params={"fields": "id,is_published,privacy,created_time,permalink_url"},
                 dry_run=args.dry_run)
    if args.dry_run:
        return
    print("Graph API (app token) →")
    print(f"  is_published : {body.get('is_published')}")
    priv = body.get("privacy") or {}
    print(f"  privacy      : value={priv.get('value')} description={priv.get('description')}")
    print(f"  permalink    : {body.get('permalink_url')}")
    print("  (app token đọc được bài chưa chắc công chúng thấy — vẫn phải mở ẩn danh)")


# ----------------------------------------------------------------------------
# CLI
# ----------------------------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="graph_api_spike.py",
        description=f"Spike Meta Graph API {GRAPH_VERSION} — đăng Page bằng tay, không đụng code tool. "
                    f"Token file: {TOKEN_FILE}",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Thứ tự 6 bước + cảnh báo: xem docstring đầu file hoặc docs/ops/2026-09-07-runbook-tich-hop.md",
    )
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--token", help="access token (mặc định đọc từ file token)")
    common.add_argument("--dry-run", action="store_true", help="in request, không gọi mạng")
    app_args = argparse.ArgumentParser(add_help=False)
    app_args.add_argument("--app-id")
    app_args.add_argument("--app-secret")

    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("whoami", parents=[common, app_args],
                       help="GET /me + /debug_token (loại token, hạn, scopes)")
    s.set_defaults(func=cmd_whoami)

    s = sub.add_parser("pages", parents=[common], help="GET /me/accounts → bảng Page + token (8 ký tự)")
    s.add_argument("--save", action="store_true", help="ghi Page token vào file token")
    s.set_defaults(func=cmd_pages)

    s = sub.add_parser("exchange", parents=[common, app_args], help="đổi user token ngắn → long-lived (60 ngày)")
    s.add_argument("--save", action="store_true")
    s.set_defaults(func=cmd_exchange)

    s = sub.add_parser("post-feed", parents=[common], help="POST /{page-id}/feed")
    s.add_argument("--page-id", required=True)
    s.add_argument("--message", required=True)
    s.add_argument("--link")
    s.add_argument("--schedule", help="ISO 8601, vd 2026-09-08T09:00+07:00 (10 phút → 30 ngày)")
    s.set_defaults(func=cmd_post_feed)

    s = sub.add_parser("post-photo", parents=[common], help="POST /{page-id}/photos (multipart)")
    s.add_argument("--page-id", required=True)
    s.add_argument("--file", required=True)
    s.add_argument("--message", default="")
    s.set_defaults(func=cmd_post_photo)

    s = sub.add_parser("post-reel", parents=[common], help="Reels 3 bước: start → upload → finish, poll tới ready")
    s.add_argument("--page-id", required=True)
    s.add_argument("--file", required=True)
    s.add_argument("--description", default="")
    s.add_argument("--schedule", help="ISO 8601 → video_state=SCHEDULED")
    s.set_defaults(func=cmd_post_reel)

    s = sub.add_parser("comment", parents=[common], help="POST /{post-id}/comments (kèm ảnh: --image)")
    s.add_argument("--post-id", required=True)
    s.add_argument("--message", required=True)
    s.add_argument("--image")
    s.set_defaults(func=cmd_comment)

    s = sub.add_parser("verify-public", parents=[common, app_args],
                       help="hướng dẫn kiểm công khai + đọc is_published/privacy bằng app token")
    s.add_argument("--post-id", required=True)
    s.set_defaults(func=cmd_verify_public)
    return p


def main(argv: list[str] | None = None) -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    args = build_parser().parse_args(argv)
    if args.cmd == "exchange" and not (args.app_id and args.app_secret):
        die("exchange cần --app-id và --app-secret")
    args.func(args)


if __name__ == "__main__":
    main()
