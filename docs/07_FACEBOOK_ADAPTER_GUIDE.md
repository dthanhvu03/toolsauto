# Facebook adapter (FB-first) — Guide for implementation

## Goal
Implement adapter for Facebook posting workflow using Playwright with persistent profile.

## Critical constraints
- Do not rely on random class names or deep DOM selectors.
- Prefer Playwright "role/text/label" based locators.
- Use scoped locators (dialog/composer scope) to increase speed & accuracy.
- Avoid hard sleeps. Use wait_for_selector, locator.wait_for, networkidle where appropriate.
- Capture screenshot + page HTML dump on error.

## Session strategy
Preferred: launch_persistent_context(user_data_dir=profiles/<account>)
- First-time login is manual (init script)
- Subsequent runs reuse profile

## FB flow (high-level only)
1) Navigate to Facebook home (or Page composer depending on target)
2) Open composer ("Create post")
3) Upload media (input[type=file])
4) Focus caption textbox (contenteditable/role=textbox)
5) Type caption with human-like key delay (small)
6) Click Post/Publish
7) Wait for confirmation signal (UI toast, button disabled, or post dialog closes)

## Selector acquisition process (MANDATORY)
- Use "playwright codegen" to generate initial locators for your environment.
- Replace fragile selectors with robust ones:
  - get_by_role("button", name=...)
  - get_by_label(...)
  - get_by_text(...)
  - locator('[role="textbox"]') within composer scope

## Robustness patterns
- Implement fallback selector list per action:
  - open composer
  - find textbox
  - find post button
- Each fallback has short timeout (2–3s), proceed to next.

## Failure artifacts
- screenshot: logs/fb/job_<id>_error.png
- html: logs/fb/job_<id>_error.html
- optional: trace.zip (Playwright tracing)

## Acceptance criteria
- Adapter can publish a job in stable environment with persistent profile
- On failure, artifacts are produced and error is actionable