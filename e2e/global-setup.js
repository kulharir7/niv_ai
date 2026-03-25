// e2e/global-setup.js — Login to Frappe and save auth state
const { test, expect } = require('@playwright/test');
const fs = require('fs');
const path = require('path');

const authDir = path.join(__dirname, '.auth');
const authFile = path.join(authDir, 'user.json');

test('login to Frappe', async ({ page }) => {
  // Skip if already authenticated
  if (fs.existsSync(authFile)) {
    const stats = fs.statSync(authFile);
    const ageMinutes = (Date.now() - stats.mtimeMs) / 60000;
    if (ageMinutes < 30) return; // Reuse if <30 min old
  }

  // Create auth directory
  if (!fs.existsSync(authDir)) fs.mkdirSync(authDir, { recursive: true });

  const baseURL = process.env.NIV_TEST_URL || 'http://localhost:8080';
  const user = process.env.NIV_TEST_USER || 'Administrator';
  const pass = process.env.NIV_TEST_PASS || 'admin';

  await page.goto(`${baseURL}/login`);
  await page.fill('#login_email', user);
  await page.fill('#login_password', pass);
  await page.click('.btn-login');
  await page.waitForURL('**/app/**', { timeout: 15000 });

  // Save auth state
  await page.context().storageState({ path: authFile });
});
