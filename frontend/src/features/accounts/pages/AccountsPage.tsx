import { PageHeader } from "@/shared/ui/PageHeader";
import { Panel } from "@/shared/ui/Panel";
import { QueryBody } from "@/shared/ui/QueryBody";
import { ActionMsg } from "@/shared/ui/ActionMsg";
import { inputClass, primaryBtnClass, selectClass } from "@/shared/ui/controls";
import { AccountsFilters } from "../components/AccountsFilters";
import { AccountsList } from "../components/AccountsList";
import { useAccountsController } from "../hooks/useAccountsController";
import { useState } from "react";

export function AccountsPage() {
  const ctl = useAccountsController();
  const [name, setName] = useState("");
  const [plat, setPlat] = useState("facebook");

  return (
    <div className="mx-auto max-w-5xl">
      <PageHeader
        title="Tài khoản"
        subtitle={ctl.query.data ? `${ctl.query.data.total} accounts` : "—"}
        classicHref="/app/accounts"
      />
      <ActionMsg text={ctl.msg} />
      <form
        className="mt-4 flex flex-wrap gap-2 rounded-2xl border border-slate-200 bg-white p-4"
        onSubmit={(e) => {
          e.preventDefault();
          if (!name.trim()) return;
          ctl.create(name.trim(), plat);
          setName("");
        }}
      >
        <input
          className={inputClass}
          placeholder="Tên tài khoản"
          value={name}
          onChange={(e) => setName(e.target.value)}
        />
        <select className={selectClass} value={plat} onChange={(e) => setPlat(e.target.value)}>
          <option value="facebook">facebook</option>
          <option value="instagram">instagram</option>
          <option value="threads">threads</option>
          <option value="tiktok">tiktok</option>
        </select>
        <button type="submit" className={primaryBtnClass} disabled={ctl.creating}>
          Thêm
        </button>
        <p className="w-full text-xs text-slate-400">Cookie / đăng nhập browser vẫn ở Classic.</p>
      </form>

      <AccountsFilters
        platform={ctl.platform}
        qDraft={ctl.qDraft}
        onPlatformChange={ctl.setPlatform}
        onDraftChange={ctl.setQDraft}
        onSearch={ctl.applySearch}
      />

      <Panel className="mt-4">
        <QueryBody
          isLoading={ctl.query.isLoading}
          isError={ctl.query.isError}
          loadingText="Đang tải…"
          errorText="Lỗi tải accounts"
        >
          <AccountsList
            rows={ctl.rows}
            busyId={ctl.busyId}
            onToggle={ctl.toggle}
            onRename={ctl.rename}
            onDelete={ctl.remove}
          />
        </QueryBody>
      </Panel>
    </div>
  );
}
