import { Check, Clock, Eye, Film, Search } from "lucide-react";
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { cn } from "@/shared/lib/cn";
import { ghostBtnClass, inputClass, primaryBtnClass, selectClass } from "@/shared/ui/controls";
import { PageHeader } from "@/shared/ui/PageHeader";
import { Panel } from "@/shared/ui/Panel";
import { Toast } from "@/shared/ui/Toast";
import * as api from "../api/studioApi";
import { JobsPanel } from "../components/JobsPanel";
import { DEFAULT_TECHNIQUES, TechniquePicker } from "../components/TechniquePicker";
import { useAction, useSetup } from "../hooks/useStudio";
import { mmss } from "../lib/status";
import type { Techniques, TikTokItem } from "../types/studio.types";

const TRACK_KEY = "studio-tiktok-tracked";

/** Việc vừa gửi ở trang này — nhớ trong trình duyệt để tải lại trang vẫn theo dõi được (không có cũng không sao). */
function loadTracked(): number[] {
  try {
    const v = JSON.parse(localStorage.getItem(TRACK_KEY) || "[]");
    return Array.isArray(v) ? v.filter((x) => Number.isInteger(x)).slice(0, 100) : [];
  } catch {
    return [];
  }
}

function saveTracked(ids: number[]) {
  try {
    localStorage.setItem(TRACK_KEY, JSON.stringify(ids));
  } catch {
    /* chế độ ẩn danh / chặn lưu: chỉ mất phần nhớ khi tải lại */
  }
}

const views = new Intl.NumberFormat("vi-VN", { notation: "compact", maximumFractionDigits: 1 });

/** Một dòng tóm tắt kỹ thuật đang bật (thanh dưới cùng). */
function techSummary(t: Techniques): string {
  const on = [
    t.subtitles && "Phụ đề",
    t.dub && `Lồng tiếng${t.vieneu_voice ? ` (${t.vieneu_voice})` : ""}`,
    t.hook.trim() && "Hook",
    t.music_asset_id && "Nhạc nền",
    "Ghi nguồn",
  ].filter(Boolean);
  return on.join(" · ");
}

function ItemCard({ it, on, toggle }: { it: TikTokItem; on: boolean; toggle: () => void }) {
  const [broken, setBroken] = useState(false);
  return (
    <button
      type="button"
      onClick={toggle}
      className={cn(
        "flex flex-col overflow-hidden rounded-2xl border bg-white text-left shadow-sm",
        on ? "border-indigo-500 ring-2 ring-indigo-200" : "border-slate-200",
        it.taken && !on && "opacity-60"
      )}
    >
      <span className="relative block aspect-[9/16] max-h-72 bg-slate-900">
        {it.thumbnail && !broken ? (
          <img src={it.thumbnail} alt="" loading="lazy" referrerPolicy="no-referrer" className="size-full object-cover" onError={() => setBroken(true)} />
        ) : (
          <span className="flex size-full items-center justify-center text-slate-500">
            <Film className="size-8" />
          </span>
        )}
        <span
          className={cn(
            "absolute left-2 top-2 flex size-6 items-center justify-center rounded-md border-2",
            on ? "border-indigo-500 bg-indigo-500 text-white" : "border-white/80 bg-black/30"
          )}
        >
          {on ? <Check className="size-4" /> : null}
        </span>
        {it.taken ? (
          <span className="absolute right-2 top-2 rounded bg-emerald-600 px-1.5 py-0.5 text-[11px] font-semibold text-white">Đã lấy</span>
        ) : null}
        <span className="absolute inset-x-2 bottom-2 flex justify-between text-[11px] text-white">
          {it.views != null ? (
            <span className="inline-flex items-center gap-1 rounded bg-black/60 px-1.5 py-0.5">
              <Eye className="size-3" /> {views.format(it.views)}
            </span>
          ) : (
            <span />
          )}
          {it.duration ? (
            <span className="inline-flex items-center gap-1 rounded bg-black/60 px-1.5 py-0.5">
              <Clock className="size-3" /> {mmss(it.duration)}
            </span>
          ) : null}
        </span>
      </span>
      <span className="line-clamp-2 p-2 text-xs text-slate-700">{it.title || <i className="text-slate-400">Không có tiêu đề</i>}</span>
    </button>
  );
}

/**
 * PLAN-113 — dán link TikTok (kênh / 1 video) → quét (chỉ đọc danh sách) → tick chọn → kênh hoặc «Đăng tay», mẫu,
 * tuỳ chọn → «Tải & dựng». Video lấy về là video sưu tầm: ghi nguồn, không lật / LUT / biến thể (ADR-061 mục 11).
 */
export function StudioTiktokPage() {
  const setup = useSetup();
  const channels = setup.data?.channels ?? [];
  const templates = (setup.data?.templates ?? []).filter((t) => t.kind !== "ab_montage");
  const [url, setUrl] = useState("");
  const [limit, setLimit] = useState(10);
  const [items, setItems] = useState<TikTokItem[]>([]);
  const [picked, setPicked] = useState<Set<string>>(new Set());
  const [channel, setChannel] = useState<number | "" | "manual">("");
  const [templateId, setTemplateId] = useState<number | "">("");
  const [techniques, setTechniques] = useState<Techniques>(DEFAULT_TECHNIQUES);
  const [toast, setToast] = useState({ text: "", seq: 0 });
  const [tracked, setTracked] = useState<number[]>(loadTracked);
  const say = (text: string) => setToast((t) => ({ text, seq: t.seq + 1 }));

  const scan = useAction(
    () => api.scanTiktok(url.trim(), limit),
    (r) => {
      setItems(r.items);
      setPicked(new Set());
      return `Tìm thấy ${r.items.length} video.`;
    },
    []
  );
  const take = useAction(
    () =>
      api.takeTiktok({
        items: items.filter((i) => picked.has(i.url)).map((i) => ({ url: i.url, title: i.title })),
        channel_id: typeof channel === "number" ? channel : null,
        template_id: templateId === "" ? null : templateId,
        techniques,
      }),
    (r) => {
      setItems((xs) => xs.map((i) => (picked.has(i.url) ? { ...i, taken: true } : i)));
      setPicked(new Set());
      setTracked((t) => {
        const next = [...r.task_ids, ...t].slice(0, 100);
        saveTracked(next);
        return next;
      });
      return `Đã nhận ${r.count} video — tiến trình từng video hiện ngay bên dưới ô quét.`;
    },
    [["studio-projects"]]
  );
  // quét / gửi / nghe thử đều báo qua một Toast chung của trang
  useEffect(() => void (scan.msg && say(scan.msg)), [scan.seq]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => void (take.msg && say(take.msg)), [take.seq]); // eslint-disable-line react-hooks/exhaustive-deps

  const fresh = items.filter((i) => !i.taken);
  const toggle = (u: string) =>
    setPicked((s) => {
      const n = new Set(s);
      if (n.has(u)) n.delete(u);
      else n.add(u);
      return n;
    });

  return (
    <div className="mx-auto max-w-6xl sm:pb-40">
      <PageHeader title="Lấy từ TikTok" subtitle="Dán link kênh hoặc video → chọn video → Studio tải về và dựng" />
      <Panel className="mt-4 p-4">
        <form
          className="flex flex-wrap items-end gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            if (url.trim()) scan.run(undefined);
          }}
        >
          <label className="min-w-[16rem] flex-1 text-xs text-slate-500">
            Link TikTok
            <input
              className={`${inputClass} mt-1 w-full`}
              placeholder="https://www.tiktok.com/@ten_kenh  hoặc link 1 video"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
            />
          </label>
          <label className="text-xs text-slate-500">
            Số video
            <input
              type="number"
              min={1}
              max={30}
              className={`${inputClass} mt-1 block w-20`}
              value={limit}
              onChange={(e) => setLimit(Math.max(1, Math.min(30, Number(e.target.value) || 1)))}
            />
          </label>
          <button type="submit" className={`${primaryBtnClass} inline-flex h-9 items-center gap-1.5`} disabled={!url.trim() || scan.busy}>
            <Search className="size-4" /> {scan.busy ? "Đang quét…" : "Quét"}
          </button>
        </form>
        <p className="mt-2 text-xs text-slate-400">
          Chỉ đọc danh sách (mới nhất trước), chưa tải gì. Quét kênh mất khoảng 10–40 giây. Quét liên tục nhiều lần TikTok có thể chặn
          tạm.
        </p>
      </Panel>

      {tracked.length ? (
        <div>
          <JobsPanel ids={tracked} title="Video đã gửi dựng" />
          <button
            type="button"
            className="mt-1 text-xs text-slate-400 hover:text-slate-700"
            onClick={() => {
              setTracked([]);
              saveTracked([]);
            }}
          >
            Ẩn danh sách này
          </button>
        </div>
      ) : null}

      {items.length ? (
        <Panel className="mt-4 p-4">
          <h2 className="mb-2 text-sm font-semibold text-slate-700">Kỹ thuật cho video sẽ dựng (áp cho cả lô)</h2>
          <TechniquePicker value={techniques} onChange={setTechniques} collected />
        </Panel>
      ) : null}

      {items.length ? (
        <>
          <div className="mt-5 flex flex-wrap items-center gap-2 text-sm">
            <span className="text-slate-600">
              {items.length} video · đã chọn <b>{picked.size}</b>
            </span>
            <button type="button" className={ghostBtnClass} onClick={() => setPicked(new Set(fresh.map((i) => i.url)))} disabled={!fresh.length}>
              Chọn tất cả chưa lấy ({fresh.length})
            </button>
            <button type="button" className={ghostBtnClass} onClick={() => setPicked(new Set())} disabled={!picked.size}>
              Bỏ chọn
            </button>
          </div>
          <div className="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
            {items.map((it) => (
              <ItemCard key={it.url} it={it} on={picked.has(it.url)} toggle={() => toggle(it.url)} />
            ))}
          </div>
        </>
      ) : null}

      {items.length ? (
        // điện thoại: nằm sau lưới (cuộn tới); màn rộng: dính đáy để chọn tới đâu cũng bấm được
        <div className="mt-4 rounded-2xl border border-slate-200 bg-white px-4 py-3 sm:fixed sm:inset-x-0 sm:bottom-0 sm:z-40 sm:mt-0 sm:rounded-none sm:border-x-0 sm:border-b-0 sm:bg-white/95 sm:shadow-[0_-4px_12px_rgba(0,0,0,0.05)] sm:backdrop-blur lg:left-64">
          <div className="mx-auto flex max-w-6xl flex-col gap-2">
            <div className="flex flex-wrap items-end gap-2">
              <label className="text-xs text-slate-500">
                Đăng lên
                <select
                  className={`${selectClass} mt-1 block`}
                  value={channel}
                  onChange={(e) => setChannel(e.target.value === "manual" ? "manual" : e.target.value ? Number(e.target.value) : "")}
                >
                  <option value="">— chọn —</option>
                  <option value="manual">Đăng tay (không qua Buffer)</option>
                  {channels.map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.name}
                    </option>
                  ))}
                </select>
              </label>
              <label className="text-xs text-slate-500">
                Mẫu edit
                <select
                  className={`${selectClass} mt-1 block`}
                  value={templateId}
                  onChange={(e) => setTemplateId(e.target.value ? Number(e.target.value) : "")}
                >
                  <option value="">{typeof channel === "number" ? "Mẫu của kênh" : "basic"}</option>
                  {templates.map((t) => (
                    <option key={t.id} value={t.id}>
                      {t.name} ({t.kind})
                    </option>
                  ))}
                </select>
              </label>
              <div className="min-w-0 self-center text-xs text-slate-600">
                <span className="font-semibold text-slate-700">Kỹ thuật: </span>
                {techSummary(techniques)}
              </div>
              <button
                type="button"
                className={`${primaryBtnClass} ml-auto h-9`}
                disabled={!picked.size || channel === "" || take.busy}
                title={channel === "" ? "Chọn kênh hoặc «Đăng tay» trước" : undefined}
                onClick={() => take.run(undefined)}
              >
                {take.busy ? "Đang gửi…" : `Tải & dựng (${picked.size})`}
              </button>
            </div>
            <p className="text-xs text-slate-500">
              Video lấy từ TikTok là video sưu tầm: tự ghi nguồn <b>@kênh</b>; lật gương / đổi tông màu / biến thể chỉ cho video tự quay.
              {channel === "manual" ? " Đăng tay: duyệt xong tải video ở Studio → «Đã duyệt»." : ""}{" "}
              <Link to="/app/go/studio" className="underline">
                Mở Studio
              </Link>
            </p>
          </div>
        </div>
      ) : null}
      <Toast text={toast.text} seq={toast.seq} raised={items.length > 0} />
    </div>
  );
}
