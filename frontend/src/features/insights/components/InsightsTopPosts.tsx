import type { TopPost } from "../types/insights.types";
import { formatK } from "../lib/formatK";

export function InsightsTopPosts({ posts }: { posts: TopPost[] }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[640px] text-left text-sm">
        <thead className="border-b border-slate-100 bg-slate-50 text-xs uppercase text-slate-500">
          <tr>
            <th className="px-3 py-2">Page</th>
            <th className="px-3 py-2">Caption</th>
            <th className="px-3 py-2">Views</th>
            <th className="px-3 py-2">ER</th>
            <th className="px-3 py-2">Link</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100">
          {posts.length === 0 ? (
            <tr>
              <td colSpan={5} className="px-3 py-8 text-center text-slate-400">
                Không có bài trong khoảng này
              </td>
            </tr>
          ) : (
            posts.map((p, i) => (
              <tr key={`${p.post_url}-${i}`} className="hover:bg-slate-50/80">
                <td className="px-3 py-2 text-xs font-medium">{p.page_name || p.platform || "—"}</td>
                <td className="max-w-[16rem] truncate px-3 py-2 text-xs text-slate-600">
                  {p.caption || "—"}
                </td>
                <td className="px-3 py-2 tabular-nums text-xs">{formatK(p.views)}</td>
                <td className="px-3 py-2 tabular-nums text-xs">{p.engagement_rate ?? 0}%</td>
                <td className="px-3 py-2 text-xs">
                  <a
                    href={p.post_url}
                    target="_blank"
                    rel="noreferrer"
                    className="text-indigo-600 hover:underline"
                  >
                    Mở
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
