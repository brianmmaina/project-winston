import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig(({ mode }) => {
  const rootEnv = loadEnv(mode, "../", "");
  const apiKey = rootEnv.API_KEY || process.env.API_KEY || "";
  const backendTarget = process.env.VITE_PROXY_TARGET ?? "http://localhost:8000";

  return {
    plugins: [react()],
    server: {
      port: 5173,
      proxy: {
        "/api": {
          target: backendTarget,
          changeOrigin: true,
          timeout: 120000,
          proxyTimeout: 120000,
          ...(apiKey ? { headers: { Authorization: `Bearer ${apiKey}` } } : {}),
        },
      },
    },
  };
});
