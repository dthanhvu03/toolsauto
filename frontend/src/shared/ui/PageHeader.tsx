import { ExternalLink } from "lucide-react";
import type { ReactNode } from "react";
import { cn } from "@/shared/lib/cn";

export function PageHeader({
  title,
  subtitle,
  classicHref,
  classicLabel = "Classic",
  classicHover = "hover:underline",
}: {
  title: string;
  subtitle?: ReactNode;
  classicHref?: string;
  classicLabel?: string;
  classicHover?: string;
}) {
  return (
    <div className="flex flex-wrap items-end justify-between gap-3">
      <div>
        <h1 className="text-2xl font-semibold text-slate-900">{title}</h1>
        {subtitle != null && subtitle !== "" ? (
          <p className="mt-1 text-sm text-slate-500">{subtitle}</p>
        ) : null}
      </div>
      {classicHref ? (
        <a
          href={classicHref}
          className={cn(
            "inline-flex items-center gap-1 text-xs font-medium text-slate-400",
            classicHover
          )}
        >
          {classicLabel} <ExternalLink className="size-3" />
        </a>
      ) : null}
    </div>
  );
}
