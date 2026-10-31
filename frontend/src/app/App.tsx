import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { AppShell } from "@/layouts/AppShell";
import { OverviewPage } from "@/features/overview/pages/OverviewPage";
import { SettingsRoute } from "@/features/settings/routes/SettingsRoute";
import { JobsPage } from "@/features/jobs/pages/JobsPage";
import { ViralPage } from "@/features/viral/pages/ViralPage";
import { ViralSourcesPage } from "@/features/viral-sources/pages/ViralSourcesPage";
import { CompliancePage } from "@/features/compliance/pages/CompliancePage";
import { LogsPage } from "@/features/logs/pages/LogsPage";
import { AiStudioPage } from "@/features/ai-studio/pages/AiStudioPage";
import { SyspanelPage } from "@/features/syspanel/pages/SyspanelPage";
import { DatabasePage } from "@/features/database/pages/DatabasePage";
import { TelegramUxPage } from "@/features/telegram/pages/TelegramUxPage";
import { StudioBoardPage } from "@/features/studio/pages/StudioBoardPage";
import { DoctypeListPage } from "@/features/doctype/pages/DoctypeListPage";
import { DoctypeBuilderPage } from "@/features/doctype/pages/DoctypeBuilderPage";
import { RecordListPage } from "@/features/doctype/pages/RecordListPage";
import { RecordFormPage } from "@/features/doctype/pages/RecordFormPage";
import { StudioEditorPage } from "@/features/studio/pages/StudioEditorPage";
import { StudioAssetsPage } from "@/features/studio/pages/StudioAssetsPage";
import { StudioSetupPage } from "@/features/studio/pages/StudioSetupPage";
import { StudioTiktokPage } from "@/features/studio/pages/StudioTiktokPage";

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
            <Route path="go/studio" element={<StudioBoardPage />} />
            <Route path="go/studio/:id" element={<StudioEditorPage />} />
            <Route path="go/studio-assets" element={<StudioAssetsPage />} />
            <Route path="go/studio-setup" element={<StudioSetupPage />} />
            <Route path="go/studio-tiktok" element={<StudioTiktokPage />} />
            <Route path="go/viral" element={<ViralPage />} />
            <Route path="go/viral-sources" element={<ViralSourcesPage />} />
            <Route path="go/compliance" element={<CompliancePage />} />
            <Route path="go/logs" element={<LogsPage />} />
            <Route path="go/ai-studio" element={<AiStudioPage />} />
            <Route path="go/syspanel" element={<SyspanelPage />} />
            <Route path="go/database" element={<DatabasePage />} />
            <Route path="go/telegram" element={<TelegramUxPage />} />
            <Route path="go/doctype" element={<DoctypeListPage />} />
            <Route path="go/doctype/:name" element={<DoctypeBuilderPage />} />
            <Route path="go/doc/:doctype" element={<RecordListPage />} />
            <Route path="go/doc/:doctype/:name" element={<RecordFormPage />} />
            <Route path="*" element={<Navigate to="/app" replace />} />
          </Route>
          <Route path="/" element={<Navigate to="/app" replace />} />
          <Route path="*" element={<Navigate to="/app" replace />} />
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  );
}
