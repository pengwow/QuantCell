import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Tauri 期望前端固定在 1420；tauri dev/build 在 desktop/ui 目录执行 hook
export default defineConfig({
  plugins: [react()],
  clearScreen: false,
  server: {
    port: 1420,
    strictPort: true,
  },
});
