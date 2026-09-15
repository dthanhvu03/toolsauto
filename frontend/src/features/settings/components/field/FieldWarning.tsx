export function FieldWarning({ message }: { message?: string }) {
  if (!message) return null;
  return <p className="mt-1 text-xs font-medium text-amber-700">{message}</p>;
}
