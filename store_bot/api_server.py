"""API cho đại lý: xem sản phẩm, mua bằng số dư của chính họ, giá đã trừ mức giảm của khóa.

Xác thực: header `X-API-Key: sk_…` hoặc `Authorization: Bearer sk_…`.
Gửi `request_id` khi mua: gọi lại cùng request_id (mạng lỗi, timeout) sẽ trả đơn cũ, không trừ tiền lần hai.
Hàng lấy từ FatCat: nguồn chậm thì trả 202 + status "pending"; gọi lại cùng request_id để lấy nốt.

Kèm webhook SePay (`POST /webhooks/sepay`) tự cộng tiền nạp khi có STORE_SEPAY_WEBHOOK_KEY.
Chạy: python -m store_bot.api_server
"""

from __future__ import annotations

import hmac
import logging

import uvicorn
from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from store_bot import messages as msg
from store_bot.bot import StoreBot
from store_bot.config import ConfigError, Settings, default_dotenv, load_settings
from store_bot.db import ApiKey, Order, StoreError, StoreRepository, unit_price
from store_bot.fulfill import Fulfiller
from store_bot.telegram_api import TelegramApi
from store_bot.upstream import FatCatClient

logger = logging.getLogger("store_bot")

ERROR_STATUS = {
    "bad_quantity": 400,
    "insufficient_balance": 402,
    "product_blocked": 403,
    "product_not_found": 404,
    "product_inactive": 409,
    "out_of_stock": 409,
}


class OrderRequest(BaseModel):
    product_id: int
    quantity: int = Field(default=1, ge=1)
    request_id: str | None = Field(default=None, min_length=1, max_length=64)


def _order_json(order: Order) -> dict:
    return {
        "order_id": order.id,
        "product_id": order.product_id,
        "product_name": order.product_name,
        "quantity": order.quantity,
        "unit_price": order.unit_price,
        "total": order.total,
        "items": order.items,
        "balance": order.balance_after,
        "created_at": order.created_at,
        "replayed": order.replayed,
        "status": order.status,
        "refunded": order.refunded,
    }


def create_app(settings: Settings, repo: StoreRepository, telegram: TelegramApi,
               fulfiller: Fulfiller | None = None) -> FastAPI:
    app = FastAPI(title=f"{settings.shop_name} API", docs_url="/docs", redoc_url=None)
    notifier = StoreBot(settings, repo, telegram, bot_username="", fulfiller=fulfiller)

    @app.exception_handler(StoreError)
    def _store_error(_: Request, exc: StoreError) -> JSONResponse:
        return JSONResponse(
            status_code=ERROR_STATUS.get(exc.code, 400),
            content={"error": exc.code, "message": msg.error_text(exc), **exc.info},
        )

    def current_key(x_api_key: str | None = Header(default=None),
                    authorization: str | None = Header(default=None)) -> ApiKey:
        raw = x_api_key or ""
        if not raw and authorization and authorization.lower().startswith("bearer "):
            raw = authorization[7:].strip()
        key = repo.key_for_raw(raw.strip())
        if key is None:
            raise HTTPException(status_code=401, detail="Khóa API sai hoặc đã bị thu hồi.")
        return key

    @app.get("/health")
    def health() -> dict:
        return {"ok": True}

    @app.get("/api/v1/me")
    def me(key: ApiKey = Depends(current_key)) -> dict:
        user = repo.get_user(key.user_id)
        return {
            "user_id": key.user_id,
            "name": key.user_label,
            "balance": user.balance if user else 0,
            "discount_percent": key.discount_bps / 100,
        }

    @app.get("/api/v1/products")
    def products(key: ApiKey = Depends(current_key)) -> dict:
        blocked = repo.blocked_products(key.id)
        return {"products": [
            {
                "id": p.id,
                "name": p.name,
                "description": p.description,
                "price": max(unit_price(p.price, key.discount_bps), p.cost or 0),
                "list_price": p.price,
                "stock": p.stock,
                "max_quantity": min(p.max_quantity or settings.max_order_quantity, settings.max_order_quantity),
            }
            for p in repo.list_products()
            if p.id not in blocked
        ]}

    @app.post("/api/v1/orders")
    def create_order(body: OrderRequest, key: ApiKey = Depends(current_key)):
        if body.quantity > settings.max_order_quantity:
            raise StoreError("bad_quantity", max=settings.max_order_quantity)
        order = repo.buy(
            key.user_id, body.product_id, body.quantity,
            client_ref=f"api:{body.request_id}" if body.request_id else None,
            discount_bps=key.discount_bps, source="api", api_key_id=key.id,
        )
        if order.status == "pending":
            # Đơn hàng FatCat (mới, hoặc gọi lại khi đang chờ): thử lấy hàng ngay trong lượt gọi này.
            order, result, newly = notifier.fulfiller.attempt(order.id)
            if newly:
                try:
                    notifier.report_resolved(order, result, None, None)
                except Exception:
                    logger.exception("[Store] báo admin đơn API lỗi")
        elif not order.replayed:
            try:
                notifier.after_sale(order, repo.get_user(key.user_id))
            except Exception:
                logger.exception("[Store] báo admin đơn API lỗi")
        if order.status == "pending":
            return JSONResponse(status_code=202, content=_order_json(order))
        if order.status == "failed":
            return JSONResponse(status_code=409, content={
                "error": "fulfillment_failed",
                "message": "Nguồn tạm thiếu hàng, đã hoàn tiền vào số dư. Thử lại sau.",
                **_order_json(order),
            })
        return _order_json(order)

    @app.get("/api/v1/orders/{order_id}")
    def get_order(order_id: int, key: ApiKey = Depends(current_key)) -> dict:
        order = repo.get_order(order_id, key.user_id)
        if order is None:
            raise HTTPException(status_code=404, detail="Không tìm thấy đơn.")
        return _order_json(order)

    @app.post("/webhooks/sepay")
    async def sepay(request: Request) -> dict:
        expected = settings.sepay_webhook_key
        given = request.headers.get("authorization") or ""
        if not expected or not hmac.compare_digest(given.encode(), f"Apikey {expected}".encode()):
            raise HTTPException(status_code=401, detail="unauthorized")
        payload = await request.json()
        if payload.get("transferType") != "in":
            return {"success": True}
        amount = int(payload.get("transferAmount") or 0)
        content = str(payload.get("content") or payload.get("description") or "")
        bank_ref = f"sepay:{payload.get('id')}"
        if amount <= 0 or repo.bank_ref_seen(bank_ref):
            return {"success": True}
        topup = repo.find_topup_in_text(content)
        if topup is None or topup.status != "pending":
            notifier.notify_admins(msg.admin_unmatched_transfer(amount, content))
            return {"success": True}
        topup, balance, newly = repo.confirm_topup(topup.id, "sepay", credited=amount, bank_ref=bank_ref)
        if newly:
            notifier.on_topup_credited(topup, balance)
            notifier.notify_admins(f"💳 SePay: nạp #{topup.id} {topup.code} +{msg.vnd(amount)}", quiet=True)
        return {"success": True}

    return app


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [StoreAPI] %(levelname)s %(message)s")
    try:
        settings = load_settings(dotenv_path=default_dotenv())
    except ConfigError as exc:
        logger.error("%s", exc)
        raise SystemExit(2) from exc
    repo = StoreRepository(settings.db_path)
    repo.migrate()
    client = FatCatClient(settings.fatcat_api_url, settings.fatcat_api_key) if settings.fatcat_api_key else None
    app = create_app(settings, repo, TelegramApi(settings.bot_token),
                     Fulfiller(repo, client, settings.fatcat_discount_bps))
    uvicorn.run(app, host=settings.api_host, port=settings.api_port, log_level="info")


if __name__ == "__main__":
    main()
