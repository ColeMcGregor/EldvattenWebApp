
import { test, expect } from '@playwright/test';

test.use({
  storageState: 'playwright/.auth/testuser01.json',
});

test('Member can access The Tavern', async ({ page }) => {
  await page.goto('/community/');

  await expect(
    page.getByRole('heading', {
      name: 'The Tavern',
      exact: true,
    })
  ).toBeVisible();

  await expect(
    page.getByRole('navigation', {
      name: 'EldVatten application navigation',
    })
  ).toBeVisible();
});
