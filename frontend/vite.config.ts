import path from "node:path";
import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  build: {
    rollupOptions: {
      // 双 MPA 入口:公开壳(index)+ 独立管理文档(admin)
      input: { main: "index.html", admin: "admin.html" },
    },
  },
  server: {
    proxy: {
      "/api": "http://localhost:8000",
    },
  },
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
    // mjs 腿:#304-⑦ 本地 eslint 规则的单测是 .mjs(eslint/规则本体均无仓内类型)
    include: ["src/**/*.test.{ts,tsx,mjs}"],
  },
});
