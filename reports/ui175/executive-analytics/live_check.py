"""Authenticated GET checks for the deployed dashboard; outputs no individual or secret data."""
import hashlib
import json
import random
import socket
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode, urlparse
from urllib.request import ProxyHandler, Request, build_opener

from playwright.sync_api import sync_playwright
from app import config

ROOT = Path(__file__).resolve().parents[3]
BASE = 'http://127.0.0.1:8000'
BUILD = Path('/tmp/toolsauto-executive-analytics-dist')
OUT = Path(__file__).with_name('live-proof.json')
proof = {'checked_at': datetime.now(timezone.utc).isoformat(), 'http': {}, 'periods': {}, 'browser': [],
         'page_errors': [], 'blocked_requests': [],
         'code_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()}


def safe_route(route):
    parsed = urlparse(route.request.url)
    if parsed.hostname != '127.0.0.1' or route.request.method != 'GET':
        proof['blocked_requests'].append({'method': route.request.method, 'path': parsed.path})
        route.abort()
    else:
        route.continue_()


with sync_playwright() as playwright:
    browser = playwright.chromium.launch(headless=True, args=['--no-sandbox'])
    try:
        context = browser.new_context()
        login = context.request.post(BASE + '/login', form={'username': config.ADMIN_USERNAME, 'password': config.ADMIN_PASSWORD})
        proof['login'] = login.status
        assert login.status == 200
        for path in ['/health', '/app', '/api/admin/overview', '/api/admin/processes']:
            response = context.request.get(BASE + path)
            proof['http'][path] = response.status
            assert response.status == 200, path
        for days in (7, 30):
            response = context.request.get(BASE + '/api/admin/executive?days=' + str(days))
            assert response.status == 200
            data = response.json()
            assert not data['errors']
            assert all(data.get(key) is not None for key in ['cashback', 'store', 'studio', 'threads'])
            store, cashback = data['store'], data['cashback']
            assert sum(point['revenue'] for point in store['trend']) == store['revenue']
            assert sum(point['net_profit'] for point in store['trend']) == store['profit']
            assert sum(point['net_commission'] for point in cashback['trend']) == cashback['net_commission']
            assert sum(point['margin'] for point in cashback['trend']) == cashback['margin']
            assert len(store['top_sellers']) <= 5 and len(store['top_profit']) <= 5
            for key in ['store', 'cashback']:
                dates = [point['day'] for point in data[key]['trend']]
                assert dates == sorted(dates)
            proof['periods'][str(days)] = {'http': response.status, 'sources_available': True, 'errors': [],
                'store_buckets': len(store['trend']), 'cashback_buckets': len(cashback['trend']),
                'store_top_sellers': len(store['top_sellers']), 'store_top_profit': len(store['top_profit']),
                'trend_totals_match': True}
        proof['invalid_period_status'] = context.request.get(BASE + '/api/admin/executive?days=14').status
        assert proof['invalid_period_status'] == 422
        manifest = json.loads((BUILD / '.vite/manifest.json').read_text())['index.html']
        assets = [manifest['file'], *manifest['css'], *manifest.get('assets', [])]
        proof['asset_hashes'] = {}
        for asset in assets:
            response = context.request.get(BASE + '/static/admin/' + asset)
            assert response.status == 200
            digest = hashlib.sha256(response.body()).hexdigest()
            assert digest == hashlib.sha256((BUILD / asset).read_bytes()).hexdigest()
            proof['asset_hashes'][asset] = digest
        proof['index_sha256'] = hashlib.sha256(context.request.get(BASE + '/app').body()).hexdigest()
        assert proof['index_sha256'] == hashlib.sha256((BUILD / 'index.html').read_bytes()).hexdigest()
        page = context.new_page()
        page.on('pageerror', lambda error: proof['page_errors'].append(type(error).__name__))
        page.route('**/*', safe_route)
        page.goto(BASE + '/app', wait_until='networkidle')
        for days in (7, 30):
            page.get_by_role('button', name=f'{days} ngày', exact=True).click()
            page.get_by_role('heading', name=f'AI Pass Store · {days} ngày', exact=True).wait_for()
            page.get_by_role('heading', name=f'Cashback · {days} ngày', exact=True).wait_for()
            page.get_by_role('heading', name='Top 5 món bán nhiều', exact=True).wait_for()
            page.get_by_role('heading', name='Tiền Cashback hiện tại', exact=True).wait_for()
            for width in [320, 390, 768, 1440]:
                page.set_viewport_size({'width': width, 'height': 844})
                time.sleep(random.uniform(0.1, 0.2))
                assert not page.evaluate('document.documentElement.scrollWidth > innerWidth'), (days, width)
                for svg in page.locator('[data-chart] svg').all():
                    geometry = svg.evaluate('node => ({width:node.getBoundingClientRect().width, viewWidth:node.viewBox.baseVal.width})')
                    assert abs(geometry['width'] - geometry['viewWidth']) < 2
                selectors = page.locator('[data-chart] select')
                assert selectors.count() == 2
                selectors.first.select_option(index=0)
                proof['browser'].append({'days': days, 'width': width, 'overflow': False, 'chart_geometry': 'PASS'})
        assert not proof['page_errors'] and not proof['blocked_requests']
    finally:
        browser.close()

baseline = json.loads(Path(__file__).with_name('deployment.json').read_text())['processes_before']
apps = json.loads(subprocess.run(['pm2', 'jlist'], capture_output=True, text=True, check=True).stdout)
current = {row['name']: {'pid': row['pid'], 'status': row['pm2_env']['status'], 'restarts': row['pm2_env']['restart_time']} for row in apps}
proof['dashboard'] = current['Web_Dashboard']
assert current['Web_Dashboard']['status'] == 'online'
proof['other_pm2_unchanged'] = all(current.get(name) == info for name, info in baseline.items() if name != 'Web_Dashboard')
assert proof['other_pm2_unchanged']
services = ['store-bot', 'store-api', 'cashback-bot', 'cashback-zalo']
proof['bot_services'] = dict(zip(services, subprocess.check_output(['systemctl', 'is-active', *services], text=True).splitlines()))
assert all(value == 'active' for value in proof['bot_services'].values())

host = 'laptop-t2hf25cd.tail15ebd5.ts.net'
ip = '100.102.93.11'
original = socket.getaddrinfo


def resolve_tailnet(target, *args, **kwargs):
    return original(ip if target == host else target, *args, **kwargs)


socket.getaddrinfo = resolve_tailnet
try:
    opener = build_opener(ProxyHandler({}))
    target = 'https://' + host + ':8443'
    login_request = Request(target + '/login', data=urlencode({'username': config.ADMIN_USERNAME, 'password': config.ADMIN_PASSWORD}).encode(), headers={'Content-Type': 'application/x-www-form-urlencoded'})
    with opener.open(login_request, timeout=20) as response:
        status = response.status
        cookie = response.headers.get('Set-Cookie', '').split(';', 1)[0]
    assert status == 200 and cookie.startswith('session_token=')
    with opener.open(Request(target + '/api/admin/executive?days=30', headers={'Cookie': cookie}), timeout=20) as response:
        body = json.load(response)
        assert response.status == 200 and not body['errors'] and body['store']['trend']
    proof['tailnet'] = {'login': status, 'executive_30d': 200, 'tls_verified': True}
finally:
    socket.getaddrinfo = original
proof['status'] = 'PASS'
OUT.write_text(json.dumps(proof, indent=2) + '\n')
print(json.dumps(proof))
