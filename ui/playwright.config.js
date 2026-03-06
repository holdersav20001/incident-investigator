import { defineConfig } from '@playwright/test'

export default defineConfig({
  testDir: './e2e',
  timeout: 60_000,
  expect: { timeout: 10_000 },
  use: {
    baseURL: 'http://localhost:5173',
    headless: true,
    screenshot: 'only-on-failure',
  },
  webServer: [
    {
      // Start the FastAPI backend
      command: 'python ../main.py',
      port: 8000,
      timeout: 30_000,
      reuseExistingServer: true,
    },
    {
      // Start the Vite dev server
      command: 'npm run dev',
      port: 5173,
      timeout: 30_000,
      reuseExistingServer: true,
    },
  ],
  projects: [
    {
      name: 'chromium',
      use: { browserName: 'chromium' },
    },
  ],
})
