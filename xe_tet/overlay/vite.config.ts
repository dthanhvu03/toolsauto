import { defineConfig } from "vite";

// Dev: `npm run dev` (cổng 5173) chuyển /ws, /api sang server Python 8810.
// Live: `npm run build` → dist/, server Python phục vụ luôn ở http://127.0.0.1:8810/
export default defineConfig({
  base: "./",
  css: { postcss: { plugins: [] } }, // không lấy cấu hình Tailwind của toolsauto ở thư mục cha
  build: { chunkSizeWarningLimit: 800 },
  server: {
    proxy: {
      "/ws": { target: "ws://127.0.0.1:8810", ws: true },
      "/api": "http://127.0.0.1:8810",
      "/control": "http://127.0.0.1:8810",
    },
  },
});
