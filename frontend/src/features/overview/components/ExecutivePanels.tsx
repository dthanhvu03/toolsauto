import { useQuery } from "@tanstack/react-query";
import { getJson } from "@/shared/api/http";
import { Panel } from "@/shared/ui/Panel";

type Executive = {
  generated_at: string;
  errors: Record<string, string>;
  cashback: { orders: number; net_commission: number; customer_share: number; reserve: number; margin: number; period: string } | null;
  store: { orders: number; revenue: number; cost: number; profit: number; pending_orders: number; pending_topups: number; period: string } | null;
  studio: { projects: Record<string, number>; tasks: Record<string, number> } | null;
  threads: { counts: Record<string, number>; period: string } | null;
};

const money = (value: number) => `${value.toLocaleString("vi-VN")}đ`;

function Metrics({ rows }: { rows: [string, string | number][] }) {
  return <dl className="mt-3 grid grid-cols-2 gap-3 text-sm [overflow-wrap:anywhere]">
    {rows.map(([label, value]) => <div key={label}><dt className="text-xs text-slate-500">{label}</dt><dd className="mt-1 font-semibold tabular-nums text-slate-900">{value}</dd></div>)}
  </dl>;
}

export function ExecutivePanels() {
  const q = useQuery({ queryKey: ["admin-executive"], queryFn: () => getJson<Executive>("/api/admin/executive"), refetchInterval: 60_000 });
  const data = q.data;
  return <section aria-labelledby="executive-heading" className="mt-5">
    <h2 id="executive-heading" className="font-semibold text-slate-900">Kết quả kinh doanh & hàng việc</h2>
    <p className="mt-1 text-xs text-slate-500">Số tiền tách theo mô hình kinh doanh. Mỗi nguồn có kỳ và định nghĩa riêng.</p>
    {q.isError ? <p className="mt-2 text-sm text-amber-800">Chưa tải được số liệu kinh doanh. Các khối khác vẫn hoạt động.</p> : null}
    {q.isLoading ? <p className="mt-2 text-sm text-slate-500">Đang tổng hợp kết quả…</p> : null}
    {data ? <>
      <p className="mt-1 text-xs text-slate-400">Cập nhật {new Date(data.generated_at).toLocaleString("vi-VN", { timeZone: "Asia/Ho_Chi_Minh" })}</p>
      <div className="mt-3 grid gap-3 md:grid-cols-2">
        <Panel className="p-4"><a className="font-semibold text-indigo-700" href="/cashback">Cashback · kết quả 7 ngày →</a>
          {data.cashback ? <><Metrics rows={[["Đơn ghi nhận", data.cashback.orders], ["Hoa hồng ròng", money(data.cashback.net_commission)], ["Phần khách", money(data.cashback.customer_share)], ["Biên tạm tính", money(data.cashback.margin)]]} /><p className="mt-3 text-xs text-slate-500">{data.cashback.period}. Biên đã trừ phần khách và dự phòng, chưa trừ vận hành; chưa đồng nghĩa tiền sàn đã trả.</p></> : <p className="mt-2 text-sm text-amber-800">{data.errors.cashback || "Chưa có dữ liệu"}</p>}
        </Panel>
        <Panel className="p-4"><a className="font-semibold text-indigo-700" href="/app/go/bot-users">AI Pass Store · kết quả 7 ngày →</a>
          {data.store ? <><Metrics rows={[["Đơn giao", data.store.orders], ["Doanh thu sau hoàn", money(data.store.revenue)], ["Lãi sau vốn / chi phí đã nhập", money(data.store.profit)], ["Chờ xử lý", `${data.store.pending_orders} đơn · ${data.store.pending_topups} nạp`]]} /><p className="mt-3 text-xs text-slate-500">{data.store.period}. Chi phí hạ tầng chưa nhập không được tự tính.</p></> : <p className="mt-2 text-sm text-amber-800">{data.errors.store || "Chưa có dữ liệu"}</p>}
        </Panel>
        <Panel className="p-4"><a className="font-semibold text-indigo-700" href="/app/go/studio">Studio · sản xuất nội dung →</a>
          {data.studio ? <Metrics rows={[["Chờ duyệt", data.studio.projects.REVIEW ?? 0], ["Dự án lỗi", data.studio.projects.FAILED ?? 0], ["Việc chờ", data.studio.tasks.QUEUED ?? 0], ["Việc đang chạy", data.studio.tasks.RUNNING ?? 0]]} /> : <p className="mt-2 text-sm text-amber-800">{data.errors.studio || "Chưa có dữ liệu"}</p>}
        </Panel>
        <Panel className="p-4"><a className="font-semibold text-indigo-700" href="/app/go/threads-growth">Threads · kéo khách →</a>
          {data.threads ? <><Metrics rows={[["Chờ duyệt", data.threads.counts.pending ?? 0], ["Đã duyệt chờ đăng", data.threads.counts.approved ?? 0], ["Đã đăng", data.threads.counts.posted ?? 0], ["Lỗi", data.threads.counts.failed ?? 0]]} /><p className="mt-3 text-xs text-slate-500">{data.threads.period}</p></> : <p className="mt-2 text-sm text-amber-800">{data.errors.threads || "Chưa có dữ liệu"}</p>}
        </Panel>
      </div>
      <p className="mt-3 text-xs text-slate-500">Xe Tết: trạng thái vận hành game chưa nối vào bảng điều hành này.</p>
    </> : null}
  </section>;
}
