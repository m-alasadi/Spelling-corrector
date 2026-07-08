import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/upload': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/correct': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/editor': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/health': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/api/grammar-check': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/api/grammar-check-batch': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
})
