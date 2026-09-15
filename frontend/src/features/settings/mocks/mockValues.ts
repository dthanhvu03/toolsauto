import type { SettingsValuesResponse } from "../types/settings.types";

/** TODO: replace with GET /api/settings/values */
export const mockValues: SettingsValuesResponse = {
  values: {
    APP_DISPLAY_NAME: "Auto Publisher",
    SAFE_MODE: false,
    PUBLISHER_PUBLISH_DEADLINE_SEC: 900,
    PUBLISHER_IDLE_ENGAGEMENT_DEADLINE_SEC: 1200,
    IDLE_ENGAGEMENT_COOLDOWN_MINUTES: 45,
    PLAYWRIGHT_DEFAULT_TIMEOUT_MS: 60000,
    MAINT_LOOP_SLEEP_SEC: 300,
    STRATEGIC_BOOST_INTERVAL_SEC: 7200,
    COMMENT_JOB_DELAY_MIN_SEC: 120,
    COMMENT_JOB_DELAY_MAX_SEC: 300,
    TIKWM_API_BASE: "https://api.example.com",
    TIKWM_API_TIMEOUT_SEC: 15,
    VERCEL_REDIRECT_URL: "",
    ADVANCED_DEBUG_VERBOSE: false,
  },
  sources: {
    APP_DISPLAY_NAME: "database",
    SAFE_MODE: "database",
    PUBLISHER_PUBLISH_DEADLINE_SEC: "database",
    MAINT_LOOP_SLEEP_SEC: "environment",
    TIKWM_API_BASE: "database",
  },
  secrets: {
    TELEGRAM_BOT_TOKEN: { hasValue: true },
  },
};
