import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// RoadTwin Phase 1 Walking Skeleton dev server.
// The /api proxy lets the browser page use same-origin relative URLs
// (e.g. fetch('/api/skeleton/reports')) instead of hardcoding the
// backend's host/port, while the backend keeps its own CORS allowlist
// as a defense-in-depth fallback (backend/main.py).
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true,
      },
    },
  },
});
