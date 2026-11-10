
import {
  test,
  expect,
  type Browser,
  type Page,
} from '@playwright/test';

const REPORT_URL = '/feedback/report/';
const RECEIVED_URL = '/feedback/received/';
const AUDIT_URL = '/administration/system/logs/';

const RUN = `Feedback-${Date.now()}`;

const ADMIN_STORAGE =
  'playwright/.auth/suTest.json';

const MEMBER_STORAGE =
  'playwright/.auth/testuser01.json';

const reportData = {
  contact_email: 'feedback-test@example.com',
  description: `${RUN} The requested content does not appear.`,
  expected_behavior: 'The requested content should appear.',
  steps_to_reproduce: 'Open the page and select the item.',
  page_url: 'http://localhost:8000/community/',
};

async function fillReport(
  page: Page,
  description: string,
): Promise<void> {
  await page.locator('#id_description').fill(description);

  await page.locator('#id_expected_behavior').fill(
    reportData.expected_behavior,
  );

  await page.locator('#id_steps_to_reproduce').fill(
    reportData.steps_to_reproduce,
  );

  await page.locator('#id_page_url').fill(
    reportData.page_url,
  );

  await page.locator('#id_contact_email').fill(
    reportData.contact_email,
  );
}

async function openAdmin(
  browser: Browser,
): Promise<{
  page: Page;
  close: () => Promise<void>;
}> {
  const context = await browser.newContext({
    storageState: ADMIN_STORAGE,
  });

  const page = await context.newPage();

  return {
    page,
    close: () => context.close(),
  };
}

async function getLatestBugReportAudit(
  browser: Browser,
): Promise<{
  label: string;
  actor: string;
  details: string;
}> {
  const admin = await openAdmin(browser);

  try {
    const params = new URLSearchParams({
      action: 'CREATE',
      target_type: 'BugReport',
      source: 'WEB_APP',
    });

    await admin.page.goto(
      `${AUDIT_URL}?${params.toString()}`,
    );

    const row = admin.page.locator(
      '.administration-audit-table tbody tr',
    ).first();

    await expect(row).toBeVisible();

    await expect(row).toContainText('Bug Report #');
    await expect(row).toContainText('Create');
    await expect(row).toContainText('Web App');

    const label = await row.locator(
      '.administration-audit-target',
    ).innerText();

    const actor = await row.locator(
      'td',
    ).nth(1).innerText();

    await row.getByRole('link', {
      name: /View audit record/i,
    }).click();

    await expect(
      admin.page.getByRole('heading', {
        name: 'Record Summary',
      }),
    ).toBeVisible();

    const details = await admin.page.locator(
      'main',
    ).innerText();

    return {
      label: label.trim(),
      actor: actor.trim(),
      details,
    };
  } finally {
    await admin.close();
  }
}

test.describe('Feedback — bug report submission and auditing', () => {
  test.describe.configure({
    mode: 'serial',
  });

  test.use({
    storageState: {
      cookies: [],
      origins: [],
    },
  });

  test('Anonymous visitor can open the report form', async ({
    page,
  }) => {
    await page.goto(REPORT_URL);

    await expect(
      page.getByRole('heading', {
        name: 'Report a Bug',
      }),
    ).toBeVisible();

    await expect(
      page.locator('#id_description'),
    ).toBeVisible();

    await expect(
      page.locator('#id_expected_behavior'),
    ).toBeVisible();

    await expect(
      page.locator('#id_steps_to_reproduce'),
    ).toBeVisible();

    await expect(
      page.locator('#id_page_url'),
    ).toBeVisible();

    await expect(
      page.locator('#id_contact_email'),
    ).toBeVisible();

    await expect(
      page.getByRole('button', {
        name: 'Submit Bug Report',
      }),
    ).toBeVisible();
  });

  test('Invalid description does not submit', async ({
    page,
  }) => {
    await page.goto(REPORT_URL);

    await page.locator('#id_description').fill(
      'Short',
    );

    await page.getByRole('button', {
      name: 'Submit Bug Report',
    }).click();

    await expect(page).toHaveURL(
      new RegExp(`${REPORT_URL}$`),
    );

    await expect(
      page.locator('#id_description')
        .locator('xpath=following-sibling::*'),
    ).toContainText(
      'at least 10 characters',
    );
  });

  test('Page URL is populated from the reporting link', async ({
    page,
  }) => {
    const originalPage =
      'http://localhost:8000/events/';

    await page.goto(
      `${REPORT_URL}?page=${encodeURIComponent(originalPage)}`,
    );

    await expect(
      page.locator('#id_page_url'),
    ).toHaveValue(originalPage);
  });

  test('Anonymous visitor submits a report and creates an audit', async ({
    page,
    browser,
  }) => {
    await page.goto(REPORT_URL);

    await fillReport(
      page,
      `${RUN} Anonymous report: navigation does not respond.`,
    );

    await page.getByRole('button', {
      name: 'Submit Bug Report',
    }).click();

    await expect(page).toHaveURL(
      new RegExp(`${RECEIVED_URL}$`),
    );

    await expect(
      page.getByRole('heading', {
        name: 'Bug Report Received',
      }),
    ).toBeVisible();

    const audit = await getLatestBugReportAudit(
      browser,
    );

    expect(audit.label).toMatch(
      /^Bug Report #\d+$/,
    );

    expect(audit.actor).toBe('System');

    expect(audit.details).toContain(
      audit.label,
    );

    expect(audit.details).toMatch(
      /\bAction\s+Create\b/,
    );

    expect(audit.details).toContain(
      'BugReport',
    );

    expect(audit.details).toContain(
      'Web App',
    );

    expect(audit.details).toContain(
      "'NEW'",
    );

    expect(audit.details).not.toContain(
      reportData.contact_email,
    );

    expect(audit.details).not.toContain(
      `${RUN} Anonymous report`,
    );
  });

  test('Authenticated member submits a report with correct audit actor', async ({
    browser,
  }) => {
    const context = await browser.newContext({
      storageState: MEMBER_STORAGE,
    });

    const page = await context.newPage();

    try {
      await page.goto(REPORT_URL);

      await expect(
        page.getByRole('heading', {
          name: 'Report a Bug',
        }),
      ).toBeVisible();

      await fillReport(
        page,
        `${RUN} Member report: the content fails to render.`,
      );

      await page.getByRole('button', {
        name: 'Submit Bug Report',
      }).click();

      await expect(page).toHaveURL(
        new RegExp(`${RECEIVED_URL}$`),
      );

      const audit = await getLatestBugReportAudit(
        browser,
      );

      expect(audit.label).toMatch(
        /^Bug Report #\d+$/,
      );

      expect(audit.actor).toBeTruthy();
      expect(audit.actor).not.toBe('System');

      expect(audit.details).toContain(
        audit.label,
      );

      expect(audit.details).toMatch(
        /\bAction\s+Create\b/,
      );

      expect(audit.details).toContain(
        'BugReport',
      );

      expect(audit.details).toContain(
        'Web App',
      );

      expect(audit.details).toContain(
        "'NEW'",
      );

      expect(audit.details).not.toContain(
        reportData.contact_email,
      );

      expect(audit.details).not.toContain(
        `${RUN} Member report`,
      );
    } finally {
      await context.close();
    }
  });
});
