from fastapi import APIRouter, Depends, Request, Form
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy.orm import Session
import logging

from app.database.core import get_db
from app.database.models import AffiliateLink
from app.main_templates import templates

router = APIRouter(prefix="/affiliates", tags=["affiliates"])
logger = logging.getLogger(__name__)

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
def get_affiliates_table(request: Request, q: str = "", db: Session = Depends(get_db)):
    """HTMX fragment for the table of affiliate links."""
    query = db.query(AffiliateLink).order_by(AffiliateLink.created_at.desc())
    if q.strip():
        search = f"%{q.strip().lower()}%"
        query = query.filter(AffiliateLink.keyword.ilike(search))
        
    links = query.all()
    
    return templates.TemplateResponse("fragments/affiliates_table.html", {
        "request": request,
        "links": links
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
