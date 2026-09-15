import type { FieldValueSource } from "../../types/settings.types";
import type { ReactNode } from "react";

function Badge({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <span
      className={`inline-flex items-center rounded px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-wide ${className ?? ""}`}
    >
      {children}
    </span>
  );
}

export function SettingsBadgeGroup({
  restartRequired,
  source,
}: {
  restartRequired?: boolean;
  source?: FieldValueSource;
}) {
  return (
    <>
      {restartRequired ? (
        <Badge className="border border-amber-200 bg-amber-50 text-amber-800">Restart</Badge>
      ) : null}
      {source ? (
        <Badge
          className={
            source === "environment"
              ? "border border-violet-200 bg-violet-50 text-violet-800"
              : source === "database"
                ? "border border-sky-200 bg-sky-50 text-sky-800"
                : "border border-slate-200 bg-slate-100 text-slate-600"
          }
        >
          {source}
        </Badge>
      ) : null}
    </>
  );
}
