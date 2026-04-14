"""
Debug FB Reel — full GraphQL interception.
Captures every network response while the reel page loads, saves dumps,
extracts all metrics fields.

Usage:
    python scripts/_dom_debug_run.py [reel_url] [account_id]
"""
import sys, re, json, os, time, base64
sys.path.insert(0, '/home/vu/toolsauto')

REEL_URL   = sys.argv[1] if len(sys.argv) > 1 else 'https://www.facebook.com/reel/1446114500539267'
ACCOUNT_ID = int(sys.argv[2]) if len(sys.argv) > 2 else 3
PROFILE    = f'/home/vu/toolsauto/content/profiles/facebook_{ACCOUNT_ID}'
DUMP_DIR   = '/tmp/fb_graphql_dump'
os.makedirs(DUMP_DIR, exist_ok=True)

VIDEO_ID = re.search(r'/reel/(\d+)', REEL_URL)
VIDEO_ID = VIDEO_ID.group(1) if VIDEO_ID else None

print(f"Target : {REEL_URL}")
print(f"VideoID: {VIDEO_ID}")
print(f"Profile: {PROFILE}")
print(f"Dumps  : {DUMP_DIR}\n")


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def parse_count(raw):
    """'3,6K' / '1.2M' / '970' → int."""
    raw = str(raw).strip().upper().replace('\u00a0', ' ')
    m = re.search(r'([\d,\.]+)\s*(K|M|B|TR|N)?$', raw)
    if not m:
        return 0
    num_str = m.group(1).replace(',', '.')
    parts = num_str.split('.')
    if len(parts) > 2:
        num_str = ''.join(parts)
    try:
        val = float(num_str)
    except ValueError:
        return 0
    suf = m.group(2) or ''
    if suf in ('K', 'N'):    val *= 1_000
    elif suf in ('M', 'TR'): val *= 1_000_000
    elif suf == 'B':         val *= 1_000_000_000
    return int(val)


def decode_unicode_str(raw: str) -> str:
    """Decode \\uXXXX escapes in a JSON string value."""
    try:
        return re.sub(
            r'\\u([0-9a-fA-F]{4})',
            lambda m: chr(int(m.group(1), 16)),
            raw
        )
    except Exception:
        return raw


def flatten_json(obj, prefix='', sep='.') -> dict:
    """Recursively flatten a nested dict/list to dotted-key dict."""
    items = {}
    if isinstance(obj, dict):
        for k, v in obj.items():
            new_key = f"{prefix}{sep}{k}" if prefix else k
            items.update(flatten_json(v, new_key, sep))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            new_key = f"{prefix}{sep}{i}" if prefix else str(i)
            items.update(flatten_json(v, new_key, sep))
    else:
        items[prefix] = obj
    return items


def grep_metrics(text: str, video_id: str, label: str = '') -> dict:
    """
    Grep a text blob for all FB metric fields.
    Returns dict of found values.
    """
    found = {}

    # ── View count ────────────────────────────────────────────────────────────
    for key in ['video_view_count', 'play_count', 'view_count', 'playback_count',
                'totalPlayCount', 'total_play_count', 'viewCount', 'playerCount',
                'watch_count', 'reach_count']:
        for m in re.finditer(rf'"{key}"\s*:\s*(\d+)', text, re.IGNORECASE):
            found[key] = max(found.get(key, 0), int(m.group(1)))

    # ── Reaction/Like count ───────────────────────────────────────────────────
    for pattern in [
        r'"likers"\s*:\s*\{"count"\s*:\s*(\d+)',
        r'"unified_reactors"\s*:\s*\{"count"\s*:\s*(\d+)',
        r'"reaction_count"\s*:\s*\{"count"\s*:\s*(\d+)',
        r'"reactionCount"\s*:\s*(\d+)',
    ]:
        for m in re.finditer(pattern, text):
            found['likes'] = max(found.get('likes', 0), int(m.group(1)))

    # ── Comment count ─────────────────────────────────────────────────────────
    for m in re.finditer(r'"total_comment_count"\s*:\s*(\d+)', text):
        found['comments'] = max(found.get('comments', 0), int(m.group(1)))

    # ── Share count ───────────────────────────────────────────────────────────
    for m in re.finditer(r'"share_count_reduced"\s*:\s*"([^"]+)"', text):
        v = parse_count(m.group(1))
        found['shares'] = max(found.get('shares', 0), v)
        found['shares_raw'] = m.group(1)

    # ── Caption / message ─────────────────────────────────────────────────────
    for m in re.finditer(r'"(?:message|description|caption)"\s*:\s*\{"text"\s*:\s*"((?:[^"\\]|\\.){20,1000})"', text, re.DOTALL):
        decoded = decode_unicode_str(m.group(1))
        if len(decoded) > len(found.get('caption', '')):
            found['caption'] = decoded

    # ── Published date ────────────────────────────────────────────────────────
    for key in ['creation_time', 'created_time', 'publish_time', 'published_at',
                'story_publish_time', 'backdated_time']:
        for m in re.finditer(rf'"{key}"\s*:\s*(\d{{10}})', text):
            found[key] = int(m.group(1))

    # ── OG / SEO title ────────────────────────────────────────────────────────
    for m in re.finditer(r'"seo_title"\s*:\s*"([^"]{5,200})"', text):
        found['seo_title'] = decode_unicode_str(m.group(1))

    if label and found:
        print(f"  [{label}] found: {list(found.keys())}")

    return found


# ─────────────────────────────────────────────────────────────────────────────
# Playwright — capture ALL responses
# ─────────────────────────────────────────────────────────────────────────────
from playwright.sync_api import sync_playwright, Response, Request

all_responses = []   # Every response: {url, method, status, size, body, req_body}

print("Launching browser (headless)...")
with sync_playwright() as pw:
    ctx = pw.chromium.launch_persistent_context(
        user_data_dir=PROFILE,
        headless=True,
        viewport={'width': 1280, 'height': 900},
        args=['--disable-blink-features=AutomationControlled', '--no-sandbox', '--disable-gpu'],
    )
    page = ctx.pages[0] if ctx.pages else ctx.new_page()

    # Track request bodies (for POST graphql)
    req_bodies: dict[str, str] = {}

    def on_request(req: Request):
        if 'graphql' in req.url.lower() or 'api' in req.url.lower():
            try:
                req_bodies[req.url] = req.post_data or ''
            except Exception:
                pass

    def on_response(resp: Response):
        url = resp.url
        # Skip static assets (images, fonts, video segments)
        if any(ext in url for ext in ['.png', '.jpg', '.woff', '.ico', '.svg',
                                       '.wasm', '.webp', '.mp4', '.m4v']):
            return
        # Skip large video/audio CDN chunks (fbcdn.net media)
        if 'fbcdn.net/o1/v/' in url:
            return
        try:
            body_bytes = resp.body()
            text = body_bytes.decode('utf-8', errors='replace')
            # Flag important endpoints for deep analysis
            is_graphql   = 'graphql' in url.lower()
            is_cvc       = 'unified_cvc' in url or 'view_count' in url
            is_ajax      = '/ajax/' in url and len(text) > 100
            has_video_id = VIDEO_ID in text if VIDEO_ID else False

            all_responses.append({
                'url': url,
                'status': resp.status,
                'size': len(text),
                'body': text,
                'req_body': req_bodies.get(url, '')[:500],
                'has_video_id': has_video_id,
                'is_graphql': is_graphql,
                'is_cvc': is_cvc,
                'is_ajax': is_ajax,
            })

            # Immediately print CVC hits (important!)
            if is_cvc:
                print(f"  [CVC HIT] {url[:80]} → {text[:300]}")
        except Exception:
            pass

    page.on('request', on_request)
    page.on('response', on_response)

    print(f"Navigating...")
    page.goto(REEL_URL, wait_until='networkidle', timeout=60000)
    page.wait_for_timeout(5000)    # wait for lazy data (view count GQL may fire late)
    page.evaluate('window.scrollBy(0, 300)')
    page.wait_for_timeout(3000)    # extra settle after scroll

    # DOM: caption fallback
    dom_caption = page.evaluate("""() => {
        let best = '', bestLen = 0;
        document.querySelectorAll('[dir="auto"]').forEach(el => {
            const t = (el.innerText || '').trim();
            if (t.length > 30 && t.length < 2000 && t.includes(' ') &&
                !t.startsWith('http') && (t.match(/\\n/g)||[]).length < 8 &&
                t.length > bestLen) { bestLen = t.length; best = t.slice(0, 600); }
        });
        return best;
    }""")

    body_html = page.inner_html('body')

    # DOM: try to read view count directly from the rendered page
    dom_views = page.evaluate("""() => {
        // FB Reel view count is near the video player — look for a span with
        // aria-label containing "lượt xem" or "views", or near the play button
        for (const el of document.querySelectorAll('[aria-label]')) {
            const a = el.getAttribute('aria-label') || '';
            if (/l[uư][oợ]t xem|views?/i.test(a)) return a;
        }
        // Fallback: short number spans near the video element
        const video = document.querySelector('video');
        if (video) {
            let node = video.parentElement;
            for (let i = 0; i < 8; i++) {
                if (!node) break;
                const spans = node.querySelectorAll('span, div');
                for (const s of spans) {
                    const t = (s.innerText || '').trim();
                    if (/^[\d,\.]+\s*(K|M|Tr|N|B)?$/i.test(t) && t.length < 10) return t;
                }
                node = node.parentElement;
            }
        }
        return null;
    }""")

    ctx.close()


# ─────────────────────────────────────────────────────────────────────────────
# Analyse all captured responses
# ─────────────────────────────────────────────────────────────────────────────
# Save body_html for offline inspection
html_dump_path = os.path.join(DUMP_DIR, 'body_html.txt')
with open(html_dump_path, 'w', encoding='utf-8') as _f:
    _f.write(body_html)
print(f"body_html saved ({len(body_html):,} bytes) → {html_dump_path}")
print(f"dom_views from DOM = {dom_views!r}\n")

print(f"\nTotal responses captured: {len(all_responses)}")
print(f"Responses containing VideoID: {sum(1 for r in all_responses if r['has_video_id'])}\n")

# Print all URLs (categorised)
print("=== ALL CAPTURED ENDPOINTS ===")
graphql_responses = []
for r in all_responses:
    url_short = r['url'][:100]
    tag = ''
    if r['has_video_id']:
        tag = ' ★ HAS_VIDEO_ID'
    if 'graphql' in r['url'].lower():
        tag += ' [GRAPHQL]'
        graphql_responses.append(r)
    print(f"  [{r['status']}] {r['size']:>7} bytes  {url_short}{tag}")

# ─────────────────────────────────────────────────────────────────────────────
# Deep-dive: GraphQL responses with VideoID
# ─────────────────────────────────────────────────────────────────────────────
print(f"\n=== GRAPHQL RESPONSES ({len(graphql_responses)} total) ===")
gql_metrics = {}

for i, r in enumerate(graphql_responses):
    print(f"\n--- GQL[{i}] {r['url'][:80]} ---")
    print(f"  status={r['status']} size={r['size']} has_video_id={r['has_video_id']}")
    if r['req_body']:
        print(f"  req_body (500 chars): {r['req_body'][:300]}")

    # Save full body to file
    fname = os.path.join(DUMP_DIR, f'gql_{i:02d}.json')
    with open(fname, 'w', encoding='utf-8') as f:
        f.write(r['body'])
    print(f"  → saved: {fname}")

    # Try to parse as NDJSON or JSON
    parsed_blobs = []
    for line in r['body'].splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            parsed_blobs.append(json.loads(line))
        except Exception:
            pass
    if not parsed_blobs:
        try:
            parsed_blobs.append(json.loads(r['body']))
        except Exception:
            pass

    print(f"  parsed {len(parsed_blobs)} JSON blob(s)")

    # Grep metrics from raw body
    m = grep_metrics(r['body'], VIDEO_ID, f'GQL[{i}]')
    if m:
        for k, v in m.items():
            if k not in gql_metrics or v:
                gql_metrics[k] = v

    # Print interesting keys from parsed blobs
    for blob in parsed_blobs[:3]:
        flat = flatten_json(blob)
        interesting = {k: v for k, v in flat.items()
                       if any(kw in k.lower() for kw in
                              ['count', 'view', 'like', 'react', 'share', 'comment',
                               'caption', 'time', 'date', 'publish', 'text'])
                       and v not in (None, '', [], {})}
        if interesting:
            print(f"  interesting fields:")
            for k, v in list(interesting.items())[:20]:
                print(f"    {k} = {repr(v)[:80]}")

# ─────────────────────────────────────────────────────────────────────────────
# CVC / view-count endpoints (non-GraphQL responses with VideoID or is_cvc)
# ─────────────────────────────────────────────────────────────────────────────
print(f"\n=== CVC / NON-GRAPHQL RESPONSES WITH VIDEO_ID ===")
cvc_responses = [r for r in all_responses if r.get('is_cvc') or
                 (r['has_video_id'] and not r['is_graphql'] and r['size'] < 20_000)]
print(f"Found {len(cvc_responses)} candidate(s)\n")

for r in cvc_responses:
    print(f"  URL   : {r['url'][:100]}")
    print(f"  Size  : {r['size']} bytes  status={r['status']}  is_cvc={r['is_cvc']}")
    print(f"  Body  : {r['body'][:400]}")
    # Try JSON parse
    try:
        cvc_data = json.loads(r['body'])
        flat = flatten_json(cvc_data)
        print(f"  JSON keys ({len(flat)}):")
        for k, v in flat.items():
            print(f"    {k} = {repr(v)[:80]}")
        # Grab any view-count-like field
        for key in ['count', 'view_count', 'video_view_count', 'play_count',
                    'cvc', 'certified_view_count', 'totalPlayCount']:
            if key in flat:
                try:
                    gql_metrics['views'] = max(gql_metrics.get('views', 0), int(flat[key]))
                    print(f"  *** VIEWS from {key} = {gql_metrics['views']}")
                except (TypeError, ValueError):
                    pass
    except Exception:
        # Not JSON — grep for metrics
        m_found = grep_metrics(r['body'], VIDEO_ID, f'CVC:{r["url"][-40:]}')
        if m_found:
            for k, v in m_found.items():
                if k not in gql_metrics or v:
                    gql_metrics[k] = v
    print()

# ─────────────────────────────────────────────────────────────────────────────
# Relay HTML parse (scoped — proven working)
# ─────────────────────────────────────────────────────────────────────────────
print(f"\n=== RELAY HTML (inline page data) ===")
html_metrics = grep_metrics(body_html, VIDEO_ID, 'html')

# Scoped post_id extraction (proven approach)
story_id = None
for m in re.finditer(r'"post_id"\s*:\s*"(\d+)"', body_html):
    pid = m.group(1)
    before = body_html[max(0, m.start()-600): m.start()]
    after  = body_html[m.end(): m.end()+500]
    cm = re.search(r'"total_comment_count"\s*:\s*(\d+)', before)
    has_top = re.search(r'"top_level_post_id[^"]*"\s*:\s*[^"]*"' + re.escape(VIDEO_ID), after)
    if cm and has_top:
        story_id = pid
        html_metrics['comments'] = int(cm.group(1))
        sm = re.search(r'"share_count_reduced"\s*:\s*"([^"]+)"', before)
        if sm:
            html_metrics['shares'] = parse_count(sm.group(1))
            html_metrics['shares_raw'] = sm.group(1)
        print(f"  scoped story_id={story_id} comments={html_metrics['comments']} shares={html_metrics.get('shares',0)}")
        break

# Caption: relay text field — message appears ~500 chars AFTER post_id in relay store
if story_id:
    # message.text appears ~500 chars AFTER post_id — use 3000-char window for long captions
    for pm in re.finditer(r'"post_id"\s*:\s*"' + re.escape(story_id) + r'"', body_html):
        cap_m = re.search(
            r'"message"\s*:\s*\{"text"\s*:\s*"((?:[^"\\]|\\.){10,3000})"',
            body_html[pm.end(): pm.end() + 3000]
        )
        if cap_m:
            html_metrics['caption'] = decode_unicode_str(cap_m.group(1))
            print(f"  relay caption: {html_metrics['caption'][:80]!r}")
            break
    # Fallback: look 8000 chars before post_id
    if not html_metrics.get('caption'):
        for pm in re.finditer(r'"post_id"\s*:\s*"' + re.escape(story_id) + r'"', body_html):
            cap_m = re.search(
                r'"message"\s*:\s*\{"text"\s*:\s*"((?:[^"\\]|\\.){10,3000})"',
                body_html[max(0, pm.start() - 8000): pm.start()]
            )
            if cap_m:
                html_metrics['caption'] = decode_unicode_str(cap_m.group(1))
                print(f"  relay caption (before): {html_metrics['caption'][:80]!r}")
                break

if not html_metrics.get('caption') and dom_caption:
    html_metrics['caption'] = dom_caption
    print(f"  dom caption: {dom_caption[:80]!r}")

# Likes: use base64(feedback:story_id) as anchor — relay store encodes node IDs as base64
# "feedback:921667894167902" → base64 → "ZmVlZGJhY2s6OTIxNjY3ODk0MTY3OTAy"
if story_id:
    story_id_b64 = base64.b64encode(f'feedback:{story_id}'.encode()).decode()
    # Search ALL occurrences of b64 id (relay store has it multiple times)
    b64_found = False
    for b64_m in re.finditer(re.escape(f'"{story_id_b64}"'), body_html):
        lk_m = re.search(
            r'"likers"\s*:\s*\{"count"\s*:\s*(\d+)',
            body_html[b64_m.start(): b64_m.start() + 6000]
        )
        if lk_m:
            html_metrics['likes'] = int(lk_m.group(1))
            print(f"  scoped likes (via b64 id)={html_metrics['likes']}")
            b64_found = True
            break
    if not b64_found:
        # Fallback: search for likers.count where raw story_id or b64 id is nearby
        for m in re.finditer(r'"likers"\s*:\s*\{"count"\s*:\s*(\d+)', body_html):
            ctx = body_html[max(0, m.start()-1600): m.end()+400]
            if story_id in ctx or story_id_b64 in ctx:
                html_metrics['likes'] = int(m.group(1))
                print(f"  scoped likes (fallback)={html_metrics['likes']}")
                break
        else:
            print(f"  likes: not found")

# ─────────────────────────────────────────────────────────────────────────────
# Merge GQL + HTML results (GQL takes priority when available)
# ─────────────────────────────────────────────────────────────────────────────
final = {}
all_keys = list(dict.fromkeys(
    ['views', 'likes', 'comments', 'shares', 'shares_raw', 'caption',
     'creation_time', 'seo_title'] + list(gql_metrics.keys()) + list(html_metrics.keys())
))
# Fields where HTML relay (scoped) is MORE reliable than GQL (unscoped multi-reel stream)
HTML_PRIORITY = {'comments', 'shares', 'shares_raw', 'likes', 'caption'}
for k in all_keys:
    gql_val = gql_metrics.get(k)
    html_val = html_metrics.get(k)
    if k in HTML_PRIORITY:
        # HTML relay scoped values are correct; GQL mixes all suggested reels
        final[k] = html_val if html_val is not None else gql_val
    else:
        # GQL preferred (e.g. caption, creation_time, views)
        final[k] = gql_val if gql_val is not None else html_val

# View count: DOM reading is last resort if relay/GQL both missing
if not final.get('views') and dom_views:
    final['views'] = parse_count(dom_views)
    final['views_raw_dom'] = dom_views

# ─────────────────────────────────────────────────────────────────────────────
# Print final result
# ─────────────────────────────────────────────────────────────────────────────
print(f"\n{'='*64}")
print(f"  FINAL RESULT — reel/{VIDEO_ID}")
print(f"{'='*64}")
views_val = final.get('views')
views_str = f"{views_val:,}" if views_val else f"(not found)  dom_raw={dom_views!r}"
print(f"  views    : {views_str}")
print(f"  likes    : {final.get('likes', 0):,}")
print(f"  comments : {final.get('comments', 0):,}")
print(f"  shares   : {final.get('shares', 0):,}  (raw: {final.get('shares_raw','?')!r})")
print(f"  caption  : {str(final.get('caption',''))[:200]!r}")
ts = final.get('creation_time') or final.get('publish_time') or final.get('story_publish_time')
if ts:
    import datetime
    print(f"  date     : {datetime.datetime.fromtimestamp(ts).strftime('%Y-%m-%d %H:%M')}")
else:
    print(f"  date     : (not found)")
print(f"  post_id  : {story_id or VIDEO_ID}")
print()
print("  GQL extra fields:", {k: v for k, v in gql_metrics.items()
                               if k not in ('caption','likes','comments','shares','shares_raw')})

# Save full dump for reference
dump_path = os.path.join(DUMP_DIR, 'final_metrics.json')
with open(dump_path, 'w', encoding='utf-8') as f:
    save_final = {k: v for k, v in final.items() if not isinstance(v, (bytes,))}
    json.dump({'video_id': VIDEO_ID, 'story_id': story_id, 'metrics': save_final}, f,
              ensure_ascii=False, indent=2)
print(f"\n  Full dump saved: {dump_path}")
print(f"  GQL dumps: {DUMP_DIR}/gql_*.json")
