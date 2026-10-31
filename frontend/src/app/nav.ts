import type { LucideIcon } from "lucide-react";
import {
  Database,
  Clapperboard,
  Film,
  Home,
  Layers,
  Link2,
  ListTodo,
  Orbit,
  ScrollText,
  Send,
  Server,
  Settings,
  ShieldAlert,
  SlidersHorizontal,
  Sparkles,
} from "lucide-react";

export type NavItem = {
  to: string;
  label: string;
  icon: LucideIcon;
  /** Trang ngoài SPA (Jinja / trang riêng) — mở bằng <a>, không qua React Router. */
  external?: boolean;
  end?: boolean;
};

export type NavGroup = {
  label: string;
  items: NavItem[];
};

/**
 * PLAN-108: chia theo module của luồng thật — video → Buffer.
 * Sidebar Jinja (`app/templates/layouts/app.html`) dùng cùng nhóm; sửa một bên thì sửa cả hai.
 */
export const NAV_GROUPS: NavGroup[] = [
  {
    label: "",
    items: [{ to: "/app", label: "Tổng quan", icon: Home, end: true }],
  },
  {
    label: "Video",
    items: [
      { to: "/app/go/studio", label: "Studio", icon: Clapperboard },
      { to: "/app/go/studio-assets", label: "Nguyên liệu", icon: Layers },
      { to: "/app/go/studio-setup", label: "Kênh & mẫu", icon: SlidersHorizontal },
      { to: "/app/go/viral", label: "Kho video", icon: Film },
      { to: "/app/go/viral-sources", label: "Nguồn video", icon: Link2 },
    ],
  },
  {
    label: "Buffer",
    items: [
      { to: "/app/go/jobs", label: "Lịch đăng", icon: ListTodo },
      { to: "/buffer-cluster", label: "Cụm Buffer", icon: Orbit, external: true },
    ],
  },
  {
    label: "Nội dung & AI",
    items: [
      { to: "/app/go/ai-studio", label: "AI", icon: Sparkles },
      { to: "/app/go/compliance", label: "Từ khoá cấm", icon: ShieldAlert },
    ],
  },
  {
    label: "Hệ thống",
    items: [
      { to: "/app/go/logs", label: "Nhật ký", icon: ScrollText },
      { to: "/app/settings", label: "Cài đặt vận hành", icon: Settings },
      { to: "/app/go/syspanel", label: "Panel hệ thống", icon: Server },
      { to: "/app/go/database", label: "Database", icon: Database },
      { to: "/app/go/telegram", label: "Telegram", icon: Send },
    ],
  },
];
