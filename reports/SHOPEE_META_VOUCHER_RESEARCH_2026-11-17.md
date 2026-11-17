# Shopee FB/IG voucher link research — 2026-11-17

Research only; no integration implemented. PLAN-173 remains the existing assigned Codex plan, awaiting review; this research is not execution of a new feature plan.

## What was checked

The two signed links supplied by the owner were fetched with unauthenticated GET and manual redirects, restricted to HTTPS Shopee hosts. No Shopee account, purchase, voucher claim, commission sync, provider API call, or Telegram message was used. Probe timestamp: 2026-11-17 04:13:13 UTC (11:13:13 Vietnam). Public documentation and the bot's public Telegram landing page were also read.

Sanitized network evidence is in `SHOPEE_META_VOUCHER_PROOF_2026-11-17.json`. Full payloads, signatures, credential tokens and opaque user/campaign identifiers are excluded. The input hashes identify the supplied signed URLs; the base links alone do not reproduce their signed query.

## Network observations

| Supplied link | Responses | Final path | Affiliate source in redirect |
|---|---|---|---|
| FB: https://s.shopee.vn/5LDXTRkPcG | 301 -> 200 HTML | /opaanlp/209134167/15862874216 | an_17357470550 |
| IG: https://s.shopee.vn/6VPUrMXBoM | 301 -> 200 HTML | /product/209134167/15862874216 | an_17317620047 |

Both target shop 209134167, item 15862874216. Both redirects carry utm_medium=affiliates. These are observed source identifiers, not verified ownership of either account.

The redirects preserve fb_content_id, encrypted_payload, fbclid, channel_type, content_source, content_type and sm_sig_id. The supplied cts values correspond to 11:11:21 VN (FB) and 11:08:02 VN (IG); this does not establish an expiry time.

Control: fetching each short link without its query returns 301 to /opaanlp/209134167/15862874216, retaining its respective affiliate source but with none of fb_content_id/encrypted_payload/sm_sig_id. This separates the short link's affiliate attribution layer from the appended Meta tracking layer. It does not prove the latter activates a discount.

The 200 response is a Shopee HTML application shell. It proves reachability only. No voucher selection, eligibility, remaining quota, discount at checkout, order Sub ID or payable commission was observed. The displayed 22%/24% and 13,615 monthly users are screenshot observations, not independently measured conversion results or guaranteed discounts.

## Public implementation lead — provider claim, not a live test

[AffiPad API docs](https://docs.affipad.com/api) describe POST /v1/convert, own affiliate configuration, subId, FB/IG presets and signing. In trackingOnly mode, affiliate/Sub ID must already be in the input URL; separate Sub ID arguments are ignored. Other query parameters are signature-covered. This is a third-party capability claim, not proof of Shopee approval, voucher acceptance, or that Bot San Sale uses AffiPad. No API key or quota was used.

[Official Shopee Vietnam help](https://help.shopee.vn/portal/10/article/190889-%C4%90%E1%BB%91i-t%C3%A1c-li%C3%AAn-k%E1%BA%BFt-Facebook-Facebook-Affiliate-Partnership) confirms an eligible-creator Facebook/Instagram partnership and commission on valid recorded orders. It does not document a bot-proxy workflow or establish validity of these third-party samples.

The public page https://t.me/San_coupon_bot identifies Bot San Sale but exposes no implementation provider. No messages were sent to the bot. No documented YouTube equivalent was established in this research.

## Current Cashbot integration implications

- cashback_bot/affiliate.py:16 creates case-sensitive 8-character alphanumeric Sub IDs; :24 builds an owner-affiliate redirect from a canonical product URL. Preserve exact Sub ID matching for cashback reconciliation.
- cashback_bot/affiliate.py:43 uses shared VOUCHERS for the generic voucher entry. This is unsuitable for customer-specific purchase attribution.
- cashback_bot/shopee_url.py:67 removes query parameters from short links; :99 constructs canonical product URLs. Existing standard conversion cannot be assumed to preserve a supplied Meta bundle.
- cashback_bot/sale_relay.py:87 and :175 strip affiliate/utm tracking before rewrapping. Signed output must not subsequently pass through this cleaning flow.
- cashback_bot/shopee_shortener.py provides the existing logged-in-account shortener bridge, not a Meta signature implementation. It was not invoked.
- No existing AffiPad/fb_reels/ig_reels/sm_sig_id integration was found in the inspected application code.

Working hypothesis: the observed bot combines an affiliate short link with a channel-specific tracking/signature bundle. Its backend, signature source, voucher checks and handling of failed vouchers remain unknown. Forwarding to the competitor bot and then changing attribution is therefore not an established solution.

## Proposed limited proof of concept — not executed

Customer product -> resolve product -> choose FB/IG -> generate owner affiliate link with the existing unique customer Sub ID -> add/sign the channel bundle -> return unchanged.

Before customer rollout, use one owner-controlled product case to verify all of: owner affiliate account in the generated result, exact Sub ID retained, actual voucher eligibility and applied discount in Shopee, then a legitimate order's affiliate report matching that Sub ID. Do not infer cashback entitlement from click success or quoted voucher percentage. Any real purchase remains the owner's action.

Create an assigned integration PLAN only after choosing the provider/official path and reviewing this proof. Do not change pricing, wallet accounting, shared voucher Sub ID, current customer experiments or schema as part of research.
