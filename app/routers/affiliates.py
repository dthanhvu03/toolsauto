from fastapi import APIRouter, Depends, Request, Form
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
import logging
import time

from app.database.core import get_db
from app.database.models import AffiliateLink
from app.main_templates import templates

router = APIRouter(prefix="/affiliates", tags=["affiliates"])
logger = logging.getLogger(__name__)

from pydantic import BaseModel
from typing import List, Optional
import json
import re
from app.services.gemini_rpa import GeminiRPAService
from app.services.gemini_api import GeminiAPIService

class BatchItem(BaseModel):
    keyword: str
    affiliate_url: str
    comment: Optional[str] = None
    commission_rate: Optional[float] = None

class BatchImportRequest(BaseModel):
    items: List[BatchItem]

class AIGenerateRequest(BaseModel):
    product_name: str
    category: str
    price: str
    commission_rate: float

@router.get("/", response_class=HTMLResponse)
def get_affiliates_page(request: Request):
    """Main page for Affiliate Links management."""
    return templates.TemplateResponse("pages/app_affiliates.html", {
        "request": request,
        "active_tab": "affiliates",
        "csv_import_enabled": True,
        "ai_generate_enabled": True
    })

@router.get("/table", response_class=HTMLResponse)
def get_affiliates_table(request: Request, q: str = "", page: int = 1, db: Session = Depends(get_db)):
    """HTMX fragment for the table of affiliate links."""
    limit = 25
    offset = (page - 1) * limit

    query = db.query(AffiliateLink).order_by(AffiliateLink.created_at.desc())
    if q.strip():
        search = f"%{q.strip().lower()}%"
        query = query.filter(AffiliateLink.keyword.ilike(search))

    total = query.count()
    links = query.offset(offset).limit(limit).all()
    total_pages = max(1, (total + limit - 1) // limit)

    return templates.TemplateResponse("fragments/affiliates_table.html", {
        "request": request,
        "links": links,
        "total": total,
        "page": page,
        "total_pages": total_pages,
        "q": q,
    })

@router.post("/save")
def save_affiliate(
    request: Request,
    link_id: int = Form(0),
    keyword: str = Form(...),
    url: str = Form(...),
    comment_template: str = Form(...),
    db: Session = Depends(get_db)
):
    """Create or update an affiliate link."""
    keyword = keyword.strip()
    url = url.strip()
    comment_template = comment_template.strip()
    
    if not keyword or not url or not comment_template:
        return JSONResponse({"error": "Vui lòng nhập đầy đủ Keyword, URL và Câu bình luận."}, status_code=400)
        
    if link_id > 0:
        link = db.query(AffiliateLink).filter(AffiliateLink.id == link_id).first()
        if not link:
            return JSONResponse({"error": "Không tìm thấy Link."}, status_code=404)
            
        # Check keyword uniqueness
        existing = db.query(AffiliateLink).filter(AffiliateLink.keyword == keyword, AffiliateLink.id != link_id).first()
        if existing:
            return JSONResponse({"error": f"Từ khóa '{keyword}' đã tồn tại."}, status_code=400)
            
        link.keyword = keyword
        link.url = url
        link.comment_template = comment_template
        logger.info(f"Updated affiliate link {link_id}: {keyword}")
    else:
        existing = db.query(AffiliateLink).filter(AffiliateLink.keyword == keyword).first()
        if existing:
            return JSONResponse({"error": f"Từ khóa '{keyword}' đã tồn tại."}, status_code=400)
            
        link = AffiliateLink(
            keyword=keyword,
            url=url,
            comment_template=comment_template
        )
        db.add(link)
        logger.info(f"Created new affiliate link: {keyword}")
        
    db.commit()
    
    # Return HX-Trigger to reload the table
    response = HTMLResponse(content="")
    response.headers["HX-Trigger"] = "affiliatesChanged"
    return response

@router.delete("/{link_id}")
def delete_affiliate(link_id: int, db: Session = Depends(get_db)):
    """Delete an affiliate link."""
    link = db.query(AffiliateLink).filter(AffiliateLink.id == link_id).first()
    if not link:
        return JSONResponse({"error": "Không tìm thấy Link"}, status_code=404)
        
    db.delete(link)
    db.commit()
    
    response = HTMLResponse(content="")
    response.headers["HX-Trigger"] = "affiliatesChanged"
    return response

@router.post("/import-batch")
def import_batch(req: BatchImportRequest, db: Session = Depends(get_db)):
    """Batch import or update affiliate links from CSV."""
    success = 0
    skipped = 0
    errors = []
    rows_to_upsert = []
    
    for i, item in enumerate(req.items, 1):
        if not item.keyword or not item.affiliate_url:
            errors.append({"row": i, "reason": "Thiếu thông tin bắt buộc (Keyword & URL)"})
            skipped += 1
            continue
            
        ai_status = "PENDING" if not item.comment else "DONE"
            
        rows_to_upsert.append({
            'keyword': item.keyword,
            'url': item.affiliate_url,
            'comment_template': item.comment,
            'commission_rate': float(item.commission_rate) if item.commission_rate else None,
            'ai_status': ai_status,
            'created_at': int(time.time()),
            'updated_at': int(time.time()),
        })
        success += 1
            
    if rows_to_upsert:
        try:
            stmt = sqlite_insert(AffiliateLink).values(rows_to_upsert)
            stmt = stmt.on_conflict_do_update(
                index_elements=['keyword'],
                set_={
                    'url': stmt.excluded.url,
                    'comment_template': stmt.excluded.comment_template,
                    'commission_rate': stmt.excluded.commission_rate,
                    'ai_status': stmt.excluded.ai_status,
                    'updated_at': stmt.excluded.updated_at,
                }
            )
            db.execute(stmt)
            db.commit()
        except Exception as e:
            db.rollback()
            return {"success": 0, "skipped": len(req.items), "errors": [{"row": 0, "reason": str(e)}]}

    return {"success": success, "skipped": skipped, "errors": errors}

@router.post("/ai-generate")
def ai_generate(req: AIGenerateRequest):
    """Generate keywords and comment templates using Gemini AI."""
    prompt = (
        f"Hãy đóng vai chuyên gia Affiliate Marketing. Sản phẩm: {req.product_name}. "
        f"Danh mục: {req.category}. Giá: {req.price}đ. % Hoa hồng: {req.commission_rate}%. "
        "Tạo 3-5 keywords NGẮN GỌN để nhận diện khi tìm kiếm nội dung, và 3 mẫu bình luận (1 natural, 1 urgency, 1 review). "
        "Mỗi bình luận PHẢI có chứa chính xác chuỗi '[LINK]' để hệ thống thay bằng URL sau này. "
        "Trả kết quả về ĐÚNG json có định dạng sau, KHÔNG BỌC TRONG MARKDOWN, KHÔNG CÓ TEXT THỪA: "
        '{"keywords": ["kw1", "kw2"], "comments": [{"style": "natural", "text": "..."}, {"style": "urgency", "text": "..."}, {"style": "review", "text": "..."}]}'
    )

    raw_response = None
    source = "rpa"
    
    try:
        rpa = GeminiRPAService(max_retries=1)
        raw_response = rpa.ask(prompt)
    except Exception as e:
        logger.error(f"RPA Error in ai-generate: {e}")
        
    if not raw_response:
        source = "api"
        logger.info("[AI Generate] RPA failed or timed out, trying API fallback.")
        api = GeminiAPIService()
        raw_response = api.ask(prompt)
        
    if not raw_response:
        return JSONResponse({"error": "Cả hai engine AI đều thất bại (Quá tải hoặc lỗi). Vui lòng thử lại sau."}, status_code=503)
        
    try:
        match = re.search(r'\{.*\}', raw_response, re.DOTALL)
        if match:
            data = json.loads(match.group(0))
        else:
            data = json.loads(raw_response)
        
        data["source"] = source
        return {"data": data}
    except Exception as e:
        logger.error(f"Cannot parse AI json: {e}\nRaw response: {raw_response}")
        return JSONResponse({"error": "AI trả kết quả không đúng format hoặc không phải JSON."}, status_code=500)
