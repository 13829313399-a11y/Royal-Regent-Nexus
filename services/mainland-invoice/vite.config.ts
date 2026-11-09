import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { fileURLToPath, URL } from 'node:url'

export default defineConfig({
  base: '/mainland-invoice/',
  // Shared dependency installations must not share mutable Vite caches.
  cacheDir: fileURLToPath(new URL('./.local-dev/vite-cache', import.meta.url)),
  publicDir: false,
  plugins: [react()],
  resolve: { alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) } },
  server: { host: '127.0.0.1', proxy: { '/api': 'http://127.0.0.1:8000' } },
})
