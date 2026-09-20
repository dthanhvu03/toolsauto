import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { AppShell } from "@/layouts/AppShell";
import { OverviewPage } from "@/features/overview/pages/OverviewPage";
import { SettingsRoute } from "@/features/settings/routes/SettingsRoute";
import { JobsPage } from "@/features/jobs/pages/JobsPage";
import { AccountsPage } from "@/features/accounts/pages/AccountsPage";
import { ViralPage } from "@/features/viral/pages/ViralPage";
import { AffiliatesPage } from "@/features/affiliates/pages/AffiliatesPage";
import { ViralSourcesPage } from "@/features/viral-sources/pages/ViralSourcesPage";
import { TiktokLinksPage } from "@/features/tiktok-links/pages/TiktokLinksPage";
import { InsightsPage } from "@/features/insights/pages/InsightsPage";
import { FbProTasksPage } from "@/features/fb-pro-tasks/pages/FbProTasksPage";
import { CompliancePage } from "@/features/compliance/pages/CompliancePage";
import { ThreadsPage } from "@/features/threads/pages/ThreadsPage";
import { LogsPage } from "@/features/logs/pages/LogsPage";
import { ControlPlanePage } from "@/features/control-plane/pages/ControlPlanePage";
import { AiStudioPage } from "@/features/ai-studio/pages/AiStudioPage";
import { PlatformConfigPage } from "@/features/platform-config/pages/PlatformConfigPage";
import { SyspanelPage } from "@/features/syspanel/pages/SyspanelPage";
import { DatabasePage } from "@/features/database/pages/DatabasePage";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { staleTime: 30_000, refetchOnWindowFocus: false },
  },
});

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Routes>
          <Route path="/app" element={<AppShell />}>
            <Route index element={<OverviewPage />} />
            <Route path="settings" element={<SettingsRoute />} />
            <Route path="go/jobs" element={<JobsPage />} />
            <Route
              path="go/jobs-threads"
              element={
                <JobsPage
                  title="Hàng đợi Threads"
                  defaultPlatform="threads"
                  classicHref="/app/jobs?platform=threads"
                />
              }
            />
            <Route path="go/accounts" element={<AccountsPage />} />
            <Route path="go/viral" element={<ViralPage />} />
            <Route path="go/affiliates" element={<AffiliatesPage />} />
            <Route path="go/viral-sources" element={<ViralSourcesPage />} />
            <Route path="go/tiktok-links" element={<TiktokLinksPage />} />
            <Route path="go/insights" element={<InsightsPage />} />
            <Route path="go/fb-pro-tasks" element={<FbProTasksPage />} />
            <Route path="go/compliance" element={<CompliancePage />} />
            <Route path="go/threads" element={<ThreadsPage />} />
            <Route path="go/logs" element={<LogsPage />} />
            <Route path="go/control-plane" element={<ControlPlanePage />} />
            <Route path="go/ai-studio" element={<AiStudioPage />} />
            <Route path="go/platform-config" element={<PlatformConfigPage />} />
            <Route path="go/syspanel" element={<SyspanelPage />} />
            <Route path="go/database" element={<DatabasePage />} />
            <Route path="*" element={<Navigate to="/app" replace />} />
          </Route>
          <Route path="/" element={<Navigate to="/app" replace />} />
          <Route path="*" element={<Navigate to="/app" replace />} />
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  );
}
