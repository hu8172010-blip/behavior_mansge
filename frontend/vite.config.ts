import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";

export default defineConfig({
  plugins: [vue()],
  server: {
    port: 5173,
    host: "0.0.0.0",
    proxy: {
      "/api": "http://localhost:8000",
      // 模型推理服务（远端 FastAPI）：/model/* → http://192.168.237.123:8000/*
      "/model": {
        target: "http://192.168.237.123:8000",
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/model/, ""),
      },
    },
  },
});
