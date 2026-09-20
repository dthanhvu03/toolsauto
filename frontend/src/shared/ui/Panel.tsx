import type { ReactNode } from "react";
import { cn } from "@/shared/lib/cn";

export function Panel({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <div
      className={cn(
        "overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm",
        className
      )}
    >
      {children}
    </div>
  );
}
