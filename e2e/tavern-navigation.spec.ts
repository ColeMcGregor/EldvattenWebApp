
import { test, expect } from '@playwright/test';

test.use({
  storageState: 'playwright/.auth/testuser01.json',
});

test('Member can open a board and use breadcrumbs', async ({ page }) => {
  await page.goto('/community/');

  const boards = page.locator(
    '.forum-board-row .forum-board-heading a'
  );

  expect(
    await boards.count(),
    'A visible test board is required'
  ).toBeGreaterThan(0);

  const boardName = (await boards.first().innerText()).trim();

  await boards.first().click();

  await expect(
    page.getByRole('heading', { level: 1, name: boardName })
  ).toBeVisible();

  const breadcrumbs = page.getByRole('navigation', {
    name: 'Breadcrumb',
  });

  await expect(
    breadcrumbs.getByRole('link', { name: 'The Tavern' })
  ).toBeVisible();

  await expect(
    page.locator('#threads')
  ).toBeVisible();

  await breadcrumbs.getByRole('link', {
    name: 'The Tavern',
  }).click();

  await expect(page).toHaveURL(/\/community\/$/);
});

test('Thread breadcrumb returns to the board thread list', async ({ page }) => {
  await page.goto('/community/');

  const boardUrls = await page
    .locator('.forum-board-row .forum-board-heading a')
    .evaluateAll(links =>
      links.map(link => (link as HTMLAnchorElement).href)
    );

  let foundThread = false;

  for (const url of boardUrls) {
    await page.goto(url);

    const threads = page.locator(
      '.forum-thread-row .forum-thread-heading a'
    );

    if (await threads.count() === 0) {
      continue;
    }

    const boardName = (
      await page.locator('.forum-page-heading h1').innerText()
    ).trim();

    const threadName = (await threads.first().innerText()).trim();

    await threads.first().click();

    await expect(
      page.getByRole('heading', { level: 1, name: threadName })
    ).toBeVisible();

    const breadcrumbs = page.getByRole('navigation', {
      name: 'Breadcrumb',
    });

    const boardLink = breadcrumbs.getByRole('link', {
      name: boardName,
      exact: true,
    });

    await expect(boardLink).toHaveAttribute('href', /#threads$/);

    await boardLink.click();

    await expect(page).toHaveURL(/#threads$/);
    await expect(page.locator('#threads')).toBeVisible();

    foundThread = true;
    break;
  }

  expect(
    foundThread,
    'At least one accessible thread is required for this test'
  ).toBe(true);
});
