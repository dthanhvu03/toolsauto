export function FieldHelper({ text }: { text?: string }) {
  if (!text) return null;
  return <p className="mt-1 text-xs text-slate-500">{text}</p>;
}
