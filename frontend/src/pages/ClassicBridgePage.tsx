import { ExternalLink } from "lucide-react";

export function ClassicBridgePage({
  title,
  description,
  classicHref,
}: {
  title: string;
  description?: string;
  classicHref: string;
}) {
  return (
    <div className="mx-auto max-w-2xl rounded-2xl border border-slate-200 bg-white p-8 shadow-sm">
      <h1 className="text-xl font-semibold text-slate-900">{title}</h1>
      <p className="mt-2 text-sm text-slate-600">
        {description ??
          "Trang này đang được chuyển sang React. Tạm thời dùng bản classic (Jinja/HTMX) — cùng backend, cùng dữ liệu."}
      </p>
      <a
        href={classicHref}
        className="mt-6 inline-flex items-center gap-2 rounded-lg bg-indigo-600 px-4 py-2.5 text-sm font-semibold text-white hover:bg-indigo-700"
      >
        Mở bản classic
        <ExternalLink className="size-4" />
      </a>
      <p className="mt-4 text-xs text-slate-400">
        Stack: React · Vite · TanStack Query · React Router · Tailwind. Port từng module khi ổn
        định.
      </p>
    </div>
  );
}
