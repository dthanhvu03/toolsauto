import { useEffect, useState } from "react";
import { createPortal } from "react-dom";

/**
 * Thông báo nổi cố định góc dưới — thấy được dù đang cuộn tới đâu. Đổi ``seq`` là hiện lại (cùng một câu
 * bấm hai lần vẫn báo). Tự ẩn sau 6 giây; bấm để ẩn ngay. ``raised``: trang có thanh cố định ở đáy (màn ≥ sm) → nổi cao hơn.
 */
export function Toast({ text, seq, raised = false }: { text: string; seq: number; raised?: boolean }) {
  const [shown, setShown] = useState(false);
  useEffect(() => {
    if (!text) return;
    setShown(true);
    const t = window.setTimeout(() => setShown(false), 6000);
    return () => window.clearTimeout(t);
  }, [text, seq]);
  if (!text || !shown) return null;
  const bad = text.startsWith("Lỗi");
  return createPortal(
    <button
      type="button"
      onClick={() => setShown(false)}
      className={`fixed ${raised ? "bottom-4 sm:bottom-32" : "bottom-4"} left-1/2 z-[60] w-[min(92vw,32rem)] -translate-x-1/2 rounded-xl px-4 py-3 text-left text-sm font-medium shadow-lg ${
        bad ? "bg-red-600 text-white" : "bg-slate-900 text-white"
      }`}
    >
      {text}
    </button>,
    document.body
  );
}
