"""
MCP Server — n8n-lite workflow debug tools.

Thin wrapper exposing WorkflowRegistry and Dispatcher helpers
via Model Context Protocol (stdio transport) for MCP Inspector testing.

Usage:
    venv/bin/python mcp_server.py          # start server (stdio)
    npx @modelcontextprotocol/inspector venv/bin/python mcp_server.py  # Inspector
"""

import sys
import os

# Ensure repo root is on PYTHONPATH so app.* imports work
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("n8n-lite-debug")


# ═══════════════════════════════════════════════════════════════
#  Tool 1 — get_workflow_steps
# ═══════════════════════════════════════════════════════════════

@mcp.tool()
def get_workflow_steps(platform: str, job_type: str = "POST") -> str:
    """Get the active workflow steps list from WorkflowRegistry.

    Returns the steps array configured in workflow_definitions for the
    given platform and job_type.  When steps is empty or the workflow
    row is missing the runtime keeps all blocks enabled (default).

    Args:
        platform: Platform name, e.g. "facebook"
        job_type: Job type, e.g. "POST" or "COMMENT"
    """
    from app.services.workflow_registry import WorkflowRegistry

    wf = WorkflowRegistry.get_workflow(platform, job_type)
    if not wf:
        return f"No workflow config found for {platform}:{job_type}"

    steps = wf.steps
    if not steps:
        return (
            f"Workflow '{wf.name}' found for {platform}:{job_type}, "
            "steps=[] — all runtime blocks run with defaults (nothing skipped)."
        )
    return f"Active steps for {platform}:{job_type}: {steps}"


# ═══════════════════════════════════════════════════════════════
#  Tool 2 — get_cta_templates
# ═══════════════════════════════════════════════════════════════

@mcp.tool()
def get_cta_templates(platform: str, locale: str = "vi") -> str:
    """Get CTA templates from the registry for the given platform/locale.

    Returns the list of CTA template strings currently active in the
    database.  If no templates are found the registry returns ["{link}"]
    as the default fallback.

    Args:
        platform: Platform name, e.g. "facebook"
        locale: Locale filter, e.g. "vi" or "*"
    """
    from app.services.workflow_registry import WorkflowRegistry

    templates = WorkflowRegistry.get_cta_templates(platform, locale=locale)
    if templates == ["{link}"]:
        return (
            f"No usable CTA templates for {platform}/{locale}. "
            "Fallback: [\"{{link}}\"]"
        )
    lines = [f"  {i+1}. {t}" for i, t in enumerate(templates)]
    return (
        f"CTA templates for {platform}/{locale} ({len(templates)} total):\n"
        + "\n".join(lines)
    )


# ═══════════════════════════════════════════════════════════════
#  Tool 3 — inject_cta
# ═══════════════════════════════════════════════════════════════

@mcp.tool()
def inject_cta(platform: str, text: str, locale: str = "vi") -> str:
    """Preview CTA injection on arbitrary text using the Phase 2 logic.

    Uses the real Dispatcher._inject_cta() method.  Only raw-link-only
    text gets wrapped — normal sentences are returned unchanged.
    This is a read-only preview; it does NOT modify any database state.

    Args:
        platform: Platform name, e.g. "facebook"
        text: The text to inject CTA into (e.g. a URL or caption)
        locale: Locale for CTA template selection
    """
    from app.adapters.dispatcher import Dispatcher

    result = Dispatcher._inject_cta(platform, text, locale=locale)
    if result == text:
        return f"No injection (text is not raw-link-only).\nOriginal: {text}"
    return f"CTA injected ✓\nBefore: {text}\nAfter:  {result}"


# ═══════════════════════════════════════════════════════════════
#  Tool 4 — preview_step_toggles
# ═══════════════════════════════════════════════════════════════

from app.services.workflow_registry import KNOWN_TOGGLEABLE_STEPS


@mcp.tool()
def preview_step_toggles(platform: str, job_type: str = "POST") -> str:
    """Preview which runtime steps would be active vs skipped.

    Reads the workflow_definitions.steps list and compares it against
    the known toggleable steps in the adapter: feed_browse, pre_scan,
    type_comment.

    Args:
        platform: Platform name, e.g. "facebook"
        job_type: Job type, e.g. "POST" or "COMMENT"
    """
    from app.services.workflow_registry import WorkflowRegistry

    wf = WorkflowRegistry.get_workflow(platform, job_type)
    if not wf or not wf.steps:
        wf_name = wf.name if wf else "N/A"
        return (
            f"Workflow '{wf_name}' found for {platform}:{job_type}, "
            "steps=[] — all runtime blocks run with defaults (nothing skipped)."
        )

    active = wf.steps
    lines = []
    for step in KNOWN_TOGGLEABLE_STEPS:
        if step in active:
            lines.append(f"  ✅ {step} — ACTIVE (will run)")
        else:
            lines.append(f"  ⏭️  {step} — SKIPPED (not in steps list)")

    extra = [s for s in active if s not in KNOWN_TOGGLEABLE_STEPS]
    if extra:
        lines.append(f"\n  Other active steps: {extra}")

    return (
        f"Step toggles for {platform}:{job_type}:\n"
        f"  Config steps: {active}\n\n"
        + "\n".join(lines)
    )


# ═══════════════════════════════════════════════════════════════
#  Tool 5 — invalidate_workflow_cache
# ═══════════════════════════════════════════════════════════════

@mcp.tool()
def invalidate_workflow_cache() -> str:
    """Force-invalidate the WorkflowRegistry in-memory cache.

    After calling this the next registry read will reload all config
    from the database.  Useful after manually editing DB rows.
    """
    from app.services.workflow_registry import invalidate

    invalidate()
    return "WorkflowRegistry cache invalidated ✓. Next read will reload from DB."

# ═══════════════════════════════════════════════════════════════
#  Tool 6 — get_selector_health
# ═══════════════════════════════════════════════════════════════

@mcp.tool()
def get_selector_health() -> str:
    """Get current selector health stats (in-memory).

    Shows per-selector hit/miss counts, last source (db vs static),
    and last match result.  Counters reset on server restart.
    Sorted by hit rate ascending so problematic selectors appear first.

    Useful for debugging which selectors are failing on the live DOM.
    """
    from app.services.runtime_events import get_selector_health as _get_health
    import time as _time

    stats = _get_health()
    if not stats:
        return "No selector health data yet. Run a publish job first."

    def _sort_key(item):
        s = item[1]
        total = s["hit"] + s["miss"]
        return (s["hit"] / total if total else 0, item[0])

    lines = []
    for key, s in sorted(stats.items(), key=_sort_key):
        total = s["hit"] + s["miss"]
        rate = round(s["hit"] / total * 100) if total else 0
        age = int(_time.time() - s["last_ts"]) if s["last_ts"] else -1
        status = "✅" if rate >= 50 else "⚠️" if rate > 0 else "❌"
        lines.append(
            f"  {status} {key}: {s['hit']}/{total} hits ({rate}%) | "
            f"last={s['last_result']} source={s['last_source']} {age}s ago"
        )
    return f"Selector health ({len(stats)} keys):\n" + "\n".join(lines)

# ═══════════════════════════════════════════════════════════════
#  Tool 7 — list_presets
# ═══════════════════════════════════════════════════════════════

# Import from centralized source
from app.services.workflow_registry import PRESET_DESCRIPTIONS as _PRESET_DESCRIPTIONS

@mcp.tool()
def list_presets(platform: str, job_type: str = "POST") -> str:
    """List all workflow presets for a platform:job_type.

    Shows active and inactive presets with their steps, timing, and description.
    """
    from app.services.workflow_registry import WorkflowRegistry

    presets = WorkflowRegistry.list_presets(platform, job_type)
    if not presets:
        return f"No presets found for {platform}:{job_type}."

    lines = [f"Presets for {platform}:{job_type} ({len(presets)} total):"]
    for p in presets:
        marker = "▶ ACTIVE" if p["is_active"] else "  inactive"
        steps_display = p["steps"] if p["steps"] else "[all defaults]"
        desc = _PRESET_DESCRIPTIONS.get(p["name"], "")
        lines.append(f"\n  {marker} | {p['name']}")
        if desc:
            lines.append(f"    {desc}")
        lines.append(f"    steps: {steps_display}")
        lines.append(f"    timing: {p['timing']}")
    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════
#  Tool 8 — apply_preset
# ═══════════════════════════════════════════════════════════════

@mcp.tool()
def apply_preset(preset_name: str) -> str:
    """Activate a workflow preset by name.

    Deactivates all other presets for the same platform:job_type,
    then activates the specified one. Takes effect immediately
    via cache invalidation.
    """
    from app.services.workflow_registry import WorkflowRegistry
    return WorkflowRegistry.apply_preset(preset_name)

# ═══════════════════════════════════════════════════════════════
#  Tool 9 — preview_runtime_config
# ═══════════════════════════════════════════════════════════════

@mcp.tool()
def preview_runtime_config(platform: str, job_type: str = "POST") -> str:
    """Unified snapshot of all runtime config for a platform:job_type.

    Shows: active preset, steps, timing, CTA pool, and toggleable step
    status — everything that would affect the next publish job.
    Read-only, no side effects.

    Args:
        platform: Platform name, e.g. "facebook"
        job_type: Job type, e.g. "POST" or "COMMENT"
    """
    from app.services.workflow_registry import WorkflowRegistry

    wf = WorkflowRegistry.get_workflow(platform, job_type)

    lines = [f"Runtime config for {platform}:{job_type}:", ""]

    # ── Preset / Workflow ──
    if wf:
        desc = _PRESET_DESCRIPTIONS.get(wf.name, "")
        lines.append(f"  preset: {wf.name}" + (f"  ({desc})" if desc else ""))
        steps_display = wf.steps if wf.steps else "[all defaults — nothing skipped]"
        lines.append(f"  steps:  {steps_display}")
        lines.append(f"  timing: {wf.timing}")
        lines.append(f"  retry:  {wf.retry}")
    else:
        lines.append(f"  preset: NONE — no workflow_definitions row active")
        lines.append(f"  steps:  [all defaults]")
        lines.append(f"  timing: [adapter hardcoded defaults]")

    # ── Step toggles summary ──
    lines.append("")
    active = wf.steps if wf and wf.steps else []
    if active:
        for step in KNOWN_TOGGLEABLE_STEPS:
            status = "✅ RUN" if step in active else "⏭️ SKIP"
            lines.append(f"  {status} {step}")
    else:
        lines.append("  All toggleable steps will RUN (steps=[])")

    # ── CTA pool ──
    lines.append("")
    try:
        cta = WorkflowRegistry.get_cta_templates(platform, locale="vi")
        is_fallback = cta == ["{link}"]
        lines.append(
            f"  CTA pool: {len(cta)} templates (vi)"
            + (" — fallback only" if is_fallback else "")
        )
    except Exception:
        lines.append("  CTA pool: error loading")

    # ── Other presets available ──
    lines.append("")
    try:
        all_presets = WorkflowRegistry.list_presets(platform, job_type)
        inactive = [p["name"] for p in all_presets if not p["is_active"]]
        if inactive:
            lines.append(f"  Other presets: {inactive}")
        else:
            lines.append("  Other presets: none")
    except Exception:
        pass

    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════
#  Tool 10 — preview_selector_resolution
# ═══════════════════════════════════════════════════════════════

@mcp.tool()
def preview_selector_resolution(
    platform: str, category: str, key: str
) -> str:
    """Preview which selectors would be tried for a category:key.

    Shows DB selectors (by priority), static fallback, final order,
    and health stats if available. Read-only, no side effects.

    Args:
        platform: Platform name, e.g. "facebook"
        category: Selector category, e.g. "switch_menu"
        key: Selector key, e.g. "account_menu_button"
    """
    from app.services.workflow_registry import WorkflowRegistry
    from app.services.runtime_events import get_selector_health

    # DB selectors
    db_items = WorkflowRegistry.get_selectors(platform, f"{category}:{key}")

    lines = [f"Selector resolution for {platform} → {category}:{key}", ""]

    # DB layer
    lines.append(f"  DB selectors ({len(db_items)} found):")
    if db_items:
        for i, item in enumerate(db_items):
            lines.append(
                f"    [{i}] p={item.priority} locale={item.locale} "
                f"type={item.selector_type}"
            )
            lines.append(f"        {item.selector_value}")
    else:
        lines.append("    (none)")

    # Static fallback — we can't access the adapter's hardcoded selectors
    # from here without coupling, so we note the behavior
    lines.append("")
    lines.append("  Static fallback: adapter-hardcoded (appended after DB)")
    lines.append(f"  Final order: {len(db_items)} DB → static → first visible match wins")

    # Health stats if available
    lines.append("")
    health = get_selector_health()
    health_key = f"{category}:{key}"
    if health_key in health:
        s = health[health_key]
        total = s["hit"] + s["miss"]
        rate = round(s["hit"] / total * 100) if total else 0
        status = "✅" if rate >= 50 else "⚠️" if rate > 0 else "❌"
        lines.append(
            f"  Health: {status} {s['hit']}/{total} hits ({rate}%) | "
            f"last={s['last_result']} source={s['last_source']}"
        )
    else:
        lines.append("  Health: no data yet (no publish jobs run)")

    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════
#  Entrypoint
# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    mcp.run(transport="stdio")
