import { useMemo, useState } from "react";
import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  addKeyword,
  deleteKeyword,
  fetchAnalytics,
  fetchCategories,
  fetchKeywords,
  testCheck,
  toggleKeyword,
} from "../api/complianceApi";

export function useComplianceController() {
  const [searchDraft, setSearchDraft] = useState("");
  const [search, setSearch] = useState("");
  const [severity, setSeverity] = useState("");
  const [category, setCategory] = useState("");
  const [kwPage, setKwPage] = useState(1);
  const [testText, setTestText] = useState("");
  const [testResult, setTestResult] = useState("");
  const [msg, setMsg] = useState("");
  const qc = useQueryClient();

  const analytics = useQuery({
    queryKey: ["compliance-analytics"],
    queryFn: () => fetchAnalytics(30),
  });
  const categories = useQuery({
    queryKey: ["compliance-categories"],
    queryFn: fetchCategories,
  });
  const keywords = useQuery({
    queryKey: ["compliance-keywords", search, severity, category],
    queryFn: () => fetchKeywords({ search, severity, category }),
    placeholderData: keepPreviousData,
  });
  const kwPageSize = 20;
  const kwRows = keywords.data ?? [];
  const kwTotalPages = Math.max(1, Math.ceil(kwRows.length / kwPageSize));
  const kwSlice = useMemo(
    () => kwRows.slice((kwPage - 1) * kwPageSize, kwPage * kwPageSize),
    [kwRows, kwPage]
  );

  const applySearch = () => {
    setKwPage(1);
    setSearch(searchDraft.trim());
  };
  const changeSeverity = (value: string) => {
    setKwPage(1);
    setSeverity(value);
  };
  const changeCategory = (value: string) => {
    setKwPage(1);
    setCategory(value);
  };
  const invalidateKw = () => {
    qc.invalidateQueries({ queryKey: ["compliance-keywords"] });
    qc.invalidateQueries({ queryKey: ["compliance-analytics"] });
  };
  const addMut = useMutation({
    mutationFn: addKeyword,
    onSuccess: () => {
      setMsg("Đã thêm từ khóa");
      invalidateKw();
    },
    onError: (e: Error) => setMsg(e.message),
  });
  const toggleMut = useMutation({
    mutationFn: toggleKeyword,
    onSuccess: invalidateKw,
    onError: (e: Error) => setMsg(e.message),
  });
  const delMut = useMutation({
    mutationFn: deleteKeyword,
    onSuccess: invalidateKw,
    onError: (e: Error) => setMsg(e.message),
  });
  const testMut = useMutation({
    mutationFn: testCheck,
    onSuccess: (r) => setTestResult(JSON.stringify(r, null, 2)),
    onError: (e: Error) => setTestResult(e.message),
  });

  return {
    searchDraft,
    setSearchDraft,
    applySearch,
    severity,
    category,
    changeSeverity,
    changeCategory,
    kwPage,
    setKwPage,
    kwTotalPages,
    kwSlice,
    kwTotal: kwRows.length,
    keywords,
    categories: categories.data ?? [],
    analytics,
    msg,
    testText,
    setTestText,
    testResult,
    addKeyword: (keyword: string, severity: string) => addMut.mutate({ keyword, severity }),
    toggleKeyword: (id: number) => toggleMut.mutate(id),
    deleteKeyword: (id: number) => delMut.mutate(id),
    runTest: () => testMut.mutate(testText),
  };
}
