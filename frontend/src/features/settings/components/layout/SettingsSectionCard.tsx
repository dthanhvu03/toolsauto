import type { ReactNode } from "react";
import type { SectionId } from "../../types/settings.types";

export function SettingsSectionCard({
  sectionId,
  title,
  modified,
  children,
  footer,
}: {
  sectionId: SectionId;
  title: string;
  modified: boolean;
  children: ReactNode;
  footer: ReactNode;
}) {
  return (
    <section
      id={`section-${sectionId}`}
      className="scroll-mt-28 rounded-2xl border border-slate-100 bg-white shadow-sm"
    >
      <div className="border-b border-slate-100 bg-slate-50/60 px-5 py-4">
        <h2 className="flex items-center gap-2 font-display text-base font-semibold text-slate-900">
          <span className="h-2 w-2 rounded-full bg-indigo-400" />
          {title}
          {modified ? (
            <span className="rounded-full bg-amber-100 px-2 py-0.5 text-[10px] font-bold uppercase text-amber-800">
              Modified
            </span>
          ) : null}
        </h2>
      </div>
      <div className="space-y-4 p-4 md:p-5">{children}</div>
      <div className="border-t border-slate-100 bg-slate-50/40 px-5 py-3">{footer}</div>
    </section>
  );
}
