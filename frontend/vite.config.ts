/// <reference types="vitest/config" />
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// React는 Spring Boot만 호출한다. 개발 서버는 /api 요청을 Spring으로 넘겨(proxy) 브라우저 입장에서 같은 origin이 되게 한다.
// 그래서 CORS 설정이 필요 없고, Refresh Token Cookie(SameSite=Strict)도 그대로 전달된다.
const backend = process.env.BACKEND_URL ?? "http://localhost:8080";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: { "/api": { target: backend, changeOrigin: false } },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test-setup.ts"],
  },
});
