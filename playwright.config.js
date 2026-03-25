// @ts-check
const { defineConfig } = require('@playwright/test');

module.exports = defineConfig({
  testDir: './e2e',
  timeout: 60000,
  retries: 1,
  use: {
    baseURL: process.env.NIV_TEST_URL || 'http://localhost:8080',
    screenshot: 'only-on-failure',
    trace: 'on-first-retry',
    // Login cookies will be set in global setup
    storageState: './e2e/.auth/user.json',
  },
  projects: [
    {
      name: 'setup',
      testMatch: /global-setup\.js/,
    },
    {
      name: 'chrome',
      use: { browserName: 'chromium' },
      dependencies: ['setup'],
    },
    {
      name: 'mobile',
      use: {
        browserName: 'chromium',
        ...require('@playwright/test').devices['Pixel 7'],
      },
      dependencies: ['setup'],
    },
  ],
});
