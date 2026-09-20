import { useMemo, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { fetchDatabase, fetchTable, runSql } from "../api/databaseApi";

export function useDatabaseController() {
  const [qDraft, setQDraft] = useState("");
  const [q, setQ] = useState("");
  const [table, setTable] = useState("");
  const [sql, setSql] = useState("SELECT 1");
  const [confirmed, setConfirmed] = useState(false);
  const query = useQuery({ queryKey: ["admin-database"], queryFn: fetchDatabase });
  const preview = useQuery({
    queryKey: ["admin-database-table", table],
    queryFn: () => fetchTable(table),
    enabled: Boolean(table),
  });
  const sqlMut = useMutation({
    mutationFn: () => runSql(sql, confirmed),
  });

  const tables = useMemo(() => {
    const all = query.data?.tables ?? [];
    const n = q.trim().toLowerCase();
    if (!n) return all;
    return all.filter((t) => t.name.toLowerCase().includes(n));
  }, [query.data, q]);

  return {
    query,
    tables,
    qDraft,
    setQDraft,
    applySearch: () => setQ(qDraft.trim()),
    total: query.data?.total ?? 0,
    table,
    setTable,
    preview,
    sql,
    setSql,
    confirmed,
    setConfirmed,
    sqlMut,
    run: () => sqlMut.mutate(),
  };
}
