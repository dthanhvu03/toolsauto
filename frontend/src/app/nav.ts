import type { LucideIcon } from "lucide-react";
import {
  BarChart3,
  Boxes,
  ClipboardList,
  Database,
  Home,
  Link2,
  ListTodo,
  ScrollText,
  Settings,
  ShieldAlert,
  Sparkles,
  Users,
  Workflow,
  Zap,
  LayoutGrid,
  Server,
} from "lucide-react";

export type NavItem = {
  to: string;
  label: string;
  icon: LucideIcon;
  classicHref?: string;
  reactReady?: boolean;
  end?: boolean;
};

export type NavGroup = {
  label: string;
  items: NavItem[];
};

/** Native React pages (not Jinja iframe). */
export const NATIVE_APP_PATHS = new Set([
  "/app",
  "/app/",
  "/app/settings",
  "/app/go/jobs",
  "/app/go/jobs-threads",
  "/app/go/accounts",
  "/app/go/viral",
  "/app/go/affiliates",
  "/app/go/viral-sources",
  "/app/go/tiktok-links",
  "/app/go/insights",
  "/app/go/fb-pro-tasks",
  "/app/go/compliance",
  "/app/go/threads",
  "/app/go/logs",
  "/app/go/control-plane",
  "/app/go/ai-studio",
  "/app/go/platform-config",
  "/app/go/syspanel",
  "/app/go/database",
]);

/** React routes under /app — remaining /app/go/* embed Jinja (embed=1). */
export const NAV_GROUPS: NavGroup[] = [
  {
    label: "Chung",
    items: [
      { to: "/app", label: "Tổng quan", icon: Home, end: true, reactReady: true },
      {
        to: "/app/go/jobs",
        label: "Hàng đợi job",
        icon: ListTodo,
        classicHref: "/app/jobs",
        reactReady: true,
      },
      {
        to: "/app/go/accounts",
        label: "Tài khoản",
        icon: Users,
        classicHref: "/app/accounts",
        reactReady: true,
      },
      { to: "/app/go/affiliates", label: "Kho affiliate", icon: Boxes, classicHref: "/affiliates", reactReady: true },
    ],
  },
  {
    label: "Facebook",
    items: [
      {
        to: "/app/go/viral",
        label: "Nội dung viral",
        icon: Zap,
        classicHref: "/app/viral",
        reactReady: true,
      },
      {
        to: "/app/go/viral-sources",
        label: "Nguồn video",
        icon: Link2,
        classicHref: "/app/viral/sources",
        reactReady: true,
      },
      {
        to: "/app/go/tiktok-links",
        label: "Kho kênh cũ",
        icon: ClipboardList,
        classicHref: "/app/tiktok-links",
        reactReady: true,
      },
      {
        to: "/app/go/insights",
        label: "Phân tích & tăng trưởng",
        icon: BarChart3,
        classicHref: "/insights?platform=facebook",
        reactReady: true,
      },
      {
        to: "/app/go/fb-pro-tasks",
        label: "Nhiệm vụ FB",
        icon: Workflow,
        classicHref: "/app/fb-pro-tasks/",
        reactReady: true,
      },
      {
        to: "/app/go/compliance",
        label: "Vi phạm Facebook",
        icon: ShieldAlert,
        classicHref: "/compliance/",
        reactReady: true,
      },
    ],
  },
  {
    label: "Threads",
    items: [
      { to: "/app/go/threads", label: "Threads", icon: ScrollText, classicHref: "/threads", reactReady: true },
      {
        to: "/app/go/jobs-threads",
        label: "Hàng đợi Threads",
        icon: ListTodo,
        classicHref: "/app/jobs?platform=threads",
        reactReady: true,
      },
    ],
  },
  {
    label: "Giám sát",
    items: [
      { to: "/app/go/logs", label: "Nhật ký hệ thống", icon: ScrollText, classicHref: "/app/logs", reactReady: true },
    ],
  },
  {
    label: "Cấu hình",
    items: [
      {
        to: "/app/go/control-plane",
        label: "Hub cấu hình",
        icon: LayoutGrid,
        classicHref: "/app/control-plane",
        reactReady: true,
      },
      { to: "/app/settings", label: "Cài đặt vận hành", icon: Settings, reactReady: true },
      {
        to: "/app/go/ai-studio",
        label: "AI Studio",
        icon: Sparkles,
        classicHref: "/app/ai-studio",
        reactReady: true,
      },
      {
        to: "/app/go/platform-config",
        label: "Cấu hình nền tảng",
        icon: Server,
        classicHref: "/platform-config/",
        reactReady: true,
      },
      { to: "/app/go/syspanel", label: "Panel hệ thống", icon: Server, classicHref: "/syspanel", reactReady: true },
      { to: "/app/go/database", label: "Database", icon: Database, classicHref: "/database", reactReady: true },
    ],
  },
];
