
import { test, expect } from '@playwright/test';

test('EldVatten homepage loads', async ({ page }) => {
  const response = await page.goto('/');

  expect(response?.status()).toBe(200);

  await expect(page.locator('body')).toBeVisible();
});
