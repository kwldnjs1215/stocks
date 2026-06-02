import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// start.bat이 BACKEND_PORT / FRONTEND_PORT 환경변수를 전달
const backendPort = process.env.BACKEND_PORT || '8001'
const frontendPort = parseInt(process.env.FRONTEND_PORT || '5176')

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    host: true,
    port: frontendPort,
    strictPort: true,
    proxy: {
      '/api': `http://localhost:${backendPort}`,
    },
  },
})
