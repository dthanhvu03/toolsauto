import { mmss } from "../lib/status";
import type { ProjectSpec, SubLine } from "../types/studio.types";

/**
 * Sửa từng câu phụ đề. Số thứ tự câu tính theo đoạn cắt **đã lưu** — đổi đoạn cắt thì phải lưu &
 * render trước (server bỏ sửa tay cũ vì số câu đã lệch).
 */
export function SubtitleEditor({
  sub,
  lines,
  locked,
  disabled,
  onChange,
}: {
  sub: ProjectSpec["subtitles"];
  lines: SubLine[];
  locked: boolean;
  disabled: boolean;
  onChange: (sub: ProjectSpec["subtitles"]) => void;
}) {
  const setEdit = (i: number, text: string, original: string) => {
    const edits = { ...sub.edits };
    if (text === original) delete edits[String(i)];
    else edits[String(i)] = text;
    onChange({ ...sub, edits });
  };
  // Không có câu nào thì ô «Đốt phụ đề» vô nghĩa (bật cũng không có chữ) — chỉ báo lý do.
  if (!locked && lines.length === 0) {
    return <p className="text-sm text-slate-500">Video không có lời thoại (Whisper không nghe ra câu nào) — không có phụ đề.</p>;
  }
  return (
    <div>
      <label className="flex items-center gap-2 text-sm">
        <input type="checkbox" checked={sub.enabled} disabled={disabled} onChange={(e) => onChange({ ...sub, enabled: e.target.checked })} />
        Đốt phụ đề {sub.source === "dub" ? "(câu đã lồng tiếng)" : ""}
      </label>
      {locked ? (
        <p className="mt-2 rounded-lg bg-amber-50 px-3 py-2 text-xs text-amber-900">Đoạn cắt vừa đổi — lưu & render trước rồi sửa phụ đề.</p>
      ) : (
        <ol className="mt-2 flex max-h-80 flex-col gap-1 overflow-y-auto pr-1">
          {lines.map((line, i) => {
            const value = sub.edits[String(i)] ?? line.text;
            return (
              <li key={i} className="flex items-center gap-2">
                <span className="w-16 shrink-0 text-[11px] tabular-nums text-slate-400">
                  {mmss(line.start)}–{mmss(line.end)}
                </span>
                <input
                  className={`h-8 flex-1 rounded-lg border px-2 text-sm ${value.trim() ? "border-slate-200" : "border-red-200 bg-red-50 line-through"}`}
                  value={value}
                  disabled={disabled || !sub.enabled}
                  placeholder="(bỏ câu này)"
                  onChange={(e) => setEdit(i, e.target.value, line.text)}
                />
              </li>
            );
          })}
        </ol>
      )}
      <p className="mt-1 text-[11px] text-slate-400">Xoá trắng một câu = bỏ câu đó.</p>
    </div>
  );
}
