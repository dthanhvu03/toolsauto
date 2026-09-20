import type { ReactNode } from "react";

export function QueryBody({
  isLoading,
  isError,
  loadingText,
  errorText,
  children,
}: {
  isLoading: boolean;
  isError: boolean;
  loadingText: string;
  errorText: string;
  children: ReactNode;
}) {
  if (isLoading) {
    return <p className="p-6 text-sm text-slate-500">{loadingText}</p>;
  }
  if (isError) {
    return <p className="p-6 text-sm text-red-600">{errorText}</p>;
  }
  return <>{children}</>;
}
