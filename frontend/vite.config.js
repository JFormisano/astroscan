import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    // Dev only: forward API calls to the FastAPI backend.
    proxy: { '/api': 'http://localhost:8000' },
  },
})
