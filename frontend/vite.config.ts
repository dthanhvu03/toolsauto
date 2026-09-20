import type { IncomingMessage } from "node:http";
import path from "node:path";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const API = "http://127.0.0.1:8000";

const toApi = {
  target: API,
  changeOrigin: true,
};

/** React Router paths — serve Vite HTML instead of FastAPI (which 401/redirects). */
function spaAppBypass(req: IncomingMessage) {
  if (req.method !== "GET" && req.method !== "HEAD") return;
  const accept = req.headers.accept ?? "";
  if (!accept.includes("text/html")) return;
  const pathname = (req.url ?? "").split("?")[0];
  const isSpa =
    pathname === "/app" ||
    pathname === "/app/" ||
    pathname === "/app/settings" ||
    pathname.startsWith("/app/go/");
  if (isSpa) return "/static/admin/";
}

function staticExceptAdminBypass(req: IncomingMessage) {
  if ((req.url ?? "").startsWith("/static/admin")) return req.url;
}

export default defineConfig({
  plugins: [react()],
  base: "/static/admin/",
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "src"),
    },
  },
  server: {
    port: 5173,
    proxy: {
      "/login": toApi,
      "/logout": toApi,
      "/api": toApi,
      "/viral": toApi,
      "/health": toApi,
      "/app": { ...toApi, bypass: spaAppBypass },
      "/static": { ...toApi, bypass: staticExceptAdminBypass },
      "/affiliates": toApi,
      "/insights": toApi,
      "/threads": toApi,
      "/compliance": toApi,
      "/syspanel": toApi,
      "/database": toApi,
      "/platform-config": toApi,
    },
  },
  build: {
    outDir: path.resolve(__dirname, "../app/static/admin"),
    emptyOutDir: true,
    manifest: true,
    rollupOptions: {
      output: {
        entryFileNames: "assets/index.js",
        chunkFileNames: "assets/[name].js",
        assetFileNames: "assets/[name][extname]",
      },
    },
  },
});
