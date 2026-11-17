import { NavLink, Outlet, useLocation } from "react-router-dom";
import { Coins, Home, Menu, MessageCircle, Users, X, LogOut } from "lucide-react";
import { useEffect, useState } from "react";
import { Dialog } from "radix-ui";
import { NAV_GROUPS } from "@/app/nav";
import { cn } from "@/shared/lib/cn";

const TAB_BAR = [
  { to: "/app", label: "Tổng quan", icon: Home, external: false, end: true },
  { to: "/app/go/threads-growth", label: "Threads", icon: MessageCircle, external: false, end: false },
  { to: "/cashback", label: "Cashback", icon: Coins, external: true, end: false },
  { to: "/app/go/bot-users", label: "Khách", icon: Users, external: false, end: false },
] as const;

const tabClass = (active: boolean) => cn(
  "flex min-h-16 min-w-0 flex-1 flex-col items-center justify-center gap-1 rounded-xl px-1 text-[11px] font-medium transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-indigo-600",
  active ? "bg-indigo-50 text-indigo-700" : "text-slate-500 active:bg-slate-100 active:text-slate-900"
);

function Navigation({ onNavigate }: { onNavigate?: () => void }) {
  return <>
    <nav aria-label="Tất cả chức năng" className="min-h-0 flex-1 overflow-y-auto overscroll-contain p-3 text-sm">
      {NAV_GROUPS.map((group) => (
        <div key={group.label || "home"} className="mb-3">
          {group.label ? <p className="px-3 pb-1.5 pt-2 text-xs font-semibold text-slate-500">{group.label}</p> : null}
          <ul className="flex flex-col gap-1">
            {group.items.map((item) => {
              const Icon = item.icon;
              const content = <><Icon className="size-5 shrink-0" /><span className="truncate">{item.label}</span></>;
              const classes = "flex min-h-11 items-center gap-3 rounded-xl px-3 py-2 font-medium transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-indigo-600";
              return <li key={item.to}>
                {item.external ? (
                  <a href={item.to} onClick={onNavigate} className={cn(classes, "text-slate-600 hover:bg-slate-50 hover:text-slate-900")}>{content}</a>
                ) : (
                  <NavLink to={item.to} end={item.end} onClick={onNavigate} className={({ isActive }) => cn(classes,
                    isActive ? "bg-indigo-50 text-indigo-800" : "text-slate-600 hover:bg-slate-50 hover:text-slate-900")}>{content}</NavLink>
                )}
              </li>;
            })}
          </ul>
        </div>
      ))}
    </nav>
    <div className="border-t border-slate-200 p-3 pb-[max(.75rem,env(safe-area-inset-bottom))]">
      <a href="/logout" className="flex min-h-11 items-center gap-3 rounded-xl px-3 text-sm font-medium text-red-600 hover:bg-red-50">
        <LogOut className="size-5" />Đăng xuất
      </a>
    </div>
  </>;
}

export function AppShell() {
  const [open, setOpen] = useState(false);
  const { pathname } = useLocation();
  const current = NAV_GROUPS.flatMap((group) => group.items)
    .filter((item) => !item.external && (item.end ? pathname === item.to : pathname === item.to || pathname.startsWith(`${item.to}/`)))
    .sort((a, b) => b.to.length - a.to.length)[0];

  useEffect(() => { setOpen(false); }, [pathname]);
  useEffect(() => {
    const desktop = window.matchMedia("(min-width: 1024px)");
    const closeOnDesktop = () => { if (desktop.matches) setOpen(false); };
    desktop.addEventListener("change", closeOnDesktop);
    return () => desktop.removeEventListener("change", closeOnDesktop);
  }, []);

  return (
    <Dialog.Root open={open} onOpenChange={setOpen}>
      <div className="min-h-dvh bg-slate-50 text-slate-900">
        <aside className="fixed inset-y-0 left-0 z-40 hidden w-64 flex-col border-r border-slate-200 bg-white lg:flex">
          <div className="flex h-14 shrink-0 items-center border-b border-slate-200 px-6 font-semibold tracking-tight">ToolsAuto</div>
          <Navigation />
        </aside>
        <Dialog.Portal>
          <Dialog.Overlay className="fixed inset-0 z-40 bg-slate-950/40 backdrop-blur-sm lg:hidden" />
          <Dialog.Content aria-describedby={undefined} className="fixed inset-y-0 left-0 z-50 flex w-[min(21rem,90vw)] flex-col border-r border-slate-200 bg-white pt-[env(safe-area-inset-top)] shadow-2xl focus:outline-none lg:hidden">
            <div className="flex h-16 shrink-0 items-center justify-between border-b border-slate-200 px-4">
              <Dialog.Title className="text-lg font-semibold tracking-tight">ToolsAuto</Dialog.Title>
              <Dialog.Close aria-label="Đóng menu" className="flex size-11 items-center justify-center rounded-xl text-slate-500 hover:bg-slate-100"><X className="size-5" /></Dialog.Close>
            </div>
            <Navigation onNavigate={() => setOpen(false)} />
          </Dialog.Content>
        </Dialog.Portal>

        <div className="min-w-0 lg:pl-64">
          <header className="sticky top-0 z-30 flex h-14 items-center gap-3 border-b border-slate-200 bg-white/95 px-3 backdrop-blur lg:px-6">
            <Dialog.Trigger aria-label="Mở menu" className="flex size-11 shrink-0 items-center justify-center rounded-xl hover:bg-slate-100 lg:hidden"><Menu className="size-5" /></Dialog.Trigger>
            <div className="min-w-0 flex-1 truncate text-sm font-semibold">{current?.label || "ToolsAuto"}</div>
            <span className="hidden text-xs text-slate-400 sm:inline">ToolsAuto</span>
          </header>
          <main className="min-h-[calc(100dvh-3.5rem)] min-w-0 p-4 pb-[calc(6rem+env(safe-area-inset-bottom))] md:p-6 md:pb-[calc(6rem+env(safe-area-inset-bottom))] lg:pb-6"><Outlet /></main>
        </div>

        <nav aria-label="Trang chính" className="fixed inset-x-0 bottom-0 z-30 flex gap-1 border-t border-slate-200 bg-white/95 px-2 pb-[env(safe-area-inset-bottom)] pt-1 backdrop-blur lg:hidden">
          {TAB_BAR.map((tab) => {
            const Icon = tab.icon;
            const content = <><Icon aria-hidden="true" className="size-5" /><span className="truncate">{tab.label}</span></>;
            return tab.external ? <a key={tab.to} href={tab.to} className={tabClass(false)}>{content}</a> : (
              <NavLink key={tab.to} to={tab.to} end={tab.end} className={({ isActive }) => tabClass(isActive)}>{content}</NavLink>
            );
          })}
          <Dialog.Trigger className={tabClass(open)}><Menu aria-hidden="true" className="size-5" /><span>Menu</span></Dialog.Trigger>
        </nav>
      </div>
    </Dialog.Root>
  );
}
