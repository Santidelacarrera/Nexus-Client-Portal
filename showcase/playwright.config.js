const { defineConfig } = require('@playwright/test');

module.exports = defineConfig({
  testDir: 'tests/e2e',
  use: { baseURL: process.env.SHOWCASE_URL || 'http://localhost:8100', launchOptions: { executablePath: process.env.CHROMIUM_PATH || undefined } },
});
