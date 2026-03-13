# Selector Strategy: "Smart & Accurate" (Playwright)

## Priority order (most robust -> least)
1) get_by_role(role, name=...)  (ARIA-based)
2) get_by_label(label)
3) get_by_text(text)
4) locator(css) with stable attributes (aria-label, role)
5) XPath / nth-child (last resort)

## Smart scanning principles
- Always narrow scope:
  - Find composer/dialog container first
  - Then locate button/textbox inside container
- Avoid querying whole DOM repeatedly.

## Waiting principles (no hard sleep)
- Prefer:
  - locator.wait_for(state="visible")
  - page.wait_for_selector(...)
  - page.wait_for_load_state("networkidle") when needed
- Use small timeout per step, not huge default.

## Fallback system (required)
- Provide list of candidate locators per action
- Try sequentially with short timeouts
- Fail with clear error explaining which step fails

## Debug workflow
- page.pause() in dev mode to inspect
- Always screenshot on error
- Optional: Playwright trace for hard bugs

## Acceptance criteria
- Selector changes only affect one small mapping area (selectors.py)
- Failures pinpoint the step accurately