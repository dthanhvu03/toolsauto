import type { SectionId } from "../../types/settings.types";

export function SettingsSectionNav({
  sectionOrder,
  labels,
  counts,
  activeSection,
  onNavigate,
}: {
  sectionOrder: SectionId[];
  labels: Record<string, string>;
  counts: Record<string, number>;
  activeSection?: SectionId;
  onNavigate: (id: SectionId) => void;
}) {
  return (
    <nav className="sticky top-[57px] hidden h-[calc(100vh-57px)] w-56 shrink-0 self-start overflow-y-auto border-r border-slate-100 bg-white/50 py-4 pr-3 lg:block">
      <div className="mb-2 px-2 text-[10px] font-bold uppercase tracking-widest text-slate-400">
        Sections
      </div>
      <ul className="space-y-0.5">
        {sectionOrder.map((id) => (
          <li key={id}>
            <button
              type="button"
              onClick={() => onNavigate(id)}
              className={`flex w-full items-center gap-2 rounded-lg px-3 py-2 text-left text-sm font-medium transition-colors ${
                activeSection === id
                  ? "bg-indigo-50 text-indigo-800"
                  : "text-slate-600 hover:bg-slate-50 hover:text-slate-900"
              }`}
            >
              <span
                className={`h-1.5 w-1.5 shrink-0 rounded-full ${
                  activeSection === id ? "bg-indigo-500" : "bg-slate-300"
                }`}
              />
              <span className="truncate">{labels[id] ?? id}</span>
              <span className="ml-auto tabular-nums text-[10px] text-slate-400">
                {counts[id] ?? 0}
              </span>
            </button>
          </li>
        ))}
      </ul>
    </nav>
  );
}
