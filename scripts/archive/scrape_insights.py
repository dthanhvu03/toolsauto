import sys
import os
import re
import base64
import logging
import datetime
from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import app.config as config
from app.utils.url_utils import canonical_fb_url
from zoneinfo import ZoneInfo

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - [INSIGHTS] - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def parse_count(text: str) -> int:
    """Parse FB-style count strings including Vietnamese format.
    '77K' → 77000, '3,6K' → 3600, '1,5 Tr' → 1500000, '970' → 970
    """
    if not text:
        return 0
    text = str(text).strip().upper().replace('\u00a0', ' ')
    m = re.search(r'([\d,\.]+)\s*(K|M|B|TR|N)\b', text)
    if m:
        num_str = m.group(1).replace(',', '.')
        parts = num_str.split('.')
        if len(parts) > 2:
            num_str = ''.join(parts)
        try:
            val = float(num_str)
            suf = m.group(2)
            if suf in ('K', 'N'):    val *= 1_000
            elif suf in ('M', 'TR'): val *= 1_000_000
            elif suf == 'B':         val *= 1_000_000_000
            return int(val)
        except ValueError:
            pass
    m = re.search(r'[\d\.]+', text.replace(',', ''))
    if m:
        try:
            return int(float(m.group()))
        except ValueError:
            pass
    return 0


def decode_relay_str(raw: str) -> str:
    """Decode \\uXXXX escapes in relay store JSON strings.
    Uses json.loads to handle surrogate pairs (emoji like \\uD83D\\uDE00) correctly.
    """
    import json as _json
    try:
        return _json.loads('"' + raw + '"')
    except Exception:
        # Fallback: strip lone surrogates rather than crash
        return re.sub(r'\\u([0-9a-fA-F]{4})', lambda m: chr(int(m.group(1), 16)), raw
                      ).encode('utf-8', errors='replace').decode('utf-8')


def is_view_count_text(text: str) -> bool:
    """Return True only if text looks like a standalone view count (e.g. '77K', '1.2M', '12,345')."""
    NOTIFICATION_KEYWORDS = [
        "chưa đọc", "đánh dấu", "lượt phát", "đã hiển thị",
        "chia sẻ", "theo dõi", "hãy tạo", "phút", "giờ", "ngày", "tuần",
        "tháng", "unread", "mark as read",
    ]
    lower = text.lower()
    if any(kw in lower for kw in NOTIFICATION_KEYWORDS):
        return False
    clean = text.strip().upper().replace(',', '.').replace(' ', '').replace('\n', '')
    return bool(re.match(r'^[\d\.]+[KMBT]?$', clean))


# ─────────────────────────────────────────────────────────────────────────────
# Relay HTML extraction helpers (proven working — see scripts/_dom_debug_run.py)
# ─────────────────────────────────────────────────────────────────────────────

def extract_reel_metrics_from_relay(body_html: str, video_id: str) -> dict:
    """
    Extract comments, shares, likes, caption, creation_time from the Relay Store
    embedded in the page HTML of an individual reel page.

    Returns dict with keys: story_id, comments, shares, likes, caption, creation_time
    All values default to 0/None/'' if not found.
    """
    result = {'story_id': None, 'comments': 0, 'shares': 0,
              'likes': 0, 'caption': '', 'creation_time': None}

    # ── Step 1: Find story_id (scoped to this video) ─────────────────────────
    # Look for post_id where:
    #   - total_comment_count appears in 600 chars BEFORE it
    #   - top_level_post_id=VIDEO_ID appears in 500 chars AFTER it
    story_id = None
    for m in re.finditer(r'"post_id"\s*:\s*"(\d+)"', body_html):
        pid = m.group(1)
        before = body_html[max(0, m.start() - 600): m.start()]
        after  = body_html[m.end(): m.end() + 500]
        cm = re.search(r'"total_comment_count"\s*:\s*(\d+)', before)
        has_top = re.search(
            r'"top_level_post_id[^"]*"\s*:\s*[^"]*"' + re.escape(video_id), after)
        if cm and has_top:
            story_id = pid
            result['story_id'] = story_id
            result['comments'] = int(cm.group(1))
            sm = re.search(r'"share_count_reduced"\s*:\s*"([^"]+)"', before)
            if sm:
                result['shares'] = parse_count(sm.group(1))
            break

    if not story_id:
        return result

    # ── Step 2: Likes via base64-encoded feedback ID ──────────────────────────
    # Relay store uses base64("feedback:STORY_ID") as node key for the reaction block
    story_id_b64 = base64.b64encode(f'feedback:{story_id}'.encode()).decode()
    for b64_m in re.finditer(re.escape(f'"{story_id_b64}"'), body_html):
        lk_m = re.search(
            r'"likers"\s*:\s*\{"count"\s*:\s*(\d+)',
            body_html[b64_m.start(): b64_m.start() + 6000]
        )
        if lk_m:
            result['likes'] = int(lk_m.group(1))
            break

    # ── Step 3: Caption — message.text appears ~500 chars AFTER post_id ──────
    # message.text appears ~500 chars AFTER the first post_id=story_id occurrence
    # Use a 3000-char window so long captions (with \uXXXX escapes, 500+ raw chars) fit
    for pm in re.finditer(r'"post_id"\s*:\s*"' + re.escape(story_id) + r'"', body_html):
        cap_m = re.search(
            r'"message"\s*:\s*\{"text"\s*:\s*"((?:[^"\\]|\\.){10,3000})"',
            body_html[pm.end(): pm.end() + 3000]
        )
        if cap_m:
            result['caption'] = decode_relay_str(cap_m.group(1))
            break
    # Fallback: look in 8000 chars before post_id
    if not result['caption']:
        for pm in re.finditer(r'"post_id"\s*:\s*"' + re.escape(story_id) + r'"', body_html):
            cap_m = re.search(
                r'"message"\s*:\s*\{"text"\s*:\s*"((?:[^"\\]|\\.){10,3000})"',
                body_html[max(0, pm.start() - 8000): pm.start()]
            )
            if cap_m:
                result['caption'] = decode_relay_str(cap_m.group(1))
                break

    # ── Step 4: Published date (creation_time unix timestamp) ─────────────────
    for m in re.finditer(r'"creation_time"\s*:\s*(\d{10})', body_html):
        result['creation_time'] = int(m.group(1))
        break

    return result


def extract_suggested_reels_from_gql(gql_bodies: list) -> list:
    """
    Parse captured GQL NDJSON responses and extract suggested/competitor reel data.
    FB returns ~17 blobs in one large GQL response (~700KB NDJSON).

    Each blob has a "path" field like ["viewer","video_feed_unit_feed","edges",N,...].
    We group blobs by edge index N to correctly assign metrics to each video.
    Video IDs are in "video_id":"<16-digit>" fields (not as URLs in these blobs).

    Returns list of dicts: {reel_url, page_name, page_url, views, likes, comments,
                             shares, caption, published_date}
    """
    import json as _json
    import datetime as _dt

    # edge_idx → accumulated entry for that video
    by_edge = {}

    for body in gql_bodies:
        blobs = [ln for ln in body.splitlines() if ln.strip()]

        # Only process large responses — suggested reel streams have 10+ blobs
        if len(blobs) < 10:
            continue

        for blob_text in blobs:
            # Determine which edge (video position) this blob belongs to
            edge_m = re.search(r'"path"\s*:\s*\[.*?"edges"\s*,\s*(\d+)', blob_text)
            if not edge_m:
                continue
            edge_idx = int(edge_m.group(1))

            entry = by_edge.setdefault(edge_idx, {
                'views': 0, 'likes': 0, 'comments': 0, 'shares': 0
            })

            # ── Video ID — use LAST occurrence in blob.
            # FB blobs carry all previous video_ids as cross-refs; the newest
            # video for this edge is always appended last.
            vid_all = re.findall(r'"video_id"\s*:\s*"?(\d{10,})"?', blob_text)
            if vid_all:
                entry['video_id'] = vid_all[-1]

            # ── Views (often absent; keep for future-proofing) ───────────────
            for key in ('video_view_count', 'play_count', 'view_count', 'watch_count'):
                for m in re.finditer(rf'"{key}"\s*:\s*(\d+)', blob_text):
                    entry['views'] = max(entry['views'], int(m.group(1)))

            # ── Likes ────────────────────────────────────────────────────────
            lk = re.search(r'"likers"\s*:\s*\{"count"\s*:\s*(\d+)', blob_text)
            if lk:
                entry['likes'] = max(entry['likes'], int(lk.group(1)))

            # ── Comments ─────────────────────────────────────────────────────
            cm = re.search(r'"total_comment_count"\s*:\s*(\d+)', blob_text)
            if cm:
                entry['comments'] = max(entry['comments'], int(cm.group(1)))

            # ── Shares ───────────────────────────────────────────────────────
            sh = re.search(r'"share_count_reduced"\s*:\s*"([^"]+)"', blob_text)
            if sh:
                entry['shares'] = max(entry['shares'], parse_count(sh.group(1)))

            # ── Caption ──────────────────────────────────────────────────────
            if not entry.get('caption'):
                for pat in (
                    r'"message"\s*:\s*\{"text"\s*:\s*"((?:[^"\\]|\\.){15,1000})"',
                    r'"description"\s*:\s*\{"text"\s*:\s*"((?:[^"\\]|\\.){15,1000})"',
                ):
                    cap_m = re.search(pat, blob_text)
                    if cap_m:
                        entry['caption'] = decode_relay_str(cap_m.group(1))
                        break

            # ── Page name ────────────────────────────────────────────────────
            if not entry.get('page_name'):
                # Look for name near "owner" or "actors" section
                for nm_pat in (
                    r'"owner"\s*:\s*\{[^}]*"name"\s*:\s*"([^"]{2,80})"',
                    r'"actors"\s*:\s*\[\s*\{[^}]*"name"\s*:\s*"([^"]{2,80})"',
                    r'"name"\s*:\s*"([^"]{2,80})"',
                ):
                    nm = re.search(nm_pat, blob_text)
                    if nm:
                        try:
                            candidate = _json.loads('"' + nm.group(1) + '"')
                        except Exception:
                            candidate = nm.group(1)
                        # Skip hashtags and obviously wrong names
                        if not candidate.startswith('#') and len(candidate) > 2:
                            entry['page_name'] = candidate
                            break

            # ── Published date ────────────────────────────────────────────────
            if not entry.get('published_date'):
                dm = re.search(r'"creation_time"\s*:\s*(\d{10})', blob_text)
                if dm:
                    ts = int(dm.group(1))
                    entry['published_date'] = (
                        _dt.datetime.fromtimestamp(ts).strftime('%Y-%m-%d %H:%M:%S')
                    )

    # Build final list: only entries that have a video_id
    final = []
    for edge_idx in sorted(by_edge.keys()):
        entry = by_edge[edge_idx]
        vid = entry.get('video_id')
        if not vid:
            continue
        final.append({
            'reel_url':       f"https://www.facebook.com/reel/{vid}",
            'page_name':      entry.get('page_name', ''),
            'page_url':       entry.get('page_url', ''),
            'views':          entry.get('views', 0),
            'likes':          entry.get('likes', 0),
            'comments':       entry.get('comments', 0),
            'shares':         entry.get('shares', 0),
            'caption':        entry.get('caption', ''),
            'published_date': entry.get('published_date', ''),
        })

    # Return entries with at least one engagement signal
    return [r for r in final
            if r.get('likes', 0) > 0 or r.get('comments', 0) > 0 or r.get('caption')]


def scrape_reel_detail(page, reel_url: str) -> dict:
    """
    Visit an individual reel page and extract:
      - Primary reel: comments, shares, likes, caption, published_date  (from Relay HTML)
      - Competitor reels: up to 17 suggested reels from FB GQL stream    (from network)

    Returns dict with primary metrics + '_competitor_reels' key.
    """
    video_id_m = re.search(r'/reel/(\d+)', reel_url)
    if not video_id_m:
        return {}
    video_id = video_id_m.group(1)

    gql_bodies = []

    def _on_response(resp):
        if 'graphql' not in resp.url.lower():
            return
        try:
            body = resp.body().decode('utf-8', errors='replace')
            gql_bodies.append(body)
        except Exception:
            pass

    try:
        page.on('response', _on_response)
        page.goto(reel_url, wait_until='domcontentloaded', timeout=30000)
        page.wait_for_timeout(4000)
        body_html = page.inner_html('body')
    except Exception as e:
        logger.warning(f"  reel detail scrape failed for {reel_url}: {e}")
        page.remove_listener('response', _on_response)
        return {}
    finally:
        try:
            page.remove_listener('response', _on_response)
        except Exception:
            pass

    # ── Primary reel metrics (Relay HTML — proven, scoped) ────────────────────
    metrics = extract_reel_metrics_from_relay(body_html, video_id)

    # DOM caption fallback
    if not metrics.get('caption'):
        try:
            # More specific selector for FB Reels caption
            dom_caption = page.evaluate("""() => {
                let best = '', bestLen = 0;
                // Target elements that are likely captions: .x11i5rnm[dir="auto"] or siblings of "See more"
                const candidates = document.querySelectorAll('.x11i5rnm[dir="auto"], .x193iq5w[dir="auto"], [dir="auto"]');
                candidates.forEach(el => {
                    const t = (el.innerText || '').trim();
                    // Basic sanity checks: must have spaces, not be a URL, not be too long/short
                    if (t.length > 5 && t.length < 2500 && t.includes(' ') &&
                        !t.startsWith('http') && (t.match(/\\n/g)||[]).length < 15 &&
                        t.length > bestLen) {
                        
                        // Exclusion list for notification/UI text
                        const low = t.toLowerCase();
                        if (low.includes('chưa đọc') || low.includes('chia sẻ') || 
                            low.includes('theo dõi') || /^views?:/i.test(low)) {
                            return;
                        }
                        
                        bestLen = t.length; 
                        best = t.slice(0, 800); 
                    }
                });
                return best;
            }""")
            if dom_caption:
                metrics['caption'] = dom_caption
        except Exception:
            pass

    # ── Competitor reels (GQL suggested stream) ───────────────────────────────
    metrics['_competitor_reels'] = extract_suggested_reels_from_gql(gql_bodies)
    logger.info(f"    GQL bodies={len(gql_bodies)}, competitor_reels={len(metrics['_competitor_reels'])}")

    return metrics


# ─────────────────────────────────────────────────────────────────────────────
# Main scraper
# ─────────────────────────────────────────────────────────────────────────────

def _save_competitor_reels(db_session, competitor_reels: list, account_id: int):
    """
    Upsert competitor reels harvested from GQL[5] suggested stream.
    Dedup: one row per (reel_url, scrape_date).  If seen again same day → update metrics.
    """
    from app.database.models import CompetitorReel
    from sqlalchemy import text as _sql_text

    today = datetime.date.today().isoformat()

    # Fetch existing reel_urls for today in one query (avoid N+1)
    reel_urls = [cr['reel_url'] for cr in competitor_reels]
    if not reel_urls:
        return

    placeholders = ','.join([f':u{i}' for i in range(len(reel_urls))])
    params = {f'u{i}': u for i, u in enumerate(reel_urls)}
    params['sd'] = today
    existing_rows = db_session.execute(
        _sql_text(f"SELECT reel_url, id FROM competitor_reels "
                  f"WHERE scrape_date=:sd AND reel_url IN ({placeholders})"),
        params
    ).fetchall()
    existing_map = {row[0]: row[1] for row in existing_rows}

    saved = updated = 0
    for cr in competitor_reels:
        reel_url = cr['reel_url']
        if reel_url in existing_map:
            # Update with highest observed values
            db_session.execute(
                _sql_text("""UPDATE competitor_reels
                             SET views=MAX(views,:v), likes=MAX(likes,:lk),
                                 comments=MAX(comments,:cm), shares=MAX(shares,:sh)
                             WHERE id=:rid"""),
                {'v': cr.get('views', 0), 'lk': cr.get('likes', 0),
                 'cm': cr.get('comments', 0), 'sh': cr.get('shares', 0),
                 'rid': existing_map[reel_url]}
            )
            updated += 1
        else:
            obj = CompetitorReel(
                reel_url=reel_url,
                scrape_date=today,
                page_url=cr.get('page_url'),
                views=cr.get('views', 0),
                likes=cr.get('likes', 0),
                comments=cr.get('comments', 0),
                shares=cr.get('shares', 0),
                caption=cr.get('caption', ''),
            )
            db_session.add(obj)
            existing_map[reel_url] = True  # mark as seen within this batch
            saved += 1

    if saved or updated:
        logger.debug(f"    competitor_reels: +{saved} new, {updated} updated")


def scrape_insights_for_page(page, db_session, account_id, target_url, platform="facebook"):
    from app.database.models import PageInsight, now_ts

    logger.info(f"  -> Scraping {platform.upper()}: {target_url}")
    try:
        if platform == "facebook":
            page.goto(target_url.rstrip("/") + "/reels/", timeout=60000)
        else:
            page.goto(target_url.rstrip("/"), timeout=60000)

        page.wait_for_timeout(5000)

        scroll_times = 15 if platform == "facebook" else 5
        for _ in range(scroll_times):
            page.keyboard.press("End")
            page.wait_for_timeout(2000)

        if platform == "facebook":
            js_query = """() => {
                const reels = [];
                document.querySelectorAll('a[href*="/reel/"]').forEach(l => {
                    const text = l.innerText;
                    const aria = l.getAttribute('aria-label') || '';
                    if(text && text.trim().length > 0) {
                        reels.push({
                            href: l.href,
                            text: text.replace(/\\n/g, ' '),
                            aria: aria
                        });
                    }
                });
                return reels;
            }"""
        elif platform == "tiktok":
            js_query = r"""() => {
                const videos = [];
                document.querySelectorAll('div[data-e2e="user-post-item"]').forEach(container => {
                    const link = container.querySelector('a');
                    const viewCount = container.querySelector('[data-e2e="video-views"]')?.innerText || '';
                    if(link && viewCount) {
                        videos.push({href: link.href, text: viewCount.replace(/\n/g, ' ')});
                    }
                });
                if(videos.length === 0) {
                    document.querySelectorAll('a[href*="/video/"]').forEach(l => {
                        const text = l.innerText;
                        if(text && (text.includes('K') || text.includes('M') || /\d/.test(text))) {
                            videos.push({href: l.href, text: text.replace(/\n/g, ' ')});
                        }
                    });
                }
                return videos;
            }"""
        elif platform == "instagram":
            js_query = """() => {
                const reels = [];
                document.querySelectorAll('a[href*="/reel/"], a[href*="/reels/"]').forEach(l => {
                    const text = l.innerText;
                    reels.push({href: l.href, text: text});
                });
                return reels;
            }"""
        else:
            return

        items_data = page.evaluate(js_query)

        valid_items = []
        seen = set()
        for r in items_data:
            href = r['href'].split('?')[0].rstrip('/')
            if href not in seen:
                raw_text = r['text'].strip()
                if not is_view_count_text(raw_text):
                    logger.debug(f"  Skipping: {repr(raw_text[:60])}")
                    continue
                views = parse_count(raw_text)
                if views > 0:
                    seen.add(href)
                    valid_items.append({
                        "url": href,
                        "views": views,
                        "raw_views": raw_text,
                        "aria": r.get('aria', ''),
                    })

        raw_name = target_url.rstrip('/').split('/')[-1]
        if raw_name.startswith('profile.php') or not raw_name:
            raw_name = target_url

        # Timezone-aware day_cutoff (Asia/Ho_Chi_Minh = UTC+7)
        timezone_vn = ZoneInfo(config.TIMEZONE)
        now_vn = datetime.datetime.now(timezone_vn)
        day_cutoff_vn = now_vn.replace(hour=0, minute=0, second=0, microsecond=0)
        day_cutoff = int(day_cutoff_vn.timestamp())

        from sqlalchemy import text as _sql_text
        # GLOBAL dedupe check: check all page_insights from today across ANY page_url
        existing_urls = set(
            row[0]
            for row in db_session.execute(
                _sql_text("SELECT post_url FROM page_insights WHERE recorded_at>=:cutoff"),
                {"cutoff": day_cutoff}
            ).fetchall()
        )
        existing_urls_normalized = {canonical_fb_url(u) for u in existing_urls}

        saved_count = 0
        skipped_dup = 0
        # Visit up to 3 dup reels anyway to capture competitor GQL stream.
        # After competitor data is harvested once we stop (saves time).
        _comp_visits_remaining = 3

        for r in valid_items:
            norm_url = canonical_fb_url(r['url'])
            is_dup = norm_url in existing_urls_normalized
            if is_dup:
                skipped_dup += 1
                # Still visit this reel for competitor data if not yet collected
                if platform != "facebook" or _comp_visits_remaining <= 0:
                    continue
                logger.info(f"    dup reel — visiting for competitor data ({_comp_visits_remaining} left): {norm_url}")
                detail = scrape_reel_detail(page, norm_url)
                competitor_reels = detail.pop('_competitor_reels', [])
                if competitor_reels:
                    _save_competitor_reels(db_session, competitor_reels, account_id)
                    _comp_visits_remaining = 0  # Got data — no need to visit more
                else:
                    _comp_visits_remaining -= 1
                continue

            # ── Grid-level likes (from aria-label) — fallback only ───────────
            likes_grid = 0
            if platform == "facebook" and r.get('aria'):
                like_match = re.search(
                    r'([\d\.,]+)\s*(?:likes|lượt thích|thích)',
                    r['aria'].lower()
                )
                if like_match:
                    likes_grid = parse_count(like_match.group(1))

            # ── Enrich Facebook reels with individual page data ───────────────
            detail = {}
            if platform == "facebook" and r['url']:
                logger.info(f"    enriching reel: {r['url']}")
                detail = scrape_reel_detail(page, r['url'])

            # ── Save competitor reels harvested during this reel visit ─────────
            competitor_reels = detail.pop('_competitor_reels', [])
            if competitor_reels:
                _save_competitor_reels(db_session, competitor_reels, account_id)
                _comp_visits_remaining = 0  # Already got data this page

            # Merge: grid views + detail metrics
            likes = detail.get('likes') or likes_grid
            comments = detail.get('comments', 0)
            shares = detail.get('shares', 0)
            caption = detail.get('caption', '')
            creation_time = detail.get('creation_time')
            published_date = (
                datetime.datetime.fromtimestamp(creation_time).strftime('%Y-%m-%d %H:%M:%S')
                if creation_time else None
            )

            if caption:
                low_cap = caption.lower().strip()
                if re.match(r'^views?:\s*[\d\.]+[kkm]?$', low_cap) or \
                   'chưa đọc' in low_cap or \
                   len(caption) < 5:
                    caption = ""

            insight = PageInsight(
                account_id=account_id,
                platform=platform,
                page_url=target_url,
                page_name=raw_name,
                post_url=norm_url,
                views=r['views'],
                likes=likes,
                comments=comments,
                shares=shares,
                caption=caption,
                published_date=published_date,
                recorded_at=now_ts()
            )
            db_session.add(insight)
            saved_count += 1

        db_session.commit()
        logger.info(f"  ✅ Saved {saved_count} insights (skipped {skipped_dup} dups) for {target_url} ({platform})")

    except Exception as e:
        logger.error(f"  ❌ Error scraping {target_url} ({platform}): {e}")


def main():
    from app.database.core import SessionLocal
    from app.database.models import Account

    logger.info("Initializing Multi-Platform Insights Scraper...")
    with SessionLocal() as db:
        accounts = db.query(Account).filter(Account.is_active == True).all()

        for account in accounts:
            if not account.profile_path:
                continue

            fb_targets = set()
            for p in account.managed_pages_list:
                if p.get("url"): fb_targets.add(p["url"])
            for p in account.target_pages_list:
                if p and "facebook.com" in p: fb_targets.add(p)

            import json
            tk_targets = set()
            if account.competitor_urls:
                try:
                    data = json.loads(account.competitor_urls)
                    if isinstance(data, list):
                        for item in data:
                            url = item.get("url") if isinstance(item, dict) else str(item)
                            if url and "tiktok.com" in url:
                                tk_targets.add(url)
                except Exception:
                    pass

            ig_targets = set()
            if account.platform == "instagram" and account.target_page:
                ig_targets.add(account.target_page)
            for p in account.target_pages_list:
                if p and "instagram.com" in p: ig_targets.add(p)

            if not fb_targets and not tk_targets and not ig_targets:
                continue

            logger.info(f"Opening Profile: Account #{account.id} ({account.name})")
            try:
                with sync_playwright() as pw:
                    context = pw.chromium.launch_persistent_context(
                        user_data_dir=account.profile_path,
                        headless=True,
                        viewport={"width": 1280, "height": 720},
                        args=["--disable-blink-features=AutomationControlled",
                              "--no-first-run", "--disable-infobars"]
                    )
                    page = context.pages[0] if context.pages else context.new_page()

                    for url in fb_targets:
                        scrape_insights_for_page(page, db, account.id, url, platform="facebook")
                    for url in tk_targets:
                        scrape_insights_for_page(page, db, account.id, url, platform="tiktok")
                    for url in ig_targets:
                        scrape_insights_for_page(page, db, account.id, url, platform="instagram")

                    context.close()
            except Exception as e:
                logger.error(f"Error launching browser for {account.name}: {e}")


if __name__ == "__main__":
    main()
