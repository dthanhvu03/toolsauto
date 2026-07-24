from __future__ import annotations

from playwright.sync_api import Locator, Page


class FindButtonsMixin:
    def find_next_button(self, surface: Page | Locator) -> Locator | None:
        candidates = [
            surface.locator('div[aria-label="Tiếp"], div[aria-label="Next"]').first,
            surface.get_by_role("button", name="Tiếp", exact=True).first,
            surface.get_by_role("button", name="Next", exact=True).first,
            surface.get_by_role("button", name="Next", exact=False).first,
            surface.locator('button:has-text("Tiếp")').first,
            surface.locator('button:has-text("Next")').first,
            surface.locator(
                'div[role="button"][aria-label="Tiếp"], div[role="button"][aria-label="Next"]'
            ).first,
            surface.locator(
                'span[role="button"][aria-label="Tiếp"], span[role="button"][aria-label="Next"]'
            ).first,
            surface.get_by_text("Tiếp", exact=True).first,
            surface.get_by_text("Next", exact=True).first,
        ]
        result = self._find_first_visible(candidates)
        if result:
            return result
        # Fallback: try aria-label match even if _is_visible fails (may be overlapped by dialog)
        for label in self.NEXT_BUTTON_LABELS:
            try:
                loc = surface.locator(f'div[role="button"][aria-label="{label}"]')
                if loc.count() > 0:
                    self.logger.info("FacebookAdapter: Next button '%s' found via aria-label fallback (may be overlapped)", label)
                    return loc.first
            except Exception:
                pass
        return None

    # Schedule-related aria-labels that definitively identify schedule buttons
    SCHEDULE_ARIA_LABELS = ("Schedule", "Lên lịch", "Lịch đăng", "Schedule post")

    def is_schedule_button(self, locator: Locator) -> bool:
        try:
            btn_text = (locator.inner_text() or "").strip().lower()
            aria = (locator.get_attribute("aria-label") or "").strip()

            # Short button text that matches a known post label is NEVER a schedule button
            if btn_text in ("đăng", "post", "publish", "chia sẻ", "share", "đăng bài", "đăng thước phim"):
                return False

            # Also check aria-label: if aria matches a post label, not schedule
            aria_lower = aria.lower()
            if aria_lower in ("đăng", "post", "publish", "chia sẻ", "share", "đăng bài", "đăng thước phim"):
                return False

            # Check aria-label for definitive schedule indicators
            if any(s.lower() in aria_lower for s in self.SCHEDULE_ARIA_LABELS):
                self.logger.debug("is_schedule_button=True (aria match): aria='%s', text='%s'", aria, btn_text[:40])
                return True

            # Check text content for schedule poison words
            is_poison = any(word in btn_text for word in self.SCHEDULE_POISON_WORDS)
            if is_poison:
                self.logger.debug("is_schedule_button=True (poison): text='%s', aria='%s'", btn_text[:60], aria)
            return is_poison
        except Exception:
            return False

    def _post_button_exact(self, surface: Page | Locator) -> Locator | None:
        for label in self.POST_BUTTON_LABELS:
            exact_candidates = [
                surface.locator(f'div[aria-label="{label}"]').first,
                surface.get_by_role("button", name=label, exact=True).first,
                surface.locator(f'div[role="button"][aria-label="{label}"]').first,
                surface.locator(f'button[aria-label="{label}"]').first,
            ]
            for candidate in exact_candidates:
                if self._is_visible(candidate) and not self.is_schedule_button(candidate):
                    self.logger.debug("FacebookAdapter: Post button matched via exact label '%s'", label)
                    return candidate

    def _post_button_fuzzy(self, surface: Page | Locator) -> Locator | None:
        fuzzy_candidates: list[Locator] = []
        for label in self.POST_BUTTON_LABELS:
            fuzzy_candidates.append(surface.get_by_role("button", name=label, exact=False).first)
        fuzzy_candidates.extend(
            [
                surface.locator('div[role="button"]:has-text("Đăng")').first,
                surface.locator('div[role="button"]:has-text("Post")').first,
                surface.locator('span[role="button"]:has-text("Đăng")').first,
                surface.locator('span[role="button"]:has-text("Post")').first,
                surface.locator('button:has-text("Đăng")').first,
                surface.locator('button:has-text("Post")').first,
            ]
        )
        for candidate in fuzzy_candidates:
            if self._is_visible(candidate) and not self.is_schedule_button(candidate):
                self.logger.debug("FacebookAdapter: Post button matched via fuzzy search")
                return candidate

    def _post_button_aria_fallback(self, surface: Page | Locator) -> Locator | None:
        for label in self.POST_BUTTON_LABELS:
            try:
                loc = surface.locator(f'div[role="button"][aria-label="{label}"]')
                if loc.count() > 0 and not self.is_schedule_button(loc.first):
                    self.logger.debug("FacebookAdapter: Post button '%s' found via aria-label fallback", label)
                    return loc.first
            except Exception:
                pass

    def _debug_post_label_parts(self, surface: Page | Locator) -> list[str]:
        parts: list[str] = []
        for label in self.POST_BUTTON_LABELS:
            try:
                for b in surface.get_by_role("button", name=label, exact=False).all()[:3]:
                    vis = self._is_visible(b)
                    sched = self.is_schedule_button(b) if vis else False
                    txt = (b.inner_text() or "")[:50].replace("\n", " ") if vis else "?"
                    aria_l = (b.get_attribute("aria-label") or "")[:30] if vis else "?"
                    parts.append(f"{label}→vis={vis},sched={sched},txt='{txt}',aria='{aria_l}'")
            except Exception:
                pass
        return parts

    def _log_visible_surface_buttons(self, surface: Page | Locator) -> None:
        try:
            vis_btns: list[str] = []
            for ab in surface.locator('div[role="button"], button, span[role="button"]').all()[:20]:
                try:
                    if not ab.is_visible():
                        continue
                    t = (ab.inner_text() or "").strip()[:40].replace("\n", " ")
                    a = (ab.get_attribute("aria-label") or "")[:30]
                    if t or a:
                        vis_btns.append(f"'{t}'(aria='{a}')")
                except Exception:
                    pass
            self.logger.warning(
                "FacebookAdapter: NO post-label candidates found. Visible buttons on surface: %s",
                ", ".join(vis_btns[:10]) if vis_btns else "(none)",
            )
        except Exception as exc:
            self.logger.warning(
                "FacebookAdapter: NO post-label candidates + surface scan failed: %s", exc
            )

    def _log_post_button_miss(self, surface: Page | Locator) -> None:
        debug_parts = self._debug_post_label_parts(surface)
        if debug_parts:
            self.logger.warning(
                "FacebookAdapter: Post button candidates: %s", " | ".join(debug_parts[:5])
            )
        else:
            self._log_visible_surface_buttons(surface)
        self.logger.warning(
            "FacebookAdapter: No post button found (all candidates were schedule buttons or invisible)"
        )

    def find_post_button(self, surface: Page | Locator) -> Locator | None:
        for finder in (self._post_button_exact, self._post_button_fuzzy, self._post_button_aria_fallback):
            button = finder(surface)
            if button:
                return button
        self._log_post_button_miss(surface)
        return None
