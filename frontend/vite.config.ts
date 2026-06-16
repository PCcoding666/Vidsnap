import { defineConfig } from "vite";
import react from "@vitejs/plugin-react-swc";
import path from "path";
import { componentTagger } from "lovable-tagger";

// https://vitejs.dev/config/
export default defineConfig(({ mode }) => ({
  server: {
    host: "::",
    port: 8080,
    allowedHosts: [
      'vidsnap.space',
      'www.vidsnap.space',
      'vidsnap-test.space',
      'www.vidsnap-test.space',
      'localhost',
      '127.0.0.1'
    ],
    proxy: {
      // 代理 API 请求到后端服务，解决跨域问题
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        // 不重写路径，保持 /api/v1 前缀
      },
    },
  },
  preview: {
    host: true,
    port: 3000,
    allowedHosts: [
      'vidsnap.space',
      'www.vidsnap.space',
      'vidsnap-test.space',
      'www.vidsnap-test.space',
      'localhost',
      '127.0.0.1'
    ],
  },
  plugins: [react(), mode === "development" && componentTagger()].filter(Boolean),
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
}));