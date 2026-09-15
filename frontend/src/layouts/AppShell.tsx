import { NavLink, Outlet } from "react-router-dom";
import { Menu, X, LogOut } from "lucide-react";
import { useState } from "react";
import { NAV_GROUPS } from "@/app/nav";
import { cn } from "@/shared/lib/cn";

export function AppShell() {
  const [open, setOpen] = useState(false);

  return (
    <div className="min-h-screen bg-slate-50 text-slate-900">
      {open ? (
        <button
          type="button"
          className="fixed inset-0 z-40 bg-black/30 lg:hidden"
          aria-label="Đóng menu"
          onClick={() => setOpen(false)}
        />
      ) : null}

      <aside
        className={cn(
          "fixed inset-y-0 left-0 z-50 flex w-64 flex-col border-r border-slate-200 bg-white transition-transform lg:translate-x-0",
          open ? "translate-x-0" : "-translate-x-full"
        )}
      >
        <div className="flex h-14 items-center justify-between border-b border-slate-200 px-4">
          <div className="font-semibold tracking-tight">Auto Publisher</div>
          <button type="button" className="lg:hidden" onClick={() => setOpen(false)}>
            <X className="size-5 text-slate-500" />
          </button>
        </div>
        <nav className="flex-1 overflow-y-auto p-3 text-sm">
          {NAV_GROUPS.map((group) => (
            <div key={group.label} className="mb-3">
              <p className="px-3 pb-1.5 pt-2 text-[10px] font-bold uppercase tracking-widest text-slate-400">
                {group.label}
              </p>
              <ul className="flex flex-col gap-0.5">
                {group.items.map((item) => {
                  const Icon = item.icon;
                  return (
                    <li key={item.to}>
                      <NavLink
                        to={item.to}
                        end={item.end}
                        onClick={() => setOpen(false)}
                        className={({ isActive }) =>
                          cn(
                            "flex items-center gap-3 rounded-lg px-3 py-2 font-medium transition-colors",
                            isActive
                              ? "bg-indigo-50 text-indigo-800"
                              : "text-slate-600 hover:bg-slate-50 hover:text-slate-900"
                          )
                        }
                      >
                        <Icon className="size-5 shrink-0 opacity-80" />
                        <span className="truncate">{item.label}</span>
                        {item.reactReady ? (
                          <span className="ml-auto rounded bg-emerald-50 px-1.5 py-0.5 text-[9px] font-bold uppercase text-emerald-700">
                            React
                          </span>
                        ) : null}
                      </NavLink>
                    </li>
                  );
                })}
              </ul>
            </div>
          ))}
        </nav>
        <div className="border-t border-slate-200 p-3">
          <a
            href="/logout"
            className="flex items-center gap-2 rounded-lg px-3 py-2 text-sm font-medium text-red-600 hover:bg-red-50"
          >
            <LogOut className="size-4" />
            Đăng xuất
          </a>
        </div>
      </aside>

      <div className="lg:pl-64">
        <header className="sticky top-0 z-30 flex h-14 items-center gap-3 border-b border-slate-200 bg-white/95 px-4 backdrop-blur">
          <button type="button" className="lg:hidden" onClick={() => setOpen(true)}>
            <Menu className="size-5" />
          </button>
          <div className="text-sm font-medium text-slate-500">Admin · React</div>
        </header>
        <main className="min-h-[calc(100vh-3.5rem)] p-4 md:p-6">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
