import vue from '@vitejs/plugin-vue'
import { defineConfig } from 'vite'

export default defineConfig({
  plugins: [vue()],
  // G03 开发态代理：连 1.9 远程 rebuild 后端（与 deploy/wsl-frontend/nginx.conf 反代契约一致）
  // 原 localhost:8001 是本机旧 rebuild-api 开发默认端口，当前后端唯一真源在 1.9:18091
  server: { port: 18092, proxy: { '/api/v1': { target: 'http://192.168.1.9:18091', changeOrigin: true } } },
})
