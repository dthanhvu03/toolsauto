export function ActionMsg({ text }: { text: string }) {
  if (!text) return null;
  const bad = /lỗi|vi phạm|không|fail|error/i.test(text);
  return (
    <p className={`mt-2 text-sm ${bad ? "text-red-700" : "text-emerald-700"}`}>{text}</p>
  );
}
