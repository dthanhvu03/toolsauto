export const BOT_LABEL: Record<string, string> = { cashbot: "Cashbot", ai_store: "AI Pass Store" };
export const BOT_HINT: Record<string, string> = {
  cashbot: "Hoàn tiền Shopee — @zt_shopee_bot",
  ai_store: "Bán tài khoản AI / Canva / CapCut — @aipass_shop_bot",
};

export function when(iso: string | null | undefined) {
  if (!iso) return "";
  return new Date(iso).toLocaleString("vi-VN", { hour: "2-digit", minute: "2-digit", day: "2-digit", month: "2-digit" });
}

export const fmtNum = (n: number) =>
  n >= 1_000_000 ? `${(n / 1_000_000).toFixed(1)}tr` : n >= 1000 ? `${(n / 1000).toFixed(1)}k` : `${n}`;

export const pct = (part: number, whole: number) => (whole ? `${Math.round((part / whole) * 100)}%` : "—");

export type AiRead = { model: string; tags: { label?: string; text: string }[]; raw: string };

/** «AI [A] - model | Đọc: ý định · cảm xúc · cần: … · giai đoạn · băn khoăn: … · điểm 70» → nhãn. */
export function parseAiRead(raw: string | null): AiRead | null {
  if (!raw) return null;
  const [head, body] = raw.split(" | ", 2);
  if (!body || !body.startsWith("Đọc:")) return { model: "", tags: [], raw };
  const tags = body
    .slice(4)
    .split(" · ")
    .map((s) => s.trim())
    .filter((s) => s && !/^điểm \d+$/.test(s))
    .map((s) => {
      const m = s.match(/^(cần|băn khoăn|chữ của họ|góc nói):\s*(.+)$/);
      return m ? { label: m[1], text: m[2] } : { text: s };
    });
  return { model: head.replace(/^AI \[[AB]\] - /, ""), tags, raw };
}

export function scoreTone(score: number) {
  if (score >= 80) return "bg-emerald-100 text-emerald-800";
  if (score >= 60) return "bg-indigo-100 text-indigo-800";
  return "bg-slate-100 text-slate-600";
}
