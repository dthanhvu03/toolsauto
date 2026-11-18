import { useEffect, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { getJson } from "@/shared/api/http";
import { cn } from "@/shared/lib/cn";
import { Panel } from "@/shared/ui/Panel";

type TrendPoint = { day: string; label?: string } & Record<string, number | string | undefined>;
type Product = { name: string; sold: number; revenue: number; gross_profit: number };
type Executive = {
  generated_at: string;
  errors: Record<string, string>;
  cashback: {
    orders: number; net_commission: number; customer_share: number; reserve: number; margin: number; period: string;
    trend: TrendPoint[];
    money_position: {
      settled_owner_received: number | null; upcoming_owner: number | null; customer_waiting: number; customer_wallet: number;
      payout_reserved: number; payout_paid: number; fund_available: number | null; fund_verified: boolean; open_adjustments: number;
      settled_owner_received_known?: boolean; upcoming_owner_known?: boolean;
    };
  } | null;
  store: {
    orders: number; revenue: number; cost: number; profit: number; gross_profit?: number; external_expense?: number;
    pending_orders: number; pending_topups: number; period: string; cost_note?: string;
    trend: TrendPoint[]; top_sellers: Product[]; top_profit: Product[];
    money_position: { customer_wallet: number; capital_recorded: number; capital_used: number; waiting_order_cost: number };
  } | null;
  studio: { projects: Record<string, number>; tasks: Record<string, number> } | null;
  threads: { counts: Record<string, number>; period: string } | null;
};

type Series = { key: string; label: string; color: string };
const STORE_SERIES: Series[] = [
  { key: "revenue", label: "Doanh thu sau hoàn", color: "#0f766e" },
  { key: "net_profit", label: "Lãi sau chi phí đã ghi", color: "#c2410c" },
];
const CASHBACK_SERIES: Series[] = [
  { key: "net_commission", label: "Hoa hồng ròng", color: "#0f766e" },
  { key: "margin", label: "Biên tạm tính", color: "#c2410c" },
];
const money = (value: number | null | undefined) => value == null ? "Chưa xác định" : value.toLocaleString("vi-VN") + "đ";
const compactMoney = (value: number) => new Intl.NumberFormat("vi-VN", { notation: "compact", maximumFractionDigits: 1 }).format(Math.round(value));
const dateLabel = (value: string) => {
  const match = /^(\d{4})[-/](\d{2})[-/](\d{2})/.exec(value);
  return match ? match[3] + "/" + match[2] : value;
};
const intervalLabel = (point: TrendPoint) => (point.label ?? point.day).split(" – ").map(dateLabel).join(" – ");

/** Measured pixel coordinates keep chart text and touch controls readable at every width. */
function TrendChart({ title, points, series }: { title: string; points: TrendPoint[]; series: Series[] }) {
  const container = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(300);
  const [selectedDay, setSelectedDay] = useState<string | null>(null);
  useEffect(() => {
    const node = container.current;
    if (!node) return;
    const observer = new ResizeObserver(([entry]) => setWidth(Math.max(200, entry.contentRect.width)));
    observer.observe(node);
    return () => observer.disconnect();
  }, []);
  const height = 216;
  const pad = { top: 16, right: 12, bottom: 30, left: 52 };
  const values = points.flatMap(point => series.map(item => Number(point[item.key] ?? 0)));
  const minimum = Math.min(0, ...values);
  const maximum = Math.max(0, ...values);
  const low = minimum === maximum ? 0 : minimum;
  const high = minimum === maximum ? 1 : maximum;
  const span = high - low;
  const x = (index: number) => pad.left + (points.length < 2 ? (width - pad.left - pad.right) / 2 : index * (width - pad.left - pad.right) / (points.length - 1));
  const y = (value: number) => height - pad.bottom - (value - low) / span * (height - pad.top - pad.bottom);
  const requestedIndex = points.findIndex(point => point.day === selectedDay);
  const selectedIndex = requestedIndex >= 0 ? requestedIndex : points.length - 1;
  const selected = points[selectedIndex];
  const labelStep = Math.max(1, Math.ceil(points.length / (width < 400 ? 3 : 7)));
  return <Panel className="min-w-0 p-4">
    <h3 className="text-sm font-semibold text-slate-900">{title}</h3>
    <p className="mt-1 text-xs text-slate-500">Đơn vị: đồng · chạm biểu đồ hoặc chọn mốc để xem số tiền.</p>
    <div className="mt-3 flex flex-wrap gap-x-4 gap-y-2 text-xs text-slate-600">
      {series.map(item => <span key={item.key} className="inline-flex items-center gap-1.5"><span className="h-2 w-2 rounded-full" style={{ background: item.color }} />{item.label}</span>)}
    </div>
    <div ref={container} className="mt-2 min-w-0" data-chart={title}>
      {points.length ? <>
        <svg width="100%" height={height} viewBox={"0 0 " + width + " " + height} aria-hidden="true" className="block touch-pan-y"
          onPointerDown={event => {
            const rect = event.currentTarget.getBoundingClientRect();
            const index = Math.round((event.clientX - rect.left - pad.left) / Math.max(1, width - pad.left - pad.right) * (points.length - 1));
            setSelectedDay(points[Math.max(0, Math.min(points.length - 1, index))].day);
          }}>
          {[0, 1, 2, 3].map(tick => {
            const value = high - tick * span / 3;
            return <g key={tick}><line x1={pad.left} x2={width - pad.right} y1={y(value)} y2={y(value)} stroke="#e2e8f0" />
              <text x={pad.left - 7} y={y(value) + 3} textAnchor="end" fontSize="10" fill="#64748b">{compactMoney(value)}</text></g>;
          })}
          <line x1={pad.left} x2={width - pad.right} y1={y(0)} y2={y(0)} stroke="#94a3b8" strokeDasharray="3 3" />
          {selected ? <line x1={x(selectedIndex)} x2={x(selectedIndex)} y1={pad.top} y2={height - pad.bottom} stroke="#cbd5e1" strokeDasharray="2 4" /> : null}
          {series.map(item => <g key={item.key}>
            <path d={points.map((point, index) => (index ? "L" : "M") + x(index) + "," + y(Number(point[item.key] ?? 0))).join(" ")} fill="none" stroke={item.color} strokeWidth="2" strokeLinejoin="round" />
            {points.map((point, index) => <circle key={point.day} cx={x(index)} cy={y(Number(point[item.key] ?? 0))} r={index === selectedIndex ? 4 : 2.5} fill={item.color} />)}
          </g>)}
          {points.map((point, index) => index === 0 || index === points.length - 1 || (index % labelStep === 0 && index < points.length - 2) ?
            <text key={point.day} x={x(index)} y={height - 8} textAnchor={index === 0 ? "start" : index === points.length - 1 ? "end" : "middle"} fontSize="10" fill="#64748b">{dateLabel(point.day)}</text> : null)}
        </svg>
        <label className="flex flex-wrap items-center gap-2 text-xs text-slate-600">
          <span>Mốc hiển thị</span>
          <select aria-label={"Mốc " + title} className="min-h-11 max-w-full rounded-lg border border-slate-200 bg-white px-3 text-base sm:text-sm" value={selected?.day ?? ""} onChange={event => setSelectedDay(event.target.value)}>
            {points.map(point => <option key={point.day} value={point.day}>{intervalLabel(point)}</option>)}
          </select>
        </label>
        {selected ? <dl className="mt-3 grid grid-cols-2 gap-3 rounded-xl bg-slate-50 p-3 text-sm" aria-live="polite">
          {series.map(item => <div key={item.key} className="min-w-0"><dt className="text-xs text-slate-600">{item.label}</dt><dd className="mt-1 break-words font-semibold tabular-nums" style={{ color: item.color }}>{money(Number(selected[item.key] ?? 0))}</dd></div>)}
        </dl> : null}
        {values.every(value => value === 0) ? <p className="mt-2 text-xs text-slate-500">Chưa ghi nhận giá trị trong kỳ này.</p> : null}
      </> : <p className="py-6 text-sm text-slate-500">Chưa có dữ liệu trong kỳ.</p>}
    </div>
  </Panel>;
}

function ProductList({ title, items }: { title: string; items: Product[] }) {
  return <Panel className="min-w-0 p-4">
    <h3 className="text-sm font-semibold text-slate-900">{title}</h3>
    {items.length ? <ol className="mt-2 divide-y divide-slate-100">
      {items.map((item, index) => <li key={item.name + index} className="py-3">
        <div className="flex items-start gap-2 text-sm"><span className="shrink-0 text-slate-400">{index + 1}.</span><span className="min-w-0 break-words font-medium text-slate-800 [overflow-wrap:anywhere]">{item.name}</span></div>
        <dl className="mt-2 grid grid-cols-3 gap-2 pl-5 text-xs">
          <div><dt className="text-slate-500">Đã giao</dt><dd className="mt-1 font-medium tabular-nums">{item.sold.toLocaleString("vi-VN")} món</dd></div>
          <div className="min-w-0"><dt className="text-slate-500">Doanh thu</dt><dd className="mt-1 break-words font-medium tabular-nums">{money(item.revenue)}</dd></div>
          <div className="min-w-0"><dt className="text-slate-500">Lãi gộp</dt><dd className={cn("mt-1 break-words font-medium tabular-nums", item.gross_profit < 0 ? "text-red-700" : "text-teal-800")}>{money(item.gross_profit)}</dd></div>
        </dl>
      </li>)}
    </ol> : <p className="mt-3 text-sm text-slate-500">Chưa có món đã giao trong kỳ.</p>}
  </Panel>;
}

function Metrics({ rows }: { rows: [string, string | number][] }) {
  return <dl className="mt-3 grid grid-cols-2 gap-x-4 gap-y-4 text-sm [overflow-wrap:anywhere]">
    {rows.map(([label, value]) => <div key={label} className="min-w-0"><dt className="text-xs text-slate-500">{label}</dt><dd className="mt-1 font-semibold tabular-nums text-slate-900">{value}</dd></div>)}
  </dl>;
}

export function ExecutivePanels() {
  const [days, setDays] = useState<7 | 30>(7);
  const q = useQuery({ queryKey: ["admin-executive", days], queryFn: () => getJson<Executive>("/api/admin/executive?days=" + days), refetchInterval: 60_000 });
  const data = q.data;
  const store = data?.store;
  const cashback = data?.cashback;
  return <section aria-labelledby="executive-heading" className="mt-5">
    <div className="flex flex-wrap items-center justify-between gap-3">
      <div><h2 id="executive-heading" className="font-semibold text-slate-900">Kết quả kinh doanh & hàng việc</h2>
        <p className="mt-1 text-xs text-slate-500">Theo dõi bán hàng, lợi nhuận đã ghi và tiền cần xử lý.</p></div>
      <div className="inline-flex rounded-xl border border-slate-200 bg-white p-1" role="group" aria-label="Kỳ báo cáo">
        {([7, 30] as const).map(value => <button key={value} type="button" aria-pressed={days === value} onClick={() => setDays(value)} className={cn("min-h-11 rounded-lg px-4 text-sm font-medium", days === value ? "bg-slate-900 text-white" : "text-slate-600 hover:bg-slate-100")}>{value} ngày</button>)}
      </div>
    </div>
    {q.isError ? <p className="mt-3 text-sm text-amber-800" role="alert">Chưa tải được số liệu kinh doanh. Vui lòng thử lại.</p> : null}
    {q.isLoading ? <p className="mt-3 text-sm text-slate-500" role="status">Đang tổng hợp kết quả…</p> : null}
    {data ? <>
      <p className="mt-2 text-xs text-slate-400">Cập nhật {new Date(data.generated_at).toLocaleString("vi-VN", { timeZone: "Asia/Ho_Chi_Minh" })}</p>
      <div className="mt-4 space-y-5">
        <section aria-label="Kinh doanh AI Pass Store" className="space-y-3">
          <Panel className="p-4">
            <div className="flex flex-wrap items-center justify-between gap-2"><h3 className="font-semibold text-slate-900">AI Pass Store · {days} ngày</h3><a className="text-sm text-indigo-700" href="/app/go/bot-users">Xem khách →</a></div>
            {store ? <><Metrics rows={[["Đơn đã giao", store.orders], ["Doanh thu sau hoàn", money(store.revenue)], ["Giá vốn đã ghi", money(store.cost)], ["Chi ngoài đã ghi", money(store.external_expense)], ["Lãi sau vốn và chi phí đã ghi", money(store.profit)], ["Đang chờ xử lý", store.pending_orders + " đơn · " + store.pending_topups + " nạp"]]} />
              <p className="mt-3 text-xs leading-relaxed text-slate-500">{store.period}. {store.cost_note ?? "Giá vốn chưa ghi đang tính 0đ; chi phí chưa nhập chưa được trừ."}</p></> : <p className="mt-3 text-sm text-amber-800">{data.errors.store || "Chưa có dữ liệu Store"}</p>}
          </Panel>
          {store?.trend && store.money_position ? <>
            <TrendChart key={"store-" + days} title={"Doanh thu và lãi theo " + (days === 7 ? "ngày" : "tuần")} points={store.trend} series={STORE_SERIES} />
            <div className="grid gap-3 md:grid-cols-2"><ProductList title="Top 5 món bán nhiều" items={store.top_sellers} /><ProductList title="Top 5 món lãi gộp cao" items={store.top_profit} /></div>
            <p className="text-xs text-slate-500">Lãi gộp theo món = doanh thu sau hoàn − vốn đã ghi. Chi ngoài chưa phân bổ theo món.</p>
            <Panel className="p-4"><h3 className="text-sm font-semibold text-slate-900">Tiền Store hiện tại</h3>
              <Metrics rows={[["Tiền khách còn trong ví", money(store.money_position.customer_wallet)], ["Vốn cần cho đơn chờ nhập", money(store.money_position.waiting_order_cost)], ["Sổ vốn FatCat từ đầu", money(store.money_position.capital_recorded)], ["Giá vốn đã dùng từ đầu", money(store.money_position.capital_used)]]} />
              <p className="mt-3 text-xs leading-relaxed text-slate-500">Không theo bộ lọc ngày. Tiền trong ví thuộc khách. Sổ vốn gồm khoản nạp/rút/điều chỉnh đã ghi; vốn đã dùng gồm cả đơn admin. Đây không phải số dư ngân hàng hay số dư FatCat thực tế.</p>
            </Panel>
          </> : store ? <p className="text-sm text-amber-800">Dữ liệu biểu đồ chưa khả dụng.</p> : null}
        </section>
        <section aria-label="Kinh doanh Cashback" className="space-y-3">
          <Panel className="p-4">
            <div className="flex flex-wrap items-center justify-between gap-2"><h3 className="font-semibold text-slate-900">Cashback · {days} ngày</h3><a className="text-sm text-indigo-700" href="/cashback">Chi tiết →</a></div>
            {cashback ? <><Metrics rows={[["Đơn ghi nhận", cashback.orders], ["Hoa hồng ròng", money(cashback.net_commission)], ["Phần khách", money(cashback.customer_share)], ["Biên tạm tính", money(cashback.margin)]]} />
              <p className="mt-3 text-xs leading-relaxed text-slate-500">{cashback.period}. Biên đã trừ phần khách và dự phòng, chưa trừ vận hành; chưa phải tiền sàn đã trả.</p></> : <p className="mt-3 text-sm text-amber-800">{data.errors.cashback || "Chưa có dữ liệu Cashback"}</p>}
          </Panel>
          {cashback?.trend && cashback.money_position ? <>
            <TrendChart key={"cashback-" + days} title={"Hoa hồng và biên tạm tính theo " + (days === 7 ? "ngày" : "tuần")} points={cashback.trend} series={CASHBACK_SERIES} />
            <Panel className="p-4"><h3 className="text-sm font-semibold text-slate-900">Tiền Cashback hiện tại</h3>
              <Metrics rows={[["Phần anh từ các kỳ đã khớp", cashback.money_position.settled_owner_received_known === false ? "Chưa xác minh" : money(cashback.money_position.settled_owner_received)], ["Phần anh ở các kỳ sắp về", cashback.money_position.upcoming_owner_known === false ? "Chưa xác minh" : money(cashback.money_position.upcoming_owner)], ["Khách chờ Shopee / đủ ngày giữ", money(cashback.money_position.customer_waiting)], ["Trong ví khách, rút được", money(cashback.money_position.customer_wallet)], ["Đang chờ chuyển khách", money(cashback.money_position.payout_reserved)], ["Đã chuyển khách từ đầu", money(cashback.money_position.payout_paid)], ["Quỹ chi trả còn", cashback.money_position.fund_verified ? money(cashback.money_position.fund_available) : "Chưa xác minh"]]} />
              {cashback.money_position.open_adjustments ? <p className="mt-3 text-sm text-amber-800">Có {cashback.money_position.open_adjustments} điều chỉnh đang mở cần kiểm tra.</p> : null}
              <p className="mt-3 text-xs leading-relaxed text-slate-500">Theo các kỳ đối soát và số dư hiện hành, không theo bộ lọc ngày. Phần anh đã khớp là số lũy kế sau phần khách, chưa phải tiền mặt còn để rút.</p>
            </Panel>
          </> : cashback ? <p className="text-sm text-amber-800">Dữ liệu biểu đồ chưa khả dụng.</p> : null}
        </section>
        <div className="grid gap-3 md:grid-cols-2">
          <Panel className="p-4"><a className="font-semibold text-indigo-700" href="/app/go/studio">Studio · sản xuất nội dung →</a>{data.studio ? <Metrics rows={[["Chờ duyệt", data.studio.projects.REVIEW ?? 0], ["Dự án lỗi", data.studio.projects.FAILED ?? 0], ["Việc chờ", data.studio.tasks.QUEUED ?? 0], ["Việc đang chạy", data.studio.tasks.RUNNING ?? 0]]} /> : <p className="mt-2 text-sm text-amber-800">{data.errors.studio || "Chưa có dữ liệu"}</p>}</Panel>
          <Panel className="p-4"><a className="font-semibold text-indigo-700" href="/app/go/threads-growth">Threads · kéo khách →</a>{data.threads ? <><Metrics rows={[["Chờ duyệt", data.threads.counts.pending ?? 0], ["Chờ đăng", data.threads.counts.approved ?? 0], ["Đã đăng", data.threads.counts.posted ?? 0], ["Lỗi", data.threads.counts.failed ?? 0]]} /><p className="mt-3 text-xs text-slate-500">{data.threads.period}</p></> : <p className="mt-2 text-sm text-amber-800">{data.errors.threads || "Chưa có dữ liệu"}</p>}</Panel>
        </div>
        <p className="text-xs text-slate-500">Xe Tết: chỉ số vận hành chưa nối vào bảng này.</p>
      </div>
    </> : null}
  </section>;
}
