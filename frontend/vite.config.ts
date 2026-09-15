import path from "node:path";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

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
      "/api": { target: "http://127.0.0.1:8000", changeOrigin: true },
      "/app": { target: "http://127.0.0.1:8000", changeOrigin: true },
      "/affiliates": { target: "http://127.0.0.1:8000", changeOrigin: true },
      "/insights": { target: "http://127.0.0.1:8000", changeOrigin: true },
      "/threads": { target: "http://127.0.0.1:8000", changeOrigin: true },
      "/compliance": { target: "http://127.0.0.1:8000", changeOrigin: true },
      "/syspanel": { target: "http://127.0.0.1:8000", changeOrigin: true },
      "/database": { target: "http://127.0.0.1:8000", changeOrigin: true },
      "/platform-config": { target: "http://127.0.0.1:8000", changeOrigin: true },
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
