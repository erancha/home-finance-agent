import react from '@vitejs/plugin-react'
import { defineConfig } from 'vitest/config'

export default defineConfig({
  plugins: [react()],
  // A test reads the A2A contract, which lives in docs/ at the repository root.
  server: { fs: { allow: ['..'] } },
  test: {
    environment: 'jsdom',
    pool: 'threads',
    globals: false,
    setupFiles: './src/test/setup.ts',
  },
})
