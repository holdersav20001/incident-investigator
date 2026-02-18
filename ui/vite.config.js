import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/events':    'http://localhost:8000',
      '/incidents': 'http://localhost:8000',
      '/approvals': 'http://localhost:8000',
      '/health':    'http://localhost:8000',
    },
  },
})
