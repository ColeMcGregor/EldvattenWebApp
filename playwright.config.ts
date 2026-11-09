
import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: './e2e',

  // Acceptance tests can modify shared development data.
  // Run them sequentially to prevent conflicts.
  fullyParallel: false,
  workers: 1,

  // Prevent accidental exclusive tests in CI.
  forbidOnly: !!process.env.CI,

  // Retry failed tests only in CI.
  retries: process.env.CI ? 2 : 0,

  // Show results in the terminal and save an HTML report.
  reporter: [
    ['list'],
    ['html', { open: 'never' }],
  ],

  use: {
    // Django runs through Docker Compose on this port.
    baseURL: 'http://localhost:8000',

    // Save diagnostic data when a test fails.
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',

    // Keep each browser action within a reasonable timeout.
    actionTimeout: 10000,
    navigationTimeout: 15000,
  },

  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
    {
      name: 'firefox',
      use: { ...devices['Desktop Firefox'] },
    },
    {
      name: 'webkit',
      use: { ...devices['Desktop Safari'] },
    },
  ],

  // Docker Compose manages Django separately.
  // Playwright does not need to start the web server.
});
