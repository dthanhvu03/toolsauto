import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { positiveId, sanitizeQuote } from './quote.mjs';

function sample() {
  return {
    item_id: '34', period_start_time: 0, period_end_time: 0,
    batch_item_for_item_card_full: { shopid: '12', itemid: '34', name: 'Public item', currency: 'VND', status: 1, item_status: 'normal', price: '10190000000', price_min: '10190000000', price_max: '20190000000' },
    commission_rate_detail: { seller_commission_detail: { social_media_default_exist_commission_rate: 7000 }, shopee_commission_detail: { social_media_shop_base_exist_commission_rate: 2500 }, channel_cap: { exist_user: { social_media_cap: '4000000000' } } },
    secret: 'private-value', commission_rate: { max_commission_rate: '99%' },
  };
}
const ids = { shopId: '12', itemId: '34' };

test('DTO selects verified context, preserves fixed point and excludes auth/raw', () => {
  const dto = sanitizeQuote(sample(), ids, '2026-11-19T10:00:00Z');
  assert.equal(dto.context, 'social_media_shop_existing');
  assert.equal(dto.seller_rate_raw, '7000');
  assert.equal(dto.platform_rate_raw, '2500');
  assert.equal(dto.platform_cap_raw, '4000000000');
  assert.equal(dto.price_raw, '10190000000');
  assert.equal(dto.fetched_at, '2026-11-19T10:00:00Z');
  assert.equal('last_update' in dto, false);
  assert.equal('updated_at' in dto, false);
  assert.equal(JSON.stringify(dto).includes('private-value'), false);
  assert.equal('max_commission_rate' in dto, false);
});

test('exact item, card item and shop must all match requested identities', () => {
  for (const mutate of [x => { x.item_id = '35'; }, x => { x.batch_item_for_item_card_full.itemid = '35'; }, x => { x.batch_item_for_item_card_full.shopid = '13'; }]) {
    const data = sample(); mutate(data);
    assert.throws(() => sanitizeQuote(data, ids), /identity_mismatch/);
  }
  assert.equal(positiveId(Number.MAX_SAFE_INTEGER + 1), null);
  assert.equal(positiveId(true), null);
  assert.equal(positiveId('01'), null);
});

test('explicit zero seller is valid; missing context split/cap is not', () => {
  const zero = sample(); zero.commission_rate_detail.seller_commission_detail.social_media_default_exist_commission_rate = 0;
  assert.equal(sanitizeQuote(zero, ids).seller_rate_raw, '0');
  for (const value of [null, undefined, '', '0', -1]) {
    const data = sample(); data.commission_rate_detail.channel_cap.exist_user.social_media_cap = value;
    data.commission_rate_detail.commission_cap = '4000000000';
    assert.throws(() => sanitizeQuote(data, ids), /missing_split_or_cap/);
  }
  for (const value of [null, undefined, '', -1, 100001, 'NaN', '7%', '2,5']) {
    const data = sample(); data.commission_rate_detail.shopee_commission_detail.social_media_shop_base_exist_commission_rate = value;
    assert.throws(() => sanitizeQuote(data, ids), /missing_split_or_cap/);
  }
});

test('only VND normal active products with bounded coherent prices', () => {
  for (const [field, value] of [['currency', 'USD'], ['status', 0], ['status', '1'], ['item_status', 'deleted'], ['name', '']]) {
    const data = sample(); data.batch_item_for_item_card_full[field] = value;
    assert.throws(() => sanitizeQuote(data, ids));
  }
  for (const value of ['0', '-100', '1.5', 'NaN']) {
    const data = sample(); data.batch_item_for_item_card_full.price = value;
    assert.throws(() => sanitizeQuote(data, ids), /invalid_price/);
  }
  const reversed = sample(); reversed.batch_item_for_item_card_full.price_min = '99999999999';
  assert.throws(() => sanitizeQuote(reversed, ids), /invalid_price/);
  const period = sample(); period.period_end_time = 'invalid';
  assert.throws(() => sanitizeQuote(period, ids), /invalid_period/);
});

test('eight real POC rate/cap/price/identity fixtures survive the DTO boundary', async () => {
  const text = await readFile(new URL('../../reports/plan177/portal-detail-matched-20261119.jsonl', import.meta.url), 'utf8');
  const records = text.trim().split('\n').map(JSON.parse);
  assert.equal(records.length, 8);
  let nonXtra = 0;
  for (const record of records) {
    const row = record.rows[0];
    const data = { item_id: row.item_id };
    for (const [dotted, value] of Object.entries(row.fields)) {
      const parts = dotted.split('.');
      let pointer = data;
      for (const part of parts.slice(0, -1)) pointer = pointer[part] ??= {};
      pointer[parts.at(-1)] = value;
    }
    // Public product metadata was deliberately omitted by POC capture; only
    // those fields are synthetic. All prices/splits/caps/periods/IDs are real.
    Object.assign(data.batch_item_for_item_card_full, { itemid: row.item_id, shopid: row.shop_id, name: 'POC metadata fixture', currency: 'VND', status: 1, item_status: 'normal' });
    const dto = sanitizeQuote(data, { itemId: row.item_id, shopId: row.shop_id });
    assert.equal(dto.item_id, record.request.params.item_id);
    assert.equal(dto.shop_id, record.expected_shop_id);
    if (dto.seller_rate_raw === '0') nonXtra += 1;
  }
  assert.equal(nonXtra, 1);
});
