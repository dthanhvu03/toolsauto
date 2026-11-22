import { BridgeError } from './queue.mjs';

export const QUOTE_CONTEXT = 'social_media_shop_existing';

export function positiveId(value) {
  if (typeof value === 'number' && !Number.isSafeInteger(value)) return null;
  const text = typeof value === 'string' || typeof value === 'number' ? String(value) : '';
  return /^[1-9]\d{0,19}$/.test(text) ? text : null;
}

function whole(value, { positive = false, rate = false } = {}) {
  if (typeof value === 'number' && !Number.isSafeInteger(value)) return null;
  const text = typeof value === 'string' || typeof value === 'number' ? String(value) : '';
  if (!/^\d{1,24}$/.test(text)) return null;
  const number = BigInt(text);
  if (positive && number <= 0n || rate && number > 100000n) return null;
  return number.toString();
}

function epoch(value) {
  const text = whole(value);
  if (text === null || BigInt(text) > 32503680000n) throw new BridgeError('invalid_period');
  return Number(text);
}

export function sanitizeQuote(data, requested, fetchedAt = new Date().toISOString()) {
  if (!data || typeof data !== 'object') throw new BridgeError('invalid_payload');
  const card = data.batch_item_for_item_card_full;
  const item = positiveId(data.item_id);
  const shop = positiveId(card?.shopid);
  if (item !== requested.itemId || shop !== requested.shopId || positiveId(card?.itemid) !== item) {
    throw new BridgeError('identity_mismatch');
  }
  if (card.currency !== 'VND' || card.status !== 1 || card.item_status !== 'normal') {
    throw new BridgeError('unavailable_product');
  }
  const name = typeof card.name === 'string' ? card.name.replace(/[\u0000-\u001f\u007f]/g, '').trim().slice(0, 300) : '';
  if (!name) throw new BridgeError('missing_name');
  const detail = data.commission_rate_detail;
  const seller = whole(detail?.seller_commission_detail?.social_media_default_exist_commission_rate, { rate: true });
  const platform = whole(detail?.shopee_commission_detail?.social_media_shop_base_exist_commission_rate, { rate: true });
  // Zero/empty cap has not been proven to mean a numeric ceiling in this API.
  const cap = whole(detail?.channel_cap?.exist_user?.social_media_cap, { positive: true });
  if (seller === null || platform === null || cap === null) throw new BridgeError('missing_split_or_cap');
  const price = whole(card.price, { positive: true });
  const min = whole(card.price_min, { positive: true });
  const max = whole(card.price_max, { positive: true });
  if ([price, min, max].includes(null) || BigInt(min) > BigInt(max) || BigInt(price) < BigInt(min) || BigInt(price) > BigInt(max)) {
    throw new BridgeError('invalid_price');
  }
  return {
    schema_version: 1,
    source: 'native_shopee',
    context: QUOTE_CONTEXT,
    requested_shop_id: requested.shopId,
    requested_item_id: requested.itemId,
    shop_id: shop,
    item_id: item,
    name,
    currency: card.currency,
    status: card.status,
    item_status: card.item_status,
    price_raw: price,
    price_min_raw: min,
    price_max_raw: max,
    seller_rate_raw: seller,
    platform_rate_raw: platform,
    platform_cap_raw: cap,
    period_start_time: epoch(data.period_start_time),
    period_end_time: epoch(data.period_end_time),
    fetched_at: fetchedAt,
  };
}
