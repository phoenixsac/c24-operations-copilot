import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import path from 'node:path'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: { '@': path.resolve(__dirname, './src') },
  },
  server: {
    // 0.0.0.0 so the port is reachable from outside the container. Without
    // this Vite binds loopback only and the published port goes nowhere.
    host: true,
    port: 5173,
    strictPort: true,
    // Only used once VITE_API_MODE=live. The backend does not exist yet.
    // Inside docker-compose the API is reachable as `api`, not localhost —
    // localhost in a container is the container itself.
    proxy: {
      '/api': {
        target: process.env.VITE_API_TARGET ?? 'http://localhost:8000',
        changeOrigin: true,
        // The API mounts its routes at the root; `/api` is a client-side
        // prefix that exists only so the dev server knows what to forward.
        rewrite: (p) => p.replace(/^\/api/, ''),
      },
    },
  },
})
