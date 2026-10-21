import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5180,
    // Same origin as the API in dev, so the refresh cookie just works.
    proxy: { "/api": "http://localhost:8000" },
  },
});
