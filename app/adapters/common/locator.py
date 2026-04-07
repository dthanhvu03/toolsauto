"""
LocatorStrategy — Resilient multi-layer locator resolution.

Design (per user architectural review):
- Primary locator from DB (WorkflowRegistry)
- Secondary locator from DB (lower priority)
- Heuristic fallback hardcoded in adapter code
- CSS selector is last resort only
- All resolution steps are logged for traceability
- Validates selectors are actionable before returning
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional, Callable

from playwright.sync_api import Page, Locator

logger = logging.getLogger(__name__)


@dataclass
class LocatorCandidate:
    """A single locator attempt with metadata."""
    strategy: str        # "db_primary", "db_secondary", "heuristic", "css_fallback"
    locator_type: str    # "role", "label", "text", "placeholder", "css", "test_id"
    value: str           # The actual selector or locator descriptor
    source: str          # "database", "static", "heuristic"


@dataclass
class LocatorResult:
    """Result of locator resolution."""
    found: bool
    locator: Optional[Locator] = None
    strategy_used: str = ""
    attempts: int = 0
    total_candidates: int = 0
    log_entries: list[str] = field(default_factory=list)


class LocatorStrategy:
    """
    Multi-layer locator resolution engine.
    
    Priority order:
    1. accessibility label (aria-label, role)
    2. placeholder / visible text
    3. input type / accept attributes
    4. stable attributes (data-testid)
    5. CSS selector (last resort)
    
    Each action in the adapter should define multiple strategies.
    """

    def __init__(self, page: Page, platform: str):
        self.page = page
        self.platform = platform
        self._resolution_log: list[dict] = []

    def resolve(
        self,
        action_name: str,
        candidates: list[LocatorCandidate],
        *,
        timeout_ms: int = 3000,
        must_be_visible: bool = True,
        must_be_enabled: bool = False,
    ) -> LocatorResult:
        """
        Try each candidate in order. Return the first one that:
        1. Exists in DOM
        2. Is visible (if must_be_visible)
        3. Is enabled (if must_be_enabled)
        
        Logs every attempt for full traceability.
        """
        result = LocatorResult(
            found=False,
            total_candidates=len(candidates),
        )
        prefix = f"[{self.platform}:{action_name}]"

        for i, candidate in enumerate(candidates):
            result.attempts = i + 1
            log_line = (
                f"{prefix} Try #{i+1}/{len(candidates)} "
                f"[{candidate.strategy}:{candidate.locator_type}] "
                f"src={candidate.source} val={candidate.value!r}"
            )

            try:
                loc = self._build_locator(candidate)
                if loc is None:
                    log_line += " → SKIP (unsupported type)"
                    logger.debug(log_line)
                    result.log_entries.append(log_line)
                    continue

                # Check existence
                count = loc.count()
                if count == 0:
                    log_line += " → NOT_FOUND"
                    logger.debug(log_line)
                    result.log_entries.append(log_line)
                    continue

                target = loc.first

                # Visibility check
                if must_be_visible:
                    try:
                        is_vis = target.is_visible(timeout=timeout_ms)
                    except Exception:
                        is_vis = False
                    if not is_vis:
                        log_line += f" → FOUND({count}) but NOT_VISIBLE"
                        logger.debug(log_line)
                        result.log_entries.append(log_line)
                        continue

                # Enabled check
                if must_be_enabled:
                    try:
                        is_en = target.is_enabled(timeout=timeout_ms)
                    except Exception:
                        is_en = False
                    if not is_en:
                        log_line += f" → FOUND({count}) VISIBLE but DISABLED"
                        logger.debug(log_line)
                        result.log_entries.append(log_line)
                        continue

                # Success
                log_line += f" → ✓ MATCHED (count={count})"
                logger.info(log_line)
                result.log_entries.append(log_line)
                result.found = True
                result.locator = target
                result.strategy_used = candidate.strategy

                # Record for diagnostics
                self._resolution_log.append({
                    "action": action_name,
                    "strategy": candidate.strategy,
                    "locator_type": candidate.locator_type,
                    "value": candidate.value,
                    "source": candidate.source,
                    "attempt": i + 1,
                    "total": len(candidates),
                    "matched": True,
                })
                return result

            except Exception as e:
                log_line += f" → ERROR: {e}"
                logger.warning(log_line)
                result.log_entries.append(log_line)
                continue

        # All candidates exhausted
        logger.warning(
            "%s All %d candidates exhausted — NO MATCH",
            prefix, len(candidates),
        )
        self._resolution_log.append({
            "action": action_name,
            "matched": False,
            "total_tried": len(candidates),
        })
        return result

    def _build_locator(self, candidate: LocatorCandidate) -> Optional[Locator]:
        """
        Convert a LocatorCandidate into a Playwright Locator.
        Supports: role, label, text, placeholder, test_id, css.
        """
        lt = candidate.locator_type
        val = candidate.value

        if lt == "role":
            # Format: "button" or "button:Post" (role:name)
            parts = val.split(":", 1)
            role = parts[0].strip()
            name = parts[1].strip() if len(parts) > 1 else None
            if name:
                return self.page.get_by_role(role, name=name)
            return self.page.get_by_role(role)

        elif lt == "label":
            return self.page.get_by_label(val)

        elif lt == "text":
            return self.page.get_by_text(val)

        elif lt == "placeholder":
            return self.page.get_by_placeholder(val)

        elif lt == "test_id":
            return self.page.get_by_test_id(val)

        elif lt == "css":
            return self.page.locator(val)

        elif lt == "xpath":
            return self.page.locator(f"xpath={val}")

        else:
            logger.warning(
                "LocatorStrategy: Unknown locator_type '%s' for %s",
                lt, candidate.value,
            )
            return None

    def get_resolution_log(self) -> list[dict]:
        """Return full resolution audit trail."""
        return list(self._resolution_log)

    def build_candidates_from_db(
        self,
        category: str,
        selector_key: str,
        heuristic_fallbacks: list[LocatorCandidate] | None = None,
    ) -> list[LocatorCandidate]:
        """
        Build a prioritized candidate list:
        1. DB selectors (primary by highest priority)
        2. DB selectors (secondary by lower priority)
        3. Heuristic fallbacks from adapter code
        
        This replaces the old _get_dynamic_selectors + _wait_and_locate_array pattern.
        """
        from app.services.workflow_registry import WorkflowRegistry

        candidates: list[LocatorCandidate] = []

        try:
            items = WorkflowRegistry.get_selectors(
                self.platform, f"{category}:{selector_key}"
            )
            for i, item in enumerate(items):
                candidates.append(LocatorCandidate(
                    strategy="db_primary" if i == 0 else "db_secondary",
                    locator_type=item.selector_type or "css",
                    value=item.selector_value,
                    source="database",
                ))
        except Exception as e:
            logger.warning(
                "LocatorStrategy: DB selector fetch failed for %s:%s — %s",
                category, selector_key, e,
            )

        # Append heuristic fallbacks
        if heuristic_fallbacks:
            candidates.extend(heuristic_fallbacks)

        return candidates
