import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: Number(process.env.PORT) || 5173,
    strictPort: false,
    // 後端埠可用 API_PORT 覆寫（8000 被佔用時免改設定檔）
    proxy: { "/api": `http://localhost:${process.env.API_PORT || 8000}` },
  },
});
