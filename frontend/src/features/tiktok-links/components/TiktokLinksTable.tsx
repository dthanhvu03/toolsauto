import type { TiktokLinkRow } from "../types/tiktokLinks.types";

export function TiktokLinksTable({ items }: { items: TiktokLinkRow[] }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[640px] text-left text-sm">
        <thead className="border-b border-slate-100 bg-slate-50 text-xs uppercase text-slate-500">
          <tr>
            <th className="px-3 py-2">Tài khoản</th>
            <th className="px-3 py-2">Page đích</th>
            <th className="px-3 py-2">Kênh TikTok</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100">
          {items.length === 0 ? (
            <tr>
              <td colSpan={3} className="px-3 py-8 text-center text-slate-400">
                Không có kênh cũ
              </td>
            </tr>
          ) : (
            items.map((it, i) => (
              <tr key={`${it.account_name}-${it.url}-${i}`} className="hover:bg-slate-50/80">
                <td className="px-3 py-2">{it.account_name}</td>
                <td className="max-w-[14rem] truncate px-3 py-2 text-xs text-slate-500">
                  {it.target_name || it.target_page || "—"}
                </td>
                <td className="max-w-[18rem] truncate px-3 py-2 text-xs">
                  <a
                    href={it.url}
                    target="_blank"
                    rel="noreferrer"
                    className="text-indigo-600 hover:underline"
                  >
                    {it.url}
                  </a>
                </td>
              </tr>
            ))
          )}
        </tbody>
      </table>
    </div>
  );
}
