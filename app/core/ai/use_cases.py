"""
AI use-case facade — single entry for feature code (ADR-006).

Features gọi đây thay vì `app.core.ai.runtime.pipeline` trực tiếp.
Transport: AICaptionPipeline (9Router → Gemini native fallback).
`purpose` gắn vào meta để quan sát; domain methods giữ prompt nghiệp vụ ở một chỗ.
"""
from __future__ import annotations

from typing import Any, Optional, Sequence, Tuple

from app.core.ai.pipeline import CaptionPayload
from app.core.ai.runtime import pipeline


class AIPurpose:
    """Stable purpose tags for meta['purpose']."""

    CAPTION = "caption"
    CAPTION_SIMPLE = "caption_simple"
    AFFILIATE_COMMENT = "affiliate_comment"
    AFFILIATE_GENERATE = "affiliate_generate"
    COMPLIANCE_REWRITE = "compliance_rewrite"
    COMPLIANCE_SUGGEST = "compliance_suggest"
    THREADS_NEWS = "threads_news"
    THREADS_REPLY = "threads_reply"
    INSIGHTS_COMMENTARY = "insights_commentary"
    INSIGHTS_ROADMAP = "insights_roadmap"
    STRATEGIC_ADVICE = "strategic_advice"
    INCIDENT_REPORT = "incident_report"
    STUDIO_TEST = "studio_test"
    GENERIC = "generic"


def _stamp(meta: dict | None, purpose: str) -> dict:
    out = dict(meta or {})
    out.setdefault("purpose", purpose)
    return out


def _violation_lines(violations: Sequence[Any]) -> str:
    lines: list[str] = []
    for v in violations:
        if isinstance(v, dict):
            cat = v.get("category", "")
            ev = v.get("evidence", "")
            sug = v.get("suggestion", "")
        else:
            cat = getattr(v, "category", "")
            ev = getattr(v, "evidence", "")
            sug = getattr(v, "suggestion", "")
        lines.append(f"- [{cat}] {ev}: {sug}")
    return "\n".join(lines)


def _incident_rows_for_prompt(groups: Sequence[Any]) -> str:
    lines = []
    for idx, group in enumerate(groups, 1):
        lines.append(
            "\n".join(
                [
                    f"{idx}. signature={getattr(group, 'error_signature', '-')}",
                    f"   platform={getattr(group, 'last_platform', None) or '-'} "
                    f"worker={getattr(group, 'last_worker_name', None) or '-'}",
                    f"   severity={getattr(group, 'severity_max', '-')} "
                    f"count={getattr(group, 'occurrence_count', 0)}",
                    f"   last_seen={getattr(group, 'last_seen_at', '-')}",
                    f"   sample={getattr(group, 'last_sample_message', None) or '-'}",
                    f"   job_id={getattr(group, 'last_job_id', None) or '-'} "
                    f"account_id={getattr(group, 'last_account_id', None) or '-'}",
                ]
            )
        )
    return "\n\n".join(lines)


class AIUseCases:
    """Nghiệp vụ AI — text / caption / domain helpers."""

    @staticmethod
    def is_enabled() -> bool:
        """9Router gateway flag (shared singleton)."""
        return bool(getattr(pipeline, "enabled", True))

    # ── Primitive (prompt đã dựng sẵn) ────────────────────────────────────

    @staticmethod
    def generate_text(
        prompt: str,
        *,
        purpose: str = AIPurpose.GENERIC,
    ) -> Tuple[Optional[str], dict]:
        text, meta = pipeline.generate_text(prompt)
        return text, _stamp(meta, purpose)

    @staticmethod
    async def generate_text_async(
        prompt: str,
        *,
        purpose: str = AIPurpose.GENERIC,
    ) -> Tuple[Optional[str], dict]:
        text, meta = await pipeline.generate_text_async(prompt)
        return text, _stamp(meta, purpose)

    @staticmethod
    def generate_caption(
        prompt: str,
        image_path: Optional[str] = None,
        *,
        purpose: str = AIPurpose.CAPTION,
    ) -> Tuple[Optional[CaptionPayload], dict]:
        payload, meta = pipeline.generate_caption(prompt, image_path)
        return payload, _stamp(meta, purpose)

    # ── Domain: Affiliate ─────────────────────────────────────────────────

    @staticmethod
    def generate_affiliate_comment(
        keyword: str,
        url: str,
    ) -> Tuple[Optional[str], dict]:
        prompt = (
            f"Hãy đóng vai chuyên gia Affiliate Marketing. Sản phẩm có từ khóa nhận diện là: '{keyword}'. "
            f"URL sản phẩm: {url}. "
            "Hãy tạo 1 mẫu bình luận cực kỳ hấp dẫn, tự nhiên để chèn vào bài viết. "
            "Bình luận PHẢI có chứa chính xác chuỗi '[LINK]' để hệ thống thay bằng URL sau này. "
            "Trả về kết quả dưới dạng JSON (không markdown): "
            '{"comment": "Nội dung bình luận ở đây [LINK]"}'
        )
        return AIUseCases.generate_text(prompt, purpose=AIPurpose.AFFILIATE_COMMENT)

    @staticmethod
    def generate_affiliate_bundle(
        product_name: str,
        category: str,
        price: str,
        commission_rate: str,
    ) -> Tuple[Optional[str], dict]:
        prompt = (
            f"Hãy đóng vai chuyên gia Affiliate Marketing. Sản phẩm: {product_name}. "
            f"Danh mục: {category}. Giá: {price}đ. % Hoa hồng: {commission_rate}%. "
            "Tạo 3-5 keywords NGẮN GỌN để nhận diện khi tìm kiếm nội dung, và 3 mẫu bình luận (1 natural, 1 urgency, 1 review). "
            "Mỗi bình luận PHẢI có chứa chính xác chuỗi '[LINK]' để hệ thống thay bằng URL sau này. "
            "Trả kết quả về ĐÚNG json có định dạng sau, KHÔNG BỌC TRONG MARKDOWN, KHÔNG CÓ TEXT THỪA: "
            '{"keywords": ["kw1", "kw2"], "comments": [{"style": "natural", "text": "..."}, '
            '{"style": "urgency", "text": "..."}, {"style": "review", "text": "..."}]}'
        )
        return AIUseCases.generate_text(prompt, purpose=AIPurpose.AFFILIATE_GENERATE)

    # ── Domain: Compliance ────────────────────────────────────────────────

    @staticmethod
    def rewrite_for_facebook_compliance(
        content: str,
        violations: Sequence[Any],
        product_category: str = "general",
    ) -> Tuple[Optional[str], dict]:
        violation_list = _violation_lines(violations)
        prompt = (
            f"Bạn là chuyên gia nội dung Facebook tuân thủ chính sách "
            f"cho thị trường Việt Nam.\n\n"
            f"Viết lại comment/caption sau để tuân thủ chính sách "
            f"Facebook, đồng thời giữ nguyên ý nghĩa marketing:\n\n"
            f"Nội dung gốc:\n{content}\n\n"
            f"Vi phạm cần sửa:\n{violation_list}\n\n"
            f"Danh mục sản phẩm: {product_category}\n\n"
            f"Yêu cầu:\n"
            f"- Xóa/thay thế các từ vi phạm\n"
            f"- Giữ nguyên [LINK] nếu có\n"
            f"- Dùng tiếng Việt tự nhiên\n"
            f"- Tối đa 3 emoji\n"
            f"- Dưới 300 ký tự nếu là comment\n"
            f"- Nếu không thể sửa an toàn, trả về: [REJECT]\n\n"
            f"Chỉ trả về nội dung đã viết lại, không giải thích."
        )
        return AIUseCases.generate_text(prompt, purpose=AIPurpose.COMPLIANCE_REWRITE)

    # ── Domain: Threads ───────────────────────────────────────────────────

    @staticmethod
    async def generate_threads_reply(
        content_snippet: str,
    ) -> Tuple[Optional[str], dict]:
        prompt = (
            "Bạn là một người dùng Threads thân thiện, hài hước và tinh tế. "
            f"Hãy viết một câu trả lời ngắn gọn (dưới 20 từ) cho bình luận sau: '{content_snippet}'. "
            "Hãy dùng ngôn ngữ tự nhiên, trẻ trung."
        )
        return await AIUseCases.generate_text_async(
            prompt, purpose=AIPurpose.THREADS_REPLY
        )

    # ── Domain: Incident report ───────────────────────────────────────────

    @staticmethod
    def generate_incident_report(
        groups: Sequence[Any],
    ) -> Tuple[Optional[str], dict]:
        prompt = f"""
Bạn là AI vận hành hệ thống ToolsAuto. Hãy viết Daily Health Report bằng tiếng Việt, ngắn gọn, có Markdown.

Yêu cầu:
- Không bịa nguyên nhân nếu evidence chưa đủ.
- Mỗi nhận định root cause phải gắn với signature/job/platform/count.
- Chỉ đề xuất hành động vận hành an toàn; không đề xuất tự sửa code, không auto-healing.
- Format gồm: Tóm tắt, Top lỗi, Khả năng nguyên nhân, Hành động đề xuất, Cần người kiểm tra.

Dữ liệu top incident groups trong 24h:

{_incident_rows_for_prompt(groups)}
""".strip()
        return AIUseCases.generate_text(prompt, purpose=AIPurpose.INCIDENT_REPORT)
