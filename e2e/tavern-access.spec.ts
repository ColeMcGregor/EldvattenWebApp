
import { test, expect } from '@playwright/test';

test('Anonymous users cannot access the member Tavern', async ({ page }) => {
  await page.goto('/community/');

  await expect(page).toHaveURL(
    /\/accounts\/login\/\?next=/
  );
});

test.describe('Authenticated member', () => {
  test.use({
    storageState: 'playwright/.auth/testuser01.json',
  });

  test('Tavern navigation is available', async ({ page }) => {
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

  test('Tavern search is available', async ({ page }) => {
    await page.goto('/community/');

    await expect(
      page.getByRole('searchbox', {
        name: 'Search The Tavern',
      })
    ).toBeVisible();

    await expect(
      page.getByRole('button', {
        name: 'Search',
        exact: true,
      })
    ).toBeVisible();
  });
});
