
import { defineConfig, devices } from '@playwright/test';
import { existsSync } from 'node:fs';
import { loadEnvFile } from 'node:process';

if (existsSync('.env.playwright')) {
  loadEnvFile('.env.playwright');
}

export default defineConfig({
  testDir: './e2e',

  fullyParallel: false,
  workers: 1,

  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,

  reporter: [
    ['list'],
    ['html', { open: 'never' }],
  ],

  use: {
    baseURL: 'http://localhost:8000',

    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',

    actionTimeout: 10000,
    navigationTimeout: 15000,
  },

  projects: [
    {
      name: 'setup',
      testMatch: '**/*.setup.ts',
    },

    {
      name: 'chromium',
      testMatch: '**/*.spec.ts',
      use: { ...devices['Desktop Chrome'] },
      dependencies: ['setup'],
    },

    {
      name: 'firefox',
      testMatch: '**/*.spec.ts',
      use: { ...devices['Desktop Firefox'] },
      dependencies: ['setup'],
    },

    {
      name: 'webkit',
      testMatch: '**/*.spec.ts',
      use: { ...devices['Desktop Safari'] },
      dependencies: ['setup'],
    },
  ],
});
