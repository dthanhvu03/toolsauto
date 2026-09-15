import { SettingsPage } from "@/features/settings/pages/SettingsPage";

/** Settings embedded in AppShell (no duplicate full-page chrome). */
export function SettingsRoute() {
  return <SettingsPage embedded />;
}
