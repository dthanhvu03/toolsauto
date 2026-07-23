"""AI service domain.

Canonical entry for features: ``AIUseCases`` / ``AIPurpose`` (ADR-006).
Low-level transport remains ``AICaptionPipeline`` via ``runtime.pipeline``.
"""

from app.core.ai.use_cases import AIPurpose, AIUseCases

__all__ = ["AIPurpose", "AIUseCases"]
