
import {
  test,
  expect,
  type Browser,
  type Page,
} from '@playwright/test';

const REPORT_URL = '/feedback/report/';
const RECEIVED_URL = '/feedback/received/';
const AUDIT_URL = '/administration/system/logs/';
const SYSTEM_URL = '/administration/system/';
const MANAGEMENT_URL = '/administration/system/bug-reports/';
const NOTIFICATIONS_URL = '/notifications/';

const RUN = `Feedback-${Date.now()}`;

const ADMIN_STORAGE = 'playwright/.auth/suTest.json';
const MEMBER_STORAGE = 'playwright/.auth/testuser01.json';
const SECOND_MEMBER_STORAGE = 'playwright/.auth/testuser02.json';

const reportData = {
  contact_email: 'feedback-test@example.com',
  expected_behavior: 'The requested content should appear.',
  steps_to_reproduce: 'Open the page and select the item.',
  page_url: 'http://localhost:8000/community/',
};

let managedReportId: number;

function reportLabelPattern(reportId: number): RegExp {
  return new RegExp(`^\\s*Bug Report #${reportId}\\s*$`);
}

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
  await page.locator('#id_page_url').fill(reportData.page_url);
  await page.locator('#id_contact_email').fill(
    reportData.contact_email,
  );
}

async function openWithStorage(
  browser: Browser,
  storageState: string,
) {
  const context = await browser.newContext({ storageState });

  return {
    context,
    page: await context.newPage(),
  };
}

async function getLatestBugReportAudit(
  browser: Browser,
): Promise<{
  label: string;
  actor: string;
  details: string;
}> {
  const { context, page } = await openWithStorage(
    browser,
    ADMIN_STORAGE,
  );

  try {
    const params = new URLSearchParams({
      action: 'CREATE',
      target_type: 'BugReport',
      source: 'WEB_APP',
    });

    await page.goto(`${AUDIT_URL}?${params.toString()}`);

    const row = page.locator(
      '.administration-audit-table tbody tr',
    ).first();

    await expect(row).toBeVisible();
    await expect(row).toContainText('Bug Report #');
    await expect(row).toContainText('Create');
    await expect(row).toContainText('Web App');

    const label = (
      await row.locator(
        '.administration-audit-target',
      ).innerText()
    ).trim();

    const actor = (
      await row.locator('td').nth(1).innerText()
    ).trim();

    await row.getByRole('link', {
      name: /View audit record/i,
    }).click();

    await expect(
      page.getByRole('heading', {
        name: 'Record Summary',
      }),
    ).toBeVisible();

    return {
      label,
      actor,
      details: await page.locator('main').innerText(),
    };
  } finally {
    await context.close();
  }
}

async function getUpdateAuditForReport(
  page: Page,
  reportId: number,
): Promise<string> {
  const params = new URLSearchParams({
    action: 'UPDATE',
    target_type: 'BugReport',
    source: 'WEB_APP',
  });

  await page.goto(`${AUDIT_URL}?${params.toString()}`);

  const row = page.locator(
    '.administration-audit-table tbody tr',
  ).filter({
    has: page.locator(
      '.administration-audit-target',
    ).filter({
      hasText: reportLabelPattern(reportId),
    }),
  }).first();

  await expect(row).toBeVisible();
  await expect(row).toContainText('Update');

  await row.getByRole('link', {
    name: /View audit record/i,
  }).click();

  await expect(
    page.getByRole('heading', {
      name: 'Record Summary',
    }),
  ).toBeVisible();

  return page.locator('main').innerText();
}

test.describe('Feedback — submissions and administration', () => {
  test.describe.configure({ mode: 'serial' });

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

    for (const field of [
      'description',
      'expected_behavior',
      'steps_to_reproduce',
      'page_url',
      'contact_email',
    ]) {
      await expect(
        page.locator(`#id_${field}`),
      ).toBeVisible();
    }

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

    await page.locator('#id_description').fill('Short');

    await page.getByRole('button', {
      name: 'Submit Bug Report',
    }).click();

    await expect(page).toHaveURL(
      new RegExp(`${REPORT_URL}$`),
    );

    await expect(
      page.locator('#id_description')
        .locator('xpath=following-sibling::*'),
    ).toContainText('at least 10 characters');
  });

  test('Page URL is populated from the reporting link', async ({
    page,
  }) => {
    const originalPage = 'http://localhost:8000/events/';

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

    const audit = await getLatestBugReportAudit(browser);

    expect(audit.label).toMatch(/^Bug Report #\d+$/);
    expect(audit.actor).toBe('System');
    expect(audit.details).toContain(audit.label);
    expect(audit.details).toMatch(/\bAction\s+Create\b/);
    expect(audit.details).toContain('BugReport');
    expect(audit.details).toContain('Web App');
    expect(audit.details).toContain("'NEW'");

    expect(audit.details).not.toContain(
      reportData.contact_email,
    );

    expect(audit.details).not.toContain(
      `${RUN} Anonymous report`,
    );
  });

  test('Authenticated member submits a report with attributed audit', async ({
    browser,
  }) => {
    const { context, page } = await openWithStorage(
      browser,
      MEMBER_STORAGE,
    );

    try {
      await page.goto(REPORT_URL);

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

      const audit = await getLatestBugReportAudit(browser);

      expect(audit.label).toMatch(/^Bug Report #\d+$/);

      managedReportId = Number(
        audit.label.match(/#(\d+)$/)![1],
      );

      expect(audit.actor).toBeTruthy();
      expect(audit.actor).not.toBe('System');
      expect(audit.details).toContain(audit.label);
      expect(audit.details).toMatch(/\bAction\s+Create\b/);
      expect(audit.details).toContain('BugReport');
      expect(audit.details).toContain('Web App');
      expect(audit.details).toContain("'NEW'");

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

  test('Administrator receives and opens bug report notification', async ({
    browser,
  }) => {
    const admin = await openWithStorage(
      browser,
      ADMIN_STORAGE,
    );

    const member = await openWithStorage(
      browser,
      SECOND_MEMBER_STORAGE,
    );

    const description =
      `${RUN} Notification test: the page does not respond.`;

    try {
      // Capture the existing notification links.
      await admin.page.goto(NOTIFICATIONS_URL);

      const existingNotificationLinks = new Set(
        await admin.page.locator(
          'article h2 a',
        ).evaluateAll((links) =>
          links.map((link) =>
            link.getAttribute('href'),
          ),
        ),
      );

      // Submit a new report using a separate member account.
      await member.page.goto(REPORT_URL);

      await fillReport(
        member.page,
        description,
      );

      await member.page.getByRole('button', {
        name: 'Submit Bug Report',
      }).click();

      await expect(member.page).toHaveURL(
        new RegExp(`${RECEIVED_URL}$`),
      );

      // Find the notification created by this submission.
      await admin.page.reload();

      const notificationLinks = admin.page.locator(
             'article h2 a',
        ).filter({
             hasText: /New Bug Report #\d+/,
        }); 

      await expect(notificationLinks.first()).toBeVisible();

      const allNotificationLinks =
        await notificationLinks.all();

      let newNotificationHref: string | null = null;
      let notificationTitle = '';

      for (const link of allNotificationLinks) {
        const href = await link.getAttribute('href');

        if (href && !existingNotificationLinks.has(href)) {
          newNotificationHref = href;
          notificationTitle = (await link.innerText()).trim();
          break;
        }
      }

      expect(newNotificationHref).not.toBeNull();

      const match = notificationTitle.match(
        /New Bug Report #(\d+)/,
      );

      expect(match).not.toBeNull();

      const reportId = Number(match![1]);

      const notificationArticle = admin.page.locator(
        'article',
      ).filter({
        has: admin.page.locator(
          `h2 a[href="${newNotificationHref}"]`,
        ),
      });

      await expect(notificationArticle).toContainText(
        'System',
      );

      await expect(
        notificationArticle.getByText('Unread', {
          exact: true,
        }),
      ).toBeVisible();

      // Opening the notification should navigate to the report.
      await notificationArticle.locator('h2 a').click();

      await expect(admin.page).toHaveURL(
        new RegExp(`${MANAGEMENT_URL}${reportId}/$`),
      );

      await expect(
        admin.page.getByRole('heading', {
          name: `Bug Report #${reportId}`,
        }),
      ).toBeVisible();

      await expect(
        admin.page.locator('main'),
      ).toContainText(description);

      // The notification should now be marked as read.
      await admin.page.goto(NOTIFICATIONS_URL);

      const openedNotification = admin.page.locator(
        'article',
      ).filter({
        has: admin.page.locator(
          `h2 a[href="${newNotificationHref}"]`,
        ),
      });

      await expect(
        openedNotification.getByText('Read', {
          exact: true,
        }),
      ).toBeVisible();
    } finally {
      await member.context.close();
      await admin.context.close();
    }
  });

  test('Full admin sees Bug Reports under Audit & System', async ({
    browser,
  }) => {
    const { context, page } = await openWithStorage(
      browser,
      ADMIN_STORAGE,
    );

    try {
      await page.goto(SYSTEM_URL);

      const link = page.getByRole('link', {
        name: /Bug Reports/i,
      });

      await expect(link).toBeVisible();
      await link.click();

      await expect(page).toHaveURL(
        new RegExp(`${MANAGEMENT_URL}$`),
      );

      await expect(
        page.getByRole('heading', {
          name: 'Bug Reports',
        }),
      ).toBeVisible();
    } finally {
      await context.close();
    }
  });

  test('Admin can inspect report details', async ({
    browser,
  }) => {
    const { context, page } = await openWithStorage(
      browser,
      ADMIN_STORAGE,
    );

    try {
      await page.goto(
        `${MANAGEMENT_URL}${managedReportId}/`,
      );

      await expect(
        page.getByRole('heading', {
          name: `Bug Report #${managedReportId}`,
        }),
      ).toBeVisible();

      await expect(
        page.locator('main'),
      ).toContainText(`${RUN} Member report`);

      await expect(
        page.locator('#id_status'),
      ).toHaveValue('NEW');

      await expect(
        page.locator('#id_admin_notes'),
      ).toBeVisible();
    } finally {
      await context.close();
    }
  });

  test('Admin changes report status and produces UPDATE audit', async ({
    browser,
  }) => {
    const { context, page } = await openWithStorage(
      browser,
      ADMIN_STORAGE,
    );

    try {
      await page.goto(
        `${MANAGEMENT_URL}${managedReportId}/`,
      );

      await page.locator('#id_status')
        .selectOption('INVESTIGATING');

      await page.getByRole('button', {
        name: 'Save Changes',
      }).click();

      await expect(page).toHaveURL(
        new RegExp(
          `${MANAGEMENT_URL}${managedReportId}/$`,
        ),
      );

      await expect(
        page.locator('#id_status'),
      ).toHaveValue('INVESTIGATING');

      await expect(
        page.locator('main'),
      ).toContainText('Bug report updated.');

      const audit = await getUpdateAuditForReport(
        page,
        managedReportId,
      );

      expect(audit).toMatch(/\bAction\s+Update\b/);
      expect(audit).toContain("'NEW'");
      expect(audit).toContain("'INVESTIGATING'");
      expect(audit).not.toContain(`${RUN} Member report`);
    } finally {
      await context.close();
    }
  });

  test('Admin edits internal notes without exposing their text in audit', async ({
    browser,
  }) => {
    const { context, page } = await openWithStorage(
      browser,
      ADMIN_STORAGE,
    );

    const notes = `${RUN} private investigation notes`;

    try {
      await page.goto(
        `${MANAGEMENT_URL}${managedReportId}/`,
      );

      await page.locator('#id_admin_notes').fill(notes);

      await page.getByRole('button', {
        name: 'Save Changes',
      }).click();

      await expect(
        page.locator('#id_admin_notes'),
      ).toHaveValue(notes);

      const audit = await getUpdateAuditForReport(
        page,
        managedReportId,
      );

      expect(audit).toContain('Internal notes updated.');
      expect(audit).not.toContain(notes);
    } finally {
      await context.close();
    }
  });

  test('Status filter shows matching report and excludes it from New', async ({
    browser,
  }) => {
    const { context, page } = await openWithStorage(
      browser,
      ADMIN_STORAGE,
    );

    try {
      await page.goto(
        `${MANAGEMENT_URL}?status=INVESTIGATING`,
      );

      const reportRow = page.locator(
        '.administration-audit-table tbody tr',
      ).filter({
        has: page.locator(
          '.administration-audit-target',
        ).filter({
          hasText: reportLabelPattern(managedReportId),
        }),
      });

      await expect(reportRow).toBeVisible();
      await expect(reportRow).toContainText('Investigating');

      await page.goto(
        `${MANAGEMENT_URL}?status=NEW`,
      );

      await expect(
        page.locator(
          '.administration-audit-target',
        ).filter({
          hasText: reportLabelPattern(managedReportId),
        }),
      ).toHaveCount(0);
    } finally {
      await context.close();
    }
  });

  test('Non-admin member cannot view bug report management pages', async ({
    browser,
  }) => {
    const { context, page } = await openWithStorage(
      browser,
      MEMBER_STORAGE,
    );

    try {
      const listing = await page.request.get(
        MANAGEMENT_URL,
      );

      expect(listing.status()).toBe(403);

      const detail = await page.request.get(
        `${MANAGEMENT_URL}${managedReportId}/`,
      );

      expect(detail.status()).toBe(403);
    } finally {
      await context.close();
    }
  });

  test('Anonymous visitor cannot view bug report management pages', async ({
    page,
  }) => {
    const listing = await page.request.get(
      MANAGEMENT_URL,
      { maxRedirects: 0 },
    );

    expect([301, 302, 303]).toContain(listing.status());

    const detail = await page.request.get(
      `${MANAGEMENT_URL}${managedReportId}/`,
      { maxRedirects: 0 },
    );

    expect([301, 302, 303]).toContain(detail.status());
  });
});
