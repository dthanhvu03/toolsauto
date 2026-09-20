import { useState } from "react";
import { inputClass, primaryBtnClass, selectClass } from "@/shared/ui/controls";
import type { AccountRow } from "@/features/accounts/types/accounts.types";

export function ManualJobForm({
  accounts,
  busy,
  onSubmit,
}: {
  accounts: AccountRow[];
  busy: boolean;
  onSubmit: (form: FormData) => void;
}) {
  const [accountId, setAccountId] = useState(accounts[0] ? String(accounts[0].id) : "");
  const [jobType, setJobType] = useState("POST");
  const [targetPage, setTargetPage] = useState("");
  const [caption, setCaption] = useState("");

  return (
    <form
      className="mt-4 grid gap-3 rounded-2xl border border-slate-200 bg-white p-4 sm:grid-cols-2"
      onSubmit={(e) => {
        e.preventDefault();
        const fd = new FormData(e.currentTarget);
        onSubmit(fd);
      }}
    >
      <div className="sm:col-span-2 text-sm font-semibold">Tạo job thủ công</div>
      <select
        name="account_id"
        className={selectClass}
        value={accountId}
        onChange={(e) => setAccountId(e.target.value)}
        required
      >
        {accounts.length === 0 ? <option value="">Chưa có tài khoản</option> : null}
        {accounts.map((a) => (
          <option key={a.id} value={a.id}>
            {a.name} ({a.platform})
          </option>
        ))}
      </select>
      <select
        name="job_type"
        className={selectClass}
        value={jobType}
        onChange={(e) => setJobType(e.target.value)}
      >
        <option value="POST">Reels / POST</option>
        <option value="FEED">Bài feed</option>
        <option value="STORY">Tin (Story)</option>
      </select>
      <input
        name="target_page"
        className={inputClass}
        placeholder="URL Page đích"
        value={targetPage}
        onChange={(e) => setTargetPage(e.target.value)}
      />
      <input name="media" type="file" className={inputClass} />
      <textarea
        name="caption"
        className="min-h-[4.5rem] rounded-lg border border-slate-200 px-3 py-2 text-sm sm:col-span-2"
        placeholder="Caption"
        value={caption}
        onChange={(e) => setCaption(e.target.value)}
      />
      <div className="sm:col-span-2">
        <button type="submit" className={primaryBtnClass} disabled={busy || !accountId}>
          Tạo job
        </button>
      </div>
    </form>
  );
}
