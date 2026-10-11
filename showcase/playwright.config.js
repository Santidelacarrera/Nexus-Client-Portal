const { defineConfig } = require('@playwright/test');

module.exports = defineConfig({
  testDir: 'tests/e2e',
  use: { baseURL: process.env.SHOWCASE_URL || 'http://127.0.0.1:9433', launchOptions: { executablePath: process.env.CHROMIUM_PATH || undefined } },
});
