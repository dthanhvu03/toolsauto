"""PLAN-177 read-only comparison. No DB, tokens or raw PD payload exported."""
import json
import os
import sys
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_FLOOR
from pathlib import Path
from dotenv import load_dotenv
from cashback_bot.product_data import ProductDataClient, ProductDataError, ProductQuote, quote_from_payload
from cashback_bot.shopee_url import ShopeeTarget

ROOT = Path(__file__).resolve().parents[2]
REPORT = Path(__file__).resolve().parent

def percent(raw):
    if not isinstance(raw, str) or not raw.strip().endswith('%'):
        return None
    try:
        result = Decimal(raw.strip()[:-1].replace(',', '.'))
    except InvalidOperation:
        return None
    return result if result.is_finite() and 0 <= result <= 100 else None

def vnd(raw):
    return int(Decimal(str(raw)) / Decimal(100_000))

def amount(price, rate):
    return int((Decimal(price) * rate / 100).to_integral_value(rounding=ROUND_FLOOR))

def main():
    load_dotenv(ROOT / '.env')
    key = os.environ.get('ADDLIVETAG_API_KEY')
    if not key:
        raise SystemExit('missing_existing_pd_key')
    client = ProductDataClient(key, os.environ.get('PRODUCT_DATA_URL', 'https://data.addlivetag.com/product-data/product-data.php'), timeout=15, min_interval_sec=0.8)
    lines = (REPORT / sys.argv[1]).read_text(encoding='utf-8-sig').splitlines()
    samples = []
    for record in map(json.loads, lines):
        if not record.get('rows') or not record.get('ids_exact'):
            continue
        for row in record['rows']:
            f = row['fields']
            raw_price = f.get('batch_item_for_item_card_full.price')
            seller = percent(f.get('commission_rate.seller_commission_rate'))
            total = percent(f.get('commission_rate.default_commission_rate'))
            shopee = percent(f.get('commission_rate.shopee_commission_rate'))
            if None in (raw_price, seller, total, shopee):
                continue
            price = vnd(raw_price)
            a = amount(price, total)
            seller_vnd = amount(price, seller)
            b = min(a, seller_vnd + amount(price, Decimal('2.5')))
            c = seller_vnd + min(a - seller_vnd, amount(price, Decimal('2.5')))
            raw_cap = f.get('commission_rate_detail.channel_cap.exist_user.social_media_cap')
            cap = vnd(raw_cap) if raw_cap not in (None, '') else None
            direct_shopee = amount(price, shopee)
            if cap is not None:
                direct_shopee = min(direct_shopee, cap)
            mapped_sure = min(seller_vnd + direct_shopee, seller_vnd + amount(price, Decimal('2.5')))
            sample = {'item_id': row['item_id'], 'shop_id': row['shop_id'], 'portal_fetched_at': record['at'], 'price_vnd': price, 'seller_percent': str(seller), 'default_percent': str(total), 'shopee_percent': str(shopee), 'social_media_cap_vnd': cap, 'A': a, 'B': b, 'C': c, 'mapped_sure_vnd': mapped_sure}
            target = ShopeeTarget(f"https://shopee.vn/product/{row['shop_id']}/{row['item_id']}", int(row['item_id']), int(row['shop_id']), None)
            try:
                now = datetime.now(timezone.utc)
                q = quote_from_payload(client.fetch(target), now, 24)
                exact = q.item_id == target.item_id and q.shop_id == target.shop_id
                sample['pd'] = {'fetched_at': datetime.now(timezone.utc).isoformat(), 'last_update': q.last_update.isoformat(), 'ids_exact': exact, 'price_vnd': q.price_vnd, 'commission_vnd': q.commission_vnd, 'seller_commission_vnd': q.seller_commission_vnd, 'shopee_commission_vnd': q.shopee_commission_vnd, 'sure_commission_vnd': q.sure_commission_vnd, 'is_xtra': q.is_xtra, 'is_capped': q.is_capped, 'source': q.data_source}
                if exact:
                    sample['price_delta_vnd'] = price - q.price_vnd
                    sample['delta_A'] = a - q.sure_commission_vnd
                    sample['delta_B'] = b - q.sure_commission_vnd
                    sample['delta_mapped_sure'] = mapped_sure - q.sure_commission_vnd
            except ProductDataError as exc:
                sample['pd_error'] = exc.code
            samples.append(sample)
            print(json.dumps(sample), flush=True)
    output = {'plan':'PLAN-177','at':datetime.now(timezone.utc).isoformat(),'parse':'Decimal percent; Shopee price/cap scale 100000; amounts floor whole VND','input':sys.argv[1],'samples':samples}
    (REPORT / sys.argv[2]).write_text(json.dumps(output, indent=2) + '\n', encoding='utf8')

def self_check():
    checks = 0
    def check(condition):
        nonlocal checks
        if not condition:
            raise AssertionError('contract check failed')
        checks += 1
    for raw, expected in [('4,5%', Decimal('4.5')), ('0%', Decimal(0)), ('17.01%', Decimal('17.01'))]:
        check(percent(raw) == expected)
    for invalid in ['', None, 'NaN%', 'Infinity%', '-1%', '101%', '7']:
        check(percent(invalid) is None)
    check(vnd('10190000000') == 101900)
    check(vnd('4000000000') == 40000)
    for price, seller_rate, platform_rate, cap, expected in [(138475, '0', '7', 40000, 3461), (159000, '10', '7', 40000, 19875), (2000000, '7', '7', 40000, 180000), (100000, '0', '0', 40000, 0), (99, '7', '2.5', 40000, 8)]:
        seller = amount(price, Decimal(seller_rate))
        platform = min(amount(price, Decimal(platform_rate)), cap)
        current = ProductQuote(item_id=1, shop_id=2, name='contract', price_vnd=price, commission_vnd=seller + platform, last_update=datetime.now(timezone.utc), data_source='api', api_status='success', product_url='https://shopee.vn/product/2/1', seller_commission_vnd=seller, shopee_commission_vnd=platform)
        check(current.sure_commission_vnd == expected)
        check(min(seller + platform, seller + amount(price, Decimal('2.5'))) == expected)
    records = list(map(json.loads, (REPORT / 'portal-detail-matched-20261119.jsonl').read_text().splitlines()))
    check(len(records) == 8)
    for record in records:
        check(record['ids_exact'] is True)
        f = record['rows'][0]['fields']
        for part in ['seller', 'shopee', 'default']:
            check(percent(f['commission_rate.' + part + '_commission_rate']) / 100 == Decimal(f['commission_rate_detail.' + part + '_commission_rate']) / 100000)
    report = json.loads((REPORT / 'portal-detail-compare-20261119.json').read_text())
    check(len(report['samples']) == 8)
    check(sum(s['pd']['is_xtra'] is False for s in report['samples']) >= 1)
    check(all(s['pd']['ids_exact'] and s['delta_mapped_sure'] == 0 and s['price_delta_vnd'] == 0 for s in report['samples']))
    check(sum(s['delta_A'] > 0 for s in report['samples']) == 5)
    print(json.dumps({'contract_checks': checks, 'failures': 0, 'unique_exact_items': 8, 'non_xtra': 1, 'default_as_total_overquotes': 5}))

if __name__ == '__main__':
    if sys.argv[1:] == ['--check']:
        self_check()
    else:
        main()
