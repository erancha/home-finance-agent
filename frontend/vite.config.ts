import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

const BACKEND = 'http://localhost:8010'

export default defineConfig({
  plugins: [react()],
  server: { proxy: { '/api': BACKEND, '/health': BACKEND } },
})
