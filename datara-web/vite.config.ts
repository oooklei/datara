import vue from '@vitejs/plugin-vue'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [vue()],
  server: {
    /* I1 F9：本地开发代理 /api → FastAPI 后端（http.ts base=/api/v1）
       DATARA_API_PROXY 可覆盖代理目标（如复用 1.9 nginx 的 /api 路由观察冻结版），默认不变 */
    proxy: {
      '/api': {
        target: process.env.DATARA_API_PROXY || 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
})
