import vue from '@vitejs/plugin-vue'
import { defineConfig } from 'vite'

export default defineConfig({
  plugins: [vue()],
  server: { port: 18092, proxy: { '/api/v1': { target: 'http://localhost:8001', changeOrigin: true } } },
})
