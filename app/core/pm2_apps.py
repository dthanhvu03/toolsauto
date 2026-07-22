"""Single source of PM2 app names used by syspanel UI and log whitelist.

Keep in sync with ``ecosystem.config.js`` ``apps[].name``.
"""

from __future__ import annotations

# Names from ecosystem.config.js (plus legacy single-instance aliases).
PM2_SAFE_NAMES: frozenset[str] = frozenset({
    "FB_Publisher_1",
    "FB_Publisher_2",
    "AI_Generator_1",
    "AI_Generator_2",
    "Maintenance",
    "Web_Dashboard",
    "9Router_Gateway",
    "Threads_AutoReply",
    "Threads_NewsWorker",
    "Threads_Publisher",
    # Legacy (pre _1/_2 scaling)
    "FB_Publisher",
    "AI_Generator",
})

# PM2 log filename stems (PM2 turns '_' → '-' in log file names).
PM2_LOG_MAP: dict[str, dict[str, str]] = {
    "FB_Publisher_1": {"out": "FB-Publisher-1-out.log", "error": "FB-Publisher-1-error.log"},
    "FB_Publisher_2": {"out": "FB-Publisher-2-out.log", "error": "FB-Publisher-2-error.log"},
    "AI_Generator_1": {"out": "AI-Generator-1-out.log", "error": "AI-Generator-1-error.log"},
    "AI_Generator_2": {"out": "AI-Generator-2-out.log", "error": "AI-Generator-2-error.log"},
    "Maintenance": {"out": "Maintenance-out.log", "error": "Maintenance-error.log"},
    "Web_Dashboard": {"out": "Web-Dashboard-out.log", "error": "Web-Dashboard-error.log"},
    "Threads_Publisher": {"out": "Threads-Publisher-out.log", "error": "Threads-Publisher-error.log"},
    "Threads_NewsWorker": {"out": "Threads-NewsWorker-out.log", "error": "Threads-NewsWorker-error.log"},
    "Threads_AutoReply": {"out": "Threads-AutoReply-out.log", "error": "Threads-AutoReply-error.log"},
    # Legacy aliases → primary instance logs
    "FB_Publisher": {"out": "FB-Publisher-1-out.log", "error": "FB-Publisher-1-error.log"},
    "AI_Generator": {"out": "AI-Generator-1-out.log", "error": "AI-Generator-1-error.log"},
}
