import type { ReactNode } from "react";

export function FieldLabel({ children, right }: { children: ReactNode; right?: ReactNode }) {
  return (
    <div className="flex items-start justify-between gap-2">
      <span className="text-sm font-semibold text-slate-800">{children}</span>
      {right ? <div className="flex shrink-0 items-center gap-1">{right}</div> : null}
    </div>
  );
}
