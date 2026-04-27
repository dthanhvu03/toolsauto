import logging
import time
import json
import re
from typing import Dict, List, Tuple, Any
from sqlalchemy.orm import Session
from sqlalchemy.dialects.postgresql import insert as pg_insert
from app.database.models import AffiliateLink
from app.services.fb_compliance import compliance_checker, Severity, log_violation
from app.services.affiliate_ai import AffiliateAIService
from app.services.gemini_rpa import GeminiRPAService
from app.services.gemini_api import GeminiAPIService
from app.constants import JobStatus

logger = logging.getLogger(__name__)

class AffiliateService:

    @staticmethod
    def get_links_paged(db: Session, q: str = "", page: int = 1, limit: int = 25) -> Dict[str, Any]:
        offset = (page - 1) * limit
        query = db.query(AffiliateLink).order_by(AffiliateLink.created_at.desc())
        if q.strip():
            search = f"%{q.strip().lower()}%"
            query = query.filter(AffiliateLink.keyword.ilike(search))

        total = query.count()
        links = query.offset(offset).limit(limit).all()
        total_pages = max(1, (total + limit - 1) // limit)
        
        return {
            "links": links,
            "total": total,
            "page": page,
            "total_pages": total_pages,
        }

    @staticmethod
    def save_link(db: Session, link_id: int, keyword: str, url: str, comment_template: str) -> Tuple[bool, Dict[str, Any]]:
        keyword = keyword.strip()
        url = url.strip()
        comment_template = comment_template.strip()
        
        if not keyword or not url or not comment_template:
            return False, {"error": "Vui lòng nhập đầy đủ Keyword, URL và Câu bình luận."}

        save_check = compliance_checker.check(comment_template)
        if save_check.status == Severity.VIOLATION:
            log_violation(
                content=comment_template,
                violations=save_check.violations,
                action=Severity.VIOLATION.value,
                affiliate_id=link_id if link_id > 0 else None,
                content_type="manual_save",
            )
            return False, {
                "error": "Nội dung vi phạm chính sách Facebook, không thể lưu.",
                "violations": [v.evidence for v in save_check.violations],
                "status": "VIOLATION",
            }

        if link_id > 0:
            link = db.query(AffiliateLink).filter(AffiliateLink.id == link_id).first()
            if not link:
                return False, {"error": "Không tìm thấy Link."}
                
            existing = db.query(AffiliateLink).filter(AffiliateLink.keyword == keyword, AffiliateLink.id != link_id).first()
            if existing:
                return False, {"error": f"Từ khóa '{keyword}' đã tồn tại."}
                
            link.keyword = keyword
            link.url = url
            link.comment_template = comment_template
        else:
            existing = db.query(AffiliateLink).filter(AffiliateLink.keyword == keyword).first()
            if existing:
                return False, {"error": f"Từ khóa '{keyword}' đã tồn tại."}
                
            link = AffiliateLink(
                keyword=keyword,
                url=url,
                comment_template=comment_template
            )
            db.add(link)
            
        db.commit()
        return True, {}

    @staticmethod
    def delete_link(db: Session, link_id: int) -> bool:
        link = db.query(AffiliateLink).filter(AffiliateLink.id == link_id).first()
        if not link:
            return False
        db.delete(link)
        db.commit()
        return True

    @staticmethod
    def import_batch(db: Session, items: List[Any]) -> Dict[str, Any]:
        success = 0
        skipped = 0
        errors = []
        rows_to_upsert = []

        for i, item in enumerate(items, 1):
            if not item.keyword or not item.affiliate_url:
                errors.append({"row": i, "reason": "Thiếu thông tin bắt buộc (Keyword & URL)"})
                skipped += 1
                continue

            comment = (item.comment or "").strip()
            if not comment:
                try:
                    generated = AffiliateAIService.generate_comment(keyword=item.keyword, url=item.affiliate_url)
                    if generated:
                        comp = compliance_checker.check_and_rewrite(generated, product_category="general")
                        if comp.status == Severity.VIOLATION:
                            comment = ""
                            ai_status = JobStatus.PENDING
                        else:
                            comment = comp.rewritten if comp.rewritten else generated
                            ai_status = JobStatus.DONE
                    else:
                        ai_status = JobStatus.PENDING
                except Exception:
                    ai_status = JobStatus.PENDING
            else:
                ai_status = JobStatus.DONE

            if comment:
                comp = compliance_checker.check_and_rewrite(comment, product_category="general")
                if comp.status == Severity.VIOLATION:
                    errors.append({"row": i, "keyword": item.keyword, "reason": f"Vi phạm chính sách FB: {[v.evidence for v in comp.violations]}"})
                    skipped += 1
                    continue
                if comp.status == Severity.WARNING and comp.rewritten:
                    comment = comp.rewritten

            rows_to_upsert.append({
                "keyword": item.keyword,
                "url": item.affiliate_url,
                "comment_template": comment or None,
                "commission_rate": float(item.commission_rate) if item.commission_rate else None,
                "ai_status": ai_status,
                "created_at": int(time.time()),
                "updated_at": int(time.time()),
            })
            success += 1

        if rows_to_upsert:
            try:
                stmt = pg_insert(AffiliateLink).values(rows_to_upsert)
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
                return {"success": 0, "skipped": len(items), "errors": [{"row": 0, "reason": str(e)}]}

        return {"success": success, "skipped": skipped, "errors": errors}

    @staticmethod
    def ai_generate(product_name: str, category: str, price: str, commission_rate: str) -> Dict[str, Any]:
        prompt = (
            f"Hãy đóng vai chuyên gia Affiliate Marketing. Sản phẩm: {product_name}. "
            f"Danh mục: {category}. Giá: {price}đ. % Hoa hồng: {commission_rate}%. "
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
        except Exception:
            pass
            
        if not raw_response:
            source = "api"
            api = GeminiAPIService()
            raw_response = api.ask(prompt)
            
        if not raw_response:
            return {"error": "Cả hai engine AI đều thất bại.", "status_code": 503}
            
        try:
            match = re.search(r'\{.*\}', raw_response, re.DOTALL)
            data = json.loads(match.group(0)) if match else json.loads(raw_response)
            data["source"] = source

            comments = data.get("comments") or []
            product_category = category or "general"
            violation_items: list = []
            audit_snippets: list[str] = []
            enriched_comments: list[dict] = []

            for c in comments:
                if not isinstance(c, dict): continue
                text = (c.get("text") or "").strip()
                if not text:
                    enriched_comments.append(c)
                    continue
                comp = compliance_checker.check_and_rewrite(text, product_category=product_category)
                if comp.status == Severity.VIOLATION:
                    violation_items.extend(comp.violations)
                    audit_snippets.append(text)
                row = {**c, "compliance_status": comp.status.value}
                if comp.rewritten:
                    row["rewritten_text"] = comp.rewritten
                enriched_comments.append(row)

            data["comments"] = enriched_comments

            if violation_items:
                log_violation(content="\n---\n".join(audit_snippets)[:12000], violations=violation_items, action=Severity.VIOLATION.value, content_type="ai_generate")
                return {
                    "error": "Nội dung AI tạo ra vi phạm chính sách Facebook.",
                    "violations": [v.evidence for v in violation_items],
                    "status": "VIOLATION",
                    "status_code": 422
                }

            payload: dict = {"data": data}
            if any(c.get("rewritten_text") for c in enriched_comments):
                payload["needs_review"] = True
            return payload
        except Exception as e:
            return {"error": f"AI response parse error: {e}", "status_code": 500}
    @staticmethod
    def compliance_check(text: str) -> Dict[str, Any]:
        text = (text or "").strip()
        result = compliance_checker.check(text)
        return {
            "status": result.status.value,
            "violations": [
                {
                    "evidence": v.evidence,
                    "category": v.category,
                    "severity": v.severity.value,
                }
                for v in result.violations
            ],
        }
