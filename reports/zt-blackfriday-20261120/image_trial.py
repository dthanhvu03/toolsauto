"""PLAN-182: inspect/prepare one authentic image continuation; never replay an attempt."""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import importlib.util
import json
import random
import re
import sqlite3
import time
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from PIL import Image

from app.features.threads.growth.browser import GrowthBrowser
from app.features.threads.growth.config import DB_PATH
from app.features.threads.growth.session import profile_dir, profile_locked

FOLDER = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("zt_bf182_base", FOLDER / "threads_trial.py")
base = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(base)
PARENT = "https://www.threads.com/@us28qt/post/Df8jAaUCVmk"
PARENT_CODE = "Df8jAaUCVmk"
SLOT = "zt-bf26-threads-image-p1"
WORKER = base.WORKER
REPLY_SELECTOR = 'svg[aria-label="Reply"],svg[aria-label="Trả lời"],svg[title="Reply"]'
MORE_SELECTOR = '[aria-label="More"],[aria-label="Thêm"],svg[title="More"]'
PROFILE_SELECTOR = 'svg[aria-label="Profile"],svg[aria-label="Trang cá nhân"],svg[title="Profile"]'

DOM_MEDIA = r"""() => {
 const rows=[];
 for(const t of document.querySelectorAll('a[href*="/post/"] time')) {
  const a=t.closest('a'); let box=a;
  for(let i=0;i<12 && box?.parentElement;i++) {
   box=box.parentElement;
   if(box.getAttribute('data-pressable-container')==='true') break;
  }
  if(!box) continue;
  rows.push({href:a.getAttribute('href'),text:box.innerText,
   images:[...box.querySelectorAll('img')].filter(x=>x.complete && x.naturalWidth>=250 &&
    x.naturalHeight>=200 && x.getBoundingClientRect().width>=100).length});
 }
 return rows;
}"""


class GuardError(ValueError):
    """Only static, locally authored guard messages may be included in diagnostics."""


def collapsed(value):
    return " ".join(str(value or "").split())


def image_file(m, folder):
    root = Path(folder).resolve()
    path = (root / m["image_path"]).resolve()
    if (not path.is_relative_to(root) or not path.is_file()
            or path.suffix.lower() not in (".png", ".jpg", ".jpeg", ".webp")
            or not 1000 <= path.stat().st_size <= 10_000_000
            or hashlib.sha256(path.read_bytes()).hexdigest() != m.get("image_sha256")):
        raise GuardError("Image path/size/hash mismatch")
    with Image.open(path) as picture:
        if min(picture.size) < 300 or max(picture.size) > 6000:
            raise GuardError("Image dimensions outside reviewed asset limits")
        picture.verify()
    return path


def validate_manifest(m, folder=FOLDER, *, require_image=True):
    if (m.get("plan") != "PLAN-182" or m.get("account") != "us28qt"
            or m.get("slot") != SLOT or m.get("parent_url") != PARENT):
        raise GuardError("Unexpected plan/account/slot/parent")
    original = json.loads((Path(folder) / "manifest.json").read_text())
    if (original.get("status") != "posted" or original.get("post_url") != PARENT
            or hashlib.sha256(original["text"].encode()).hexdigest() != original.get("text_sha256")
            or m.get("parent_text_sha256") != original.get("text_sha256")):
        raise GuardError("Original published parent manifest mismatch")
    if require_image:
        caption = m.get("caption", "")
        if (not isinstance(caption, str) or not 12 <= len(caption) <= 470
                or hashlib.sha256(caption.encode()).hexdigest() != m.get("caption_sha256")
                or re.search(r"\d\s*%|chắc chắn|đảm bảo|đã mua|đã dùng", caption, re.I)
                or any(u != original["invite_url"] for u in re.findall(r"https?://[^\s]+", caption))):
            raise GuardError("Caption hash/copy unsupported")
        prepared = base.stamp(m["prepared_at"])
        if prepared > datetime.now(timezone.utc) + timedelta(minutes=5):
            raise GuardError("Manifest prepared in the future")
        image_file(m, folder)
    return original


def preflight(m, db_path=DB_PATH, folder=FOLDER, *, public=True, idle=True):
    now = datetime.now(timezone.utc)
    role, cfg, limits = base.load_account_roles()["us28qt"], base.load_worker_config(), base.load_limits()
    with closing(sqlite3.connect(Path(db_path).resolve().as_uri() + "?mode=ro", uri=True)) as db:
        rows = db.execute("SELECT posted_at FROM growth_posts WHERE status='posted' AND COALESCE(account,'us28qt')='us28qt' "
                          "UNION ALL SELECT created_at FROM own_posts WHERE status='posted' AND COALESCE(account,'us28qt')='us28qt'").fetchall()
        previous = db.execute("SELECT status FROM own_posts WHERE slot=?", (SLOT,)).fetchone()
    dates = [base.stamp(r[0]) for r in rows if r[0]]
    hour = sum(now - timedelta(hours=1) <= d <= now for d in dates)
    day = sum(now - timedelta(days=1) <= d <= now for d in dates)
    gap = (now - max(dates)).total_seconds() if dates else None
    checks = {"account_active": base.login_active()}
    if idle:
        state = json.loads(base.AGENT_STATUS.read_text())
        checks.update(profile_unlocked=not profile_locked(profile_dir("us28qt")),
                      worker_idle=state.get("phase") in ("waiting", "quiet_hours")
                      and 0 <= (now - base.stamp(state["heartbeat_at"])).total_seconds() <= 180)
    if public:
        checks.update(role=role.enabled and role.own_posts and role.serves("cashbot"), worker_enabled=cfg.enabled,
                      outside_quiet_hours=not base.in_quiet_hours(now, cfg.quiet_hours),
                      hour_budget=hour < (role.max_per_hour if role.max_per_hour is not None else limits.max_replies_per_hour),
                      day_budget=day < (role.max_per_day if role.max_per_day is not None else limits.max_replies_per_day),
                      spacing=gap is None or gap >= limits.min_delay_sec, no_previous_attempt=previous is None)
    return {"observed_at": now.isoformat(), "checks": checks, "blocked": [k for k, v in checks.items() if not v],
            "combined_public_last_hour": hour, "combined_public_last_day": day, "gap_seconds": gap}


def invite_href_matches(href, invite):
    if href == invite:
        return True
    parsed = urlsplit(href or "")
    if parsed.scheme != "https" or parsed.hostname not in ("l.instagram.com", "l.threads.net", "l.threads.com"):
        return False
    values = parse_qs(parsed.query)
    return any(value == invite for key in ("u", "url") for value in values.get(key, []))


def parent_scope_matches(data, original):
    # Threads visibly shortens invitation text; verify the actual anchor separately.
    chunks = [collapsed(line) for line in original["text"].splitlines()
              if line.strip() and not re.search(r"https?://", line)]
    return (data.get("timestamp_codes") == [PARENT_CODE] and data.get("reply_count") == 1
            and data.get("more_count") == 1
            and all(chunk in collapsed(data.get("text")) for chunk in chunks)
            and any(invite_href_matches(href, original["invite_url"]) for href in data.get("hrefs", [])))


def parent_container(browser, original, folder=FOLDER):
    found = base.verify_browser(browser, original, PARENT)
    browser.page.screenshot(path=str(Path(folder) / "image-parent.png"), full_page=False)
    diagnostic = browser.page.evaluate(r"""({code,text}) => {
      const links=[...document.querySelectorAll('a[href*="/post/"]')]
        .filter(a=>(a.getAttribute('href')||'').includes('/post/'+code));
      const target=links.find(a=>a.querySelector('time')) || links[0];
      const ancestors=[]; let e=target;
      for(let i=0;i<8 && e && e.tagName!=='BODY';i++,e=e.parentElement) {
        ancestors.push({tag:e.tagName,role:e.getAttribute('role'),
          pressable:e.getAttribute('data-pressable-container'),
          text:(e.innerText||'').replace(/\s+/g,' ').slice(0,150)});
      }
      return {path:location.pathname,parent_links:links.length,
        timestamp_links:links.filter(a=>a.querySelector('time')).length,
        href:target?.getAttribute('href'),ancestors,
        exact_text_in_body:(document.body.innerText||'').replace(/\s+/g,' ').includes(text)};
    }""", {"code": PARENT_CODE, "text": collapsed(original["text"])})
    diagnostic["payload_parent_found"] = found == PARENT
    base.write_json(Path(folder) / "image-parent-diagnostic.json", diagnostic)
    if found != PARENT:
        raise GuardError("Exact original parent content not verified")
    browser._check_session()
    links = browser.page.locator(f'a[href*="/post/{PARENT_CODE}"]:has(time)')
    if links.count() != 1:
        raise GuardError("Original parent timestamp link missing")
    diagnostic["scope_candidates"] = []
    chunks = [collapsed(line) for line in original["text"].splitlines()
              if line.strip() and not re.search(r"https?://", line)]
    for depth in range(1, 15):
        candidate = links.first.locator(f"xpath=ancestor::*[{depth}]")
        if not candidate.count():
            break
        data = candidate.evaluate(r"""(e,selectors) => ({text:e.innerText,
          timestamp_codes:[...new Set([...e.querySelectorAll('a[href*="/post/"] time')]
            .map(t=>(t.closest('a').getAttribute('href')||'').match(/\/post\/([^/?#]+)/)?.[1]).filter(Boolean))],
          reply_count:[...new Set([...e.querySelectorAll(selectors.reply)]
            .map(x=>x.closest('[role="button"]')||x))].length,
          more_count:[...new Set([...e.querySelectorAll(selectors.more)]
            .map(x=>x.closest('[role="button"]')||x))].length,
          svg_controls:[...e.querySelectorAll('svg')].slice(0,20).map(x=>({
            label:x.getAttribute('aria-label'),labelledby:x.getAttribute('aria-labelledby'),
            labelledby_text:(x.getAttribute('aria-labelledby')||'').split(/\s+/)
              .map(id=>document.getElementById(id)?.textContent||'').join(' ').slice(0,100),
            title:x.getAttribute('title'),child_title:x.querySelector('title')?.textContent,
            role:x.getAttribute('role'),testid:x.getAttribute('data-testid')})),
          button_controls:[...e.querySelectorAll('[role="button"],button')].slice(0,20).map(x=>({
            label:x.getAttribute('aria-label'),labelledby:x.getAttribute('aria-labelledby'),
            title:x.getAttribute('title'),text:(x.innerText||'').replace(/\s+/g,' ').slice(0,80)})),
          hrefs:[...e.querySelectorAll('a[href]')].map(a=>a.href)})""", {"reply": REPLY_SELECTOR, "more": MORE_SELECTOR})
        diagnostic["scope_candidates"].append({"depth": depth, "timestamp_codes": data["timestamp_codes"][:3],
                                               "reply_count": data["reply_count"], "more_count": data["more_count"],
                                               "paragraphs_match": all(chunk in collapsed(data["text"]) for chunk in chunks),
                                               "invite_anchor_match": any(invite_href_matches(href, original["invite_url"])
                                                                          for href in data["hrefs"])})
        if depth >= 7:
            diagnostic["scope_candidates"][-1].update(svg_controls=data["svg_controls"],
                                                       button_controls=data["button_controls"])
        if parent_scope_matches(data, original):
            diagnostic["scope"] = {"ancestor_depth": depth, "timestamp_codes": data["timestamp_codes"],
                                   "reply_count": data["reply_count"], "more_count": data["more_count"],
                                   "paragraphs_and_invite_anchor_verified": True}
            base.write_json(Path(folder) / "image-parent-diagnostic.json", diagnostic)
            return candidate
    base.write_json(Path(folder) / "image-parent-diagnostic.json", diagnostic)
    raise GuardError("Original parent scope ambiguous")


def inspect_parent(browser, original, folder):
    container = parent_container(browser, original, folder)
    browser.page.screenshot(path=str(Path(folder) / "image-parent.png"), full_page=False)
    more = container.locator(MORE_SELECTOR)
    result = {"parent_verified": True, "edit_available": None, "menu_labels": []}
    if more.count():
        more.first.click(timeout=5000)
        time.sleep(random.uniform(0.7, 1.2))
        labels = browser.page.locator('[role="menuitem"]').all_inner_texts()
        result["menu_labels"] = [collapsed(label)[:100] for label in labels[:20]]
        result["edit_available"] = any(re.match(r"^(Edit|Chỉnh sửa)(?:\s|$)", label, re.I) for label in result["menu_labels"])
        browser.page.screenshot(path=str(Path(folder) / "image-parent-menu.png"), full_page=False)
        browser.page.keyboard.press("Escape")
    return result


def preview_count(dialog):
    return dialog.locator("img").evaluate_all("""images => images.filter(x=>x.complete && x.naturalWidth>=300
      && x.naturalHeight>=300 && x.getBoundingClientRect().width>=100).length""")


def prepare_composer(browser, m, original, folder):
    container = parent_container(browser, original, folder)
    reply = container.locator(REPLY_SELECTOR)
    if reply.count() != 1:
        raise GuardError("Exact original parent reply control ambiguous")
    reply.click(timeout=8000)
    time.sleep(random.uniform(1, 2))
    dialog, box = browser._wait_composer_box(10)
    if dialog is None or box is None:
        raise GuardError("A scoped reply dialog is required")
    if "us28qt" not in dialog.inner_text().lower():
        raise GuardError("Reply dialog account/parent context missing")
    if preview_count(dialog):
        raise GuardError("Reply composer already contains media; inspect draft before proceeding")
    box.fill(m["caption"])
    if collapsed(box.inner_text()) != collapsed(m["caption"]):
        raise GuardError("Caption not entered exactly")
    inputs = dialog.locator('input[type="file"]')
    if not inputs.count():
        attach = dialog.locator('svg[aria-label="Attach media"], svg[aria-label="Add media"], '
                                '[role="button"][aria-label*="attach" i], [role="button"][aria-label*="media" i]')
        if not attach.count():
            raise GuardError("Scoped media attach control missing")
        attach.first.click(timeout=5000)
        time.sleep(random.uniform(0.7, 1.2))
        inputs = dialog.locator('input[type="file"]')
    if inputs.count() != 1:
        raise GuardError("Scoped media input missing/ambiguous")
    inputs.set_input_files(str(image_file(m, folder)))
    browser.page.wait_for_function("""() => [...document.querySelectorAll('[role="dialog"] img')]
      .some(x=>x.complete && x.naturalWidth>=300 && x.naturalHeight>=300 && x.getBoundingClientRect().width>=100)""", timeout=20000)
    time.sleep(random.uniform(1, 2))
    if preview_count(dialog) != 1:
        raise GuardError("Exactly one image preview is required")
    browser.page.screenshot(path=str(Path(folder) / "image-composer.png"), full_page=False)
    buttons = dialog.get_by_role("button", name=re.compile(r"^(Post|Đăng)$"))
    if buttons.count() != 1 or not browser.adapter._wait_for_post_button_ready(buttons.first):
        raise GuardError("Scoped Post control missing/disabled/ambiguous")
    return dialog, box, buttons.first


def confirm_composer_identity(browser, dialog):
    """Read current navigation/composer only; discovering the profile would navigate away."""
    chrome_handles = browser.page.evaluate(r"""selector => [...new Set(
      [...document.querySelectorAll(selector)]
        .map(e=>e.closest('a')?.getAttribute('href')||'')
        .map(h=>h.match(/^\/@([^/]+)\/?$/)?.[1]?.toLowerCase()).filter(Boolean))]""", PROFILE_SELECTOR)
    if (chrome_handles != ["us28qt"] or getattr(browser.adapter, "_own_handle", None) != "us28qt"
            or "us28qt" not in dialog.inner_text().lower()):
        raise GuardError("Composer and current navigation identity not verified")


def discard_composer(browser):
    browser.page.keyboard.press("Escape")
    time.sleep(random.uniform(0.4, 0.8))
    discard = browser.page.get_by_role("button", name=re.compile(r"^(Discard|Discard draft|Bỏ|Hủy bỏ)$"))
    if discard.count() == 1 and discard.is_visible():
        discard.click(timeout=5000)
    browser.page.goto(PARENT, wait_until="domcontentloaded", timeout=60000)


def payload_media(payloads, caption):
    result = {}

    def walk(node):
        if isinstance(node, dict):
            code, user = node.get("code"), node.get("user") or {}
            text = node.get("caption") or {}
            if (isinstance(code, str) and isinstance(user, dict) and user.get("username", "").lower() == "us28qt"
                    and isinstance(text, dict) and collapsed(text.get("text")) == collapsed(caption)):
                own = node.get("image_versions2") or {}
                carousel = node.get("carousel_media") or []
                count = int(bool(isinstance(own, dict) and own.get("candidates")))
                count += sum(bool(isinstance(c, dict) and (c.get("image_versions2") or {}).get("candidates")) for c in carousel)
                info = node.get("text_post_app_info") or {}
                references = []
                for owner in (node, info):
                    for key in ("reply_to_id", "reply_to_media_id", "reply_to_post", "replied_to_post"):
                        value = owner.get(key)
                        values = [value] if not isinstance(value, dict) else [value.get(k) for k in ("code", "id", "pk")]
                        references.extend(str(v) for v in values if v is not None and re.fullmatch(r"[A-Za-z0-9_-]{1,80}", str(v)))
                result[code] = {"media_count": count, "is_reply": info.get("is_reply") is True,
                                "reply_to_author": (info.get("reply_to_author") or {}).get("username"),
                                "parent_references": sorted(set(references))}
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    for payload in payloads:
        walk(payload)
    return result


def parent_identifiers(payloads):
    identifiers = {PARENT_CODE}

    def walk(node):
        if isinstance(node, dict):
            if node.get("code") == PARENT_CODE:
                identifiers.update(str(node[k]) for k in ("id", "pk") if node.get(k) is not None)
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    for payload in payloads:
        walk(payload)
    return identifiers


def parent_reference_check(references, identifiers):
    normalized = lambda value: value.split("_", 1)[0] if re.fullmatch(r"\d+_\d+", value) else value
    matches = bool({normalized(value) for value in references} & {normalized(value) for value in identifiers})
    return {"available": bool(references), "verified": matches}


def verify_image(browser, m, original, folder):
    # The parent wrapper now contains its new replies. Keep exact payload/page identity,
    # without reusing the pre-submit requirement that only one timestamp is present.
    if (base.verify_browser(browser, original, PARENT) != PARENT
            or urlsplit(browser.page.url).path.rstrip("/") != urlsplit(PARENT).path):
        raise GuardError("Published image parent page/content not verified")
    time.sleep(random.uniform(2, 3))
    browser.page.mouse.wheel(0, 600)
    time.sleep(random.uniform(1, 2))
    payloads = [*browser._payloads, *browser._embedded_payloads(wide=True)]
    media = payload_media(payloads, m["caption"])
    identifiers = parent_identifiers(payloads)
    rows = browser.page.evaluate(DOM_MEDIA)
    diagnostic = {"parent_path_verified": True, "payload_candidates": media, "dom_candidates": []}
    for row in rows:
        if re.fullmatch(r"/@us28qt/post/[A-Za-z0-9_-]+/?", urlsplit(row.get("href", "")).path):
            diagnostic["dom_candidates"].append({"path": urlsplit(row["href"]).path, "images": row.get("images", 0),
                                                  "caption_matches": collapsed(m["caption"]) in collapsed(row.get("text"))})
    base.write_json(Path(folder) / "image-verification-diagnostic.json", diagnostic)
    browser.page.screenshot(path=str(Path(folder) / "image-published-check.png"), full_page=False)
    for row in rows:
        parsed = urlsplit(row.get("href", "")).path
        match = re.fullmatch(r"/@us28qt/post/([A-Za-z0-9_-]+)/?", parsed)
        if (not match or match[1] == PARENT_CODE or collapsed(m["caption"]) not in collapsed(row.get("text"))
                or row.get("images", 0) < 1):
            continue
        info = media.get(match[1], {})
        if not (info.get("media_count", 0) > 0 and info.get("is_reply")
                and str(info.get("reply_to_author", "")).lower() == "us28qt"):
            continue
        parent_ref = parent_reference_check(info.get("parent_references", []), identifiers)
        if parent_ref["available"] and not parent_ref["verified"]:
            continue
        browser.page.screenshot(path=str(Path(folder) / "image-published.png"), full_page=False)
        return {"post_url": f"https://www.threads.com/@us28qt/post/{match[1]}", "media_count": info["media_count"],
                "caption_verified": True, "parent_page_and_original_text_verified": True,
                "reply_to_own_account_verified": True, "media_payload_and_dom_verified": True,
                "parent_reference_available": parent_ref["available"], "parent_reference_verified": parent_ref["verified"]}
    return None


def claim(m, db_path):
    with closing(sqlite3.connect(Path(db_path).resolve().as_uri() + "?mode=rw", uri=True)) as db:
        db.execute("BEGIN IMMEDIATE")
        if db.execute("SELECT 1 FROM own_posts WHERE slot=?", (SLOT,)).fetchone():
            raise GuardError("Previous image attempt exists; --verify only")
        db.execute("INSERT INTO own_posts(slot,kind,ref,text,status,created_at,account) VALUES(?,?,?,?,?,?,?)",
                   (SLOT, "zt_bf26_image_reply", "parent:" + PARENT_CODE, m["caption"], "unknown",
                    datetime.now(timezone.utc).isoformat(), "us28qt"))
        db.commit()


def save_attempt(proof, folder, db_path):
    base.write_json(Path(folder) / "image-publication.json", proof)
    if proof["status"] == "posted":
        with closing(sqlite3.connect(Path(db_path).resolve().as_uri() + "?mode=rw", uri=True)) as db:
            db.execute("UPDATE own_posts SET status='posted',post_url=?,error_message=NULL WHERE slot=?",
                       (proof["post_url"], SLOT))
            db.commit()


def execute(m, *, mode="preflight", db_path=DB_PATH, folder=FOLDER, browser_factory=GrowthBrowser):
    folder = Path(folder)
    original = validate_manifest(m, folder, require_image=mode != "inspect")
    if mode == "preflight":
        return preflight(m, db_path, folder)
    with (folder / "image.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        is_public = mode in ("prepare", "publish")
        check = preflight(m, db_path, folder, public=is_public)
        if check["blocked"]:
            return {"status": "blocked", "preflight": check}
        if mode == "publish":
            prepared = json.loads((folder / "image-prepare.json").read_text())
            if (prepared.get("status") != "prepared" or any(prepared.get(k) != m.get(k) for k in
                    ("parent_url", "caption_sha256", "image_sha256"))
                    or datetime.now(timezone.utc) - base.stamp(prepared["finished_at"]) > timedelta(hours=2)):
                raise GuardError("Current image/caption require reviewed --prepare first")
        if mode == "verify":
            proof = json.loads((folder / "image-publication.json").read_text())
            if any(proof.get(k) != m.get(k) for k in ("parent_url", "caption_sha256", "image_sha256")):
                raise GuardError("Manifest changed after image attempt")
            if proof.get("status") != "unknown":
                return {"status": "no_verification_needed"}
        else:
            proof = {"status": "not_attempted", "plan": "PLAN-182", "mode": mode, "slot": SLOT,
                     "parent_url": PARENT, "caption_sha256": m.get("caption_sha256"),
                     "image_sha256": m.get("image_sha256"), "attempt_started_at": datetime.now(timezone.utc).isoformat(),
                     "submit_called": False, "preflight": check}
        before, paused, claimed = base.pm2_state(), False, mode == "verify"
        proof["pm2_before"] = before
        try:
            if before[WORKER]["status"] == "online":
                paused = True
                base.pm2_action("stop")
                if base.pm2_state()[WORKER]["status"] != "stopped":
                    raise RuntimeError("Worker did not stop")
            if profile_locked(profile_dir("us28qt")):
                raise RuntimeError("Profile remains busy")
            with browser_factory(str(profile_dir("us28qt"))) as browser:
                live = (browser.adapter._discover_own_handle() or "").lstrip("@").lower()
                if live != "us28qt":
                    raise GuardError("Live identity mismatch")
                browser.adapter._own_handle = live
                proof["verified_live_handle"] = live
                if mode == "inspect":
                    proof.update(inspect_parent(browser, original, folder), status="inspected")
                elif mode in ("prepare", "publish"):
                    try:
                        if mode == "prepare":
                            inspection = inspect_parent(browser, original, folder)
                            proof["parent_inspection"] = inspection
                            base.write_json(folder / "image-edit-inspection.json", inspection)
                            if inspection.get("edit_available") is True:
                                raise GuardError("Edit option exists; inspect media edit before using continuation")
                        dialog, box, button = prepare_composer(browser, m, original, folder)
                    except BaseException:
                        try:
                            browser.page.screenshot(path=str(folder / "image-prepare-error.png"), full_page=False)
                        except Exception:
                            pass
                        raise
                    if mode == "prepare":
                        discard_composer(browser)
                        proof["status"] = "prepared"
                    else:
                        validate_manifest(m, folder)
                        last_check = preflight(m, db_path, folder, public=True, idle=False)
                        if last_check["blocked"]:
                            raise GuardError("Public guard changed before submit")
                        if collapsed(box.inner_text()) != collapsed(m["caption"]):
                            raise GuardError("Caption changed before submit")
                        if preview_count(dialog) != 1:
                            raise GuardError("Image preview changed before submit")
                        confirm_composer_identity(browser, dialog)
                        browser._payloads.clear()
                        claim(m, db_path)
                        claimed = True
                        proof.update(status="unknown", submit_called=True)
                        save_attempt(proof, folder, db_path)
                        button.click(timeout=10000)
                        time.sleep(random.uniform(4, 6))
                        found = verify_image(browser, m, original, folder)
                        if found:
                            proof.update(found, status="posted")
                else:
                    found = verify_image(browser, m, original, folder)
                    if found:
                        proof.update(found, status="posted")
        except BaseException as exc:
            proof["error_type"] = type(exc).__name__
            if isinstance(exc, GuardError):
                proof["error_reason"] = str(exc)
            if not claimed:
                proof["status"] = "not_published"
            if isinstance(exc, (KeyboardInterrupt, SystemExit)):
                raise
        finally:
            try:
                if paused and base.pm2_state()[WORKER]["status"] == "stopped":
                    base.pm2_action("start")
                proof["pm2_after"] = base.pm2_state()
                proof["worker_restored"] = not paused or proof["pm2_after"][WORKER]["status"] == "online"
            except Exception as exc:
                proof.update(worker_restored=False, restore_error_type=type(exc).__name__)
            proof["finished_at"] = datetime.now(timezone.utc).isoformat()
            if claimed:
                save_attempt(proof, folder, db_path)
            else:
                base.write_json(folder / f"image-{mode}.json", proof)
        return proof


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group()
    for name in ("inspect", "prepare", "publish", "verify"):
        modes.add_argument("--" + name, action="store_true")
    args = parser.parse_args()
    mode = next((name for name in ("inspect", "prepare", "publish", "verify") if getattr(args, name)), "preflight")
    m = json.loads((FOLDER / "image-manifest.json").read_text())
    result = execute(m, mode=mode)
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result.get("status") in ("posted", "inspected", "prepared") or mode == "preflight" and not result.get("blocked") else 2


if __name__ == "__main__":
    raise SystemExit(main())
