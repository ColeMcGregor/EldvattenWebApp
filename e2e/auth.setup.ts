
import { test as setup, expect } from '@playwright/test';
import { mkdirSync } from 'node:fs';
import { join } from 'node:path';

const authDirectory = join(
  process.cwd(),
  'playwright',
  '.auth'
);

const accounts = [
  {
    username: 'suTest',
    passwordVariable: 'E2E_SUTEST_PASSWORD',
  },
  {
    username: 'testuser01',
    passwordVariable: 'E2E_TESTUSER01_PASSWORD',
  },
  {
    username: 'testuser02',
    passwordVariable: 'E2E_TESTUSER02_PASSWORD',
  },
];

for (const account of accounts) {
  setup(`Authenticate ${account.username}`, async ({ page }) => {
    const password = process.env[account.passwordVariable];

    if (!password) {
      throw new Error(
        `Missing environment variable: ${account.passwordVariable}`
      );
    }

    await page.goto('/accounts/login/');

    await page.getByRole('textbox', {
      name: 'Username',
    }).fill(account.username);

    await page.getByLabel('Password').fill(password);

    await page.getByRole('button', {
      name: 'Login',
      exact: true,
    }).click();

    // Check the authenticated member application.
    await page.goto('/community/');

    await expect(page).toHaveURL(/\/community\/$/);

    await expect(
      page.getByRole('navigation', {
        name: 'EldVatten application navigation',
      })
    ).toBeVisible();

    mkdirSync(authDirectory, { recursive: true });

    await page.context().storageState({
      path: join(authDirectory, `${account.username}.json`),
    });
  });
}
