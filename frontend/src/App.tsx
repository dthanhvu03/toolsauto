import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { AppShell } from "@/layouts/AppShell";
import { OverviewPage } from "@/pages/OverviewPage";
import { SettingsRoute } from "@/pages/SettingsRoute";
import { ClassicBridgePage } from "@/pages/ClassicBridgePage";
import { JobsPage } from "@/pages/JobsPage";
import { AccountsPage } from "@/pages/AccountsPage";
import { ViralPage } from "@/pages/ViralPage";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { staleTime: 30_000, refetchOnWindowFocus: false },
  },
});

function bridge(title: string, href: string) {
  return <ClassicBridgePage title={title} classicHref={href} />;
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Routes>
          <Route path="/app" element={<AppShell />}>
            <Route index element={<OverviewPage />} />
            <Route path="settings" element={<SettingsRoute />} />
            {/* Native React lists — under /app/go/* so Jinja /app/jobs|accounts|viral stay intact */}
            <Route path="go/jobs" element={<JobsPage />} />
            <Route path="go/accounts" element={<AccountsPage />} />
            <Route path="go/viral" element={<ViralPage />} />
            <Route
              path="go/jobs-threads"
              element={bridge("Hàng đợi Threads", "/app/jobs?platform=threads")}
            />
            <Route path="go/affiliates" element={bridge("Kho affiliate", "/affiliates")} />
            <Route path="go/viral-sources" element={bridge("Nguồn video", "/app/viral/sources")} />
            <Route path="go/tiktok-links" element={bridge("Kho kênh cũ", "/app/tiktok-links")} />
            <Route
              path="go/insights"
              element={bridge("Phân tích & tăng trưởng", "/insights?platform=facebook")}
            />
            <Route path="go/fb-pro-tasks" element={bridge("Nhiệm vụ FB", "/app/fb-pro-tasks/")} />
            <Route path="go/compliance" element={bridge("Vi phạm Facebook", "/compliance/")} />
            <Route path="go/threads" element={bridge("Threads", "/threads")} />
            <Route path="go/logs" element={bridge("Nhật ký hệ thống", "/app/logs")} />
            <Route path="go/control-plane" element={bridge("Hub cấu hình", "/app/control-plane")} />
            <Route path="go/ai-studio" element={bridge("AI Studio", "/app/ai-studio")} />
            <Route
              path="go/platform-config"
              element={bridge("Cấu hình nền tảng", "/platform-config/")}
            />
            <Route path="go/syspanel" element={bridge("Panel hệ thống", "/syspanel")} />
            <Route path="go/database" element={bridge("Database", "/database")} />
            <Route path="*" element={<Navigate to="/app" replace />} />
          </Route>
          <Route path="/" element={<Navigate to="/app" replace />} />
          <Route path="*" element={<Navigate to="/app" replace />} />
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  );
}
