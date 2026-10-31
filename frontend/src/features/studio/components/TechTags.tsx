/** Nhãn kỹ thuật của một dự án (server dựng từ spec — luôn khớp bản render). */
export function TechTags({ tags, className = "" }: { tags: string[]; className?: string }) {
  if (!tags.length) return null;
  const tone = (t: string) =>
    t === "Sưu tầm"
      ? "bg-amber-100 text-amber-900"
      : t === "Lật gương" || t.startsWith("Màu ") || t === "Lồng tiếng" || t === "Phụ đề dịch"
        ? "bg-violet-100 text-violet-800"
        : t.startsWith("Mẫu ")
          ? "bg-indigo-50 text-indigo-700"
          : "bg-slate-100 text-slate-600";
  return (
    <ul className={`flex flex-wrap gap-1 ${className}`}>
      {tags.map((t) => (
        <li key={t} className={`rounded px-1.5 py-0.5 text-[10px] font-medium ${tone(t)}`}>
          {t}
        </li>
      ))}
    </ul>
  );
}
