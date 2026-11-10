import { test, expect, type Page } from '@playwright/test';

// Run only against a disposable development database.
// Operations create real records; audit entries are intentionally retained.
// The suite uses authenticated states from e2e/auth.setup.ts.

const RUN = `AuditVerify-${Date.now()}`;
const AUDIT = '/administration/system/logs/';

const state: {
  actionId?: number;
  actionTitle?: string;
  categoryId?: number;
  categoryName?: string;
  boardId?: number;
  boardName?: string;
  threadId?: number;
  threadTitle?: string;
  resourceId?: number;
  resourceTitle?: string;
  conversationId?: number;
  testUserId?: number;
  organizationId?: number;
  organizationName?: string;
  eventId?: number;
  eventTitle?: string;
  voteId?: number;
  voteTitle?: string;
  accountId?: number;
  accountName?: string;
  groupValue?: string;
} = {};

function idFrom(url: string, pattern: RegExp): number {
  const match = url.match(pattern);
  expect(match, `Expected URL to match ${pattern}: ${url}`).not.toBeNull();
  return Number(match![1]);
}

async function assertAudit(
  page: Page,
  action: string,
  targetType: string,
  targetLabel: string,
  verifyDetail = true,
): Promise<void> {
  const params = new URLSearchParams({ action, target_type: targetType });
  await page.goto(`${AUDIT}?${params}`);
  const record = page.locator('.administration-audit-table tbody tr')
    .filter({ hasText: targetLabel }).first();
  await expect(record, `Missing ${action} audit for ${targetType}: ${targetLabel}`)
    .toBeVisible();
  await expect(record).toContainText('Web App');
  if (verifyDetail) {
    await record.getByRole('link', { name: /View audit record/i }).click();
    await expect(page.getByRole('heading', { name: 'Record Summary' })).toBeVisible();
    await expect(page.locator('.administration-audit-detail-grid'))
      .toContainText(targetLabel);
  }
}

async function postWithCsrf(page: Page, url: string): Promise<void> {
  // All the POST-only moderation endpoints use Django's session/CSRF protection.
  // Read the token from a rendered form rather than disabling CSRF in tests.
  const token = await page.locator('input[name="csrfmiddlewaretoken"]').first().inputValue();
  const response = await page.request.post(url, {
    form: { csrfmiddlewaretoken: token },
    maxRedirects: 0,
  });
  expect([302, 303], `POST ${url} returned ${response.status()}`)
    .toContain(response.status());
}

async function adminAudit(page: Page, action: string, targetType: string, targetLabel: string) {
  const params = new URLSearchParams({ action, target_type: targetType, source: 'ADMIN' });
  await page.goto(`${AUDIT}?${params}`);
  const record = page.locator('.administration-audit-table tbody tr')
    .filter({ hasText: targetLabel }).first();
  await expect(record, `Missing ADMIN ${action}: ${targetLabel}`).toBeVisible();
  await expect(record).toContainText('Django Admin');
}

test.describe('Audit verification suite — real producers', () => {
  test.describe.configure({ mode: 'serial' });
  test.use({ storageState: 'playwright/.auth/suTest.json' });

  test('Actions — CREATE', async ({ page }) => {
    state.actionTitle = `${RUN} Action`;
    await page.goto('/actions/create/');
    await page.locator('#id_title').fill(state.actionTitle);
    await page.locator('#id_instructions').fill('Audit verification: create');
    await page.getByRole('button', { name: 'Save Action' }).click();
    state.actionId = idFrom(page.url(), /\/actions\/manage\/(\d+)\/$/);
    await assertAudit(page, 'CREATE', 'Action', state.actionTitle);
  });

  test('Actions — UPDATE', async ({ page }) => {
    expect(state.actionId).toBeDefined();
    await page.goto(`/actions/manage/${state.actionId}/edit/`);
    await page.locator('#id_instructions').fill('Audit verification: updated');
    await page.getByRole('button', { name: 'Save Action' }).click();
    await assertAudit(page, 'UPDATE', 'Action', state.actionTitle!);
  });

  test('Actions — DELETE', async ({ page }) => {
    expect(state.actionId).toBeDefined();
    await page.goto(`/actions/manage/${state.actionId}/delete/`);
    await page.locator('main form[method="post"]').first().locator('button[type="submit"]').click();
    await assertAudit(page, 'DELETE', 'Action', state.actionTitle!);
  });

  test('The Tavern — category CREATE', async ({ page }) => {
    state.categoryName = `${RUN} Category`;
    await page.goto('/community/categories/create/');
    await page.locator('#id_name').fill(state.categoryName);
    await page.locator('main form[method="post"] button[type="submit"]').click();
    await expect(page).toHaveURL(/\/community\/$/);
    // Read the generated category ID from the forum section.
    const section = page.locator('[id^="category-"]')
      .filter({ hasText: state.categoryName }).first();
    await expect(section).toBeVisible();
    state.categoryId = idFrom(await section.getAttribute('id') || '', /^category-(\d+)$/);
    await assertAudit(page, 'CREATE', 'forum category', state.categoryName);
  });

  test('The Tavern — category UPDATE', async ({ page }) => {
    await page.goto(`/community/categories/${state.categoryId}/edit/`);
    await page.locator('#id_description').fill('Updated by audit verification');
    await page.locator('main form[method="post"] button[type="submit"]').click();
    await assertAudit(page, 'UPDATE', 'forum category', state.categoryName!);
  });

  test('The Tavern — category ARCHIVE', async ({ page }) => {
    await page.goto('/community/');
    await postWithCsrf(page, `/community/categories/${state.categoryId}/archive/`);
    await assertAudit(page, 'ARCHIVE', 'forum category', state.categoryName!);
  });

  test('The Tavern — category RESTORE', async ({ page }) => {
    await page.goto('/community/?archived=1');
    await postWithCsrf(page, `/community/categories/${state.categoryId}/restore/`);
    await assertAudit(page, 'RESTORE', 'forum category', state.categoryName!);
  });

  test('The Tavern — board CREATE', async ({ page }) => {
    state.boardName = `${RUN} Board`;
    await page.goto(`/community/categories/${state.categoryId}/boards/create/`);
    await page.locator('#id_name').fill(state.boardName);
    await page.locator('#id_thread_creation_policy').selectOption('OPEN');
    await page.getByRole('button', { name: 'Create Board' }).click();
    state.boardId = idFrom(page.url(), /\/community\/boards\/(\d+)\/$/);
    await assertAudit(page, 'CREATE', 'forum board', state.boardName);
  });

  test('The Tavern — board LOCK', async ({ page }) => {
    await page.goto(`/community/boards/${state.boardId}/`);
    await postWithCsrf(page, `/community/boards/${state.boardId}/lock/`);
    await assertAudit(page, 'LOCK', 'forum board', state.boardName!);
  });

  test('The Tavern — board UNLOCK', async ({ page }) => {
    await page.goto(`/community/boards/${state.boardId}/`);
    await postWithCsrf(page, `/community/boards/${state.boardId}/unlock/`);
    await assertAudit(page, 'UNLOCK', 'forum board', state.boardName!);
  });

  test('The Tavern — thread CREATE', async ({ page }) => {
    state.threadTitle = `${RUN} Thread`;
    await page.goto(`/community/boards/${state.boardId}/threads/create/`);
    await page.locator('#id_title').fill(state.threadTitle);
    await page.locator('#id_body').fill('Audit verification opening post.');
    await page.locator('main form[method="post"] button[type="submit"]').last().click();
    state.threadId = idFrom(page.url(), /\/community\/threads\/(\d+)\/$/);
    await assertAudit(page, 'CREATE', 'forum thread', state.threadTitle);
  });

  for (const [action, endpoint] of [
    ['PIN', 'pin'],
    ['UNPIN', 'unpin'],
    ['LOCK', 'lock'],
    ['UNLOCK', 'unlock'],
    ['ARCHIVE', 'archive'],
    ['RESTORE', 'restore'],
  ] as const) {
    test(`The Tavern — thread ${action}`, async ({ page }) => {
      await page.goto(`/community/threads/${state.threadId}/${action === 'RESTORE' ? '?archived=1' : ''}`);
      await postWithCsrf(page, `/community/threads/${state.threadId}/${endpoint}/`);
      await assertAudit(page, action, 'forum thread', state.threadTitle!);
    });
  }

  test('Resources — CREATE link resource', async ({ page }) => {
    state.resourceTitle = `${RUN} Resource`;
    await page.goto('/resources/manage/create/');
    await page.locator('#id_title').fill(state.resourceTitle);
    await page.locator('#id_resource_type').selectOption('LINK');
    await page.locator('#id_external_url').fill('https://example.com/audit-test');
    await page.locator('#id_visibility').selectOption('MEMBERS');
    await page.locator('main form[method="post"] button[type="submit"]').last().click();
    state.resourceId = idFrom(page.url(), /\/resources\/manage\/(\d+)\/$/);
    await assertAudit(page, 'CREATE', 'Resource', state.resourceTitle);
  });

  test('Resources — UPDATE', async ({ page }) => {
    await page.goto(`/resources/manage/${state.resourceId}/edit/`);
    await page.locator('#id_description').fill('Updated by audit verification suite');
    await page.locator('main form[method="post"] button[type="submit"]').last().click();
    await assertAudit(page, 'UPDATE', 'Resource', state.resourceTitle!);
  });

  test('Organization Admin — CREATE citizenship class', async ({ page }) => {
    state.organizationName = `${RUN} Class`;
    await page.goto('/admin/organization/citizenshipclass/add/');
    await page.locator('#id_name').fill(state.organizationName);
    await page.locator('input[name="_save"]').click();
    await expect(page).toHaveURL(/\/admin\/organization\/citizenshipclass\/(?:\?.*)?$/);
    await adminAudit(page, 'CREATE', 'Citizenship class', state.organizationName);
  });

  test('Organization Admin — UPDATE citizenship class', async ({ page }) => {
    await page.goto(`/admin/organization/citizenshipclass/?q=${encodeURIComponent(state.organizationName!)}`);
    await page.getByRole('link', { name: state.organizationName!, exact: true }).click();
    state.organizationId = idFrom(page.url(), /\/admin\/organization\/citizenshipclass\/(\d+)\/change\//);
    await page.locator('#id_description').fill('Audit verification changed');
    await page.locator('input[name="_save"]').click();
    await adminAudit(page, 'UPDATE', 'Citizenship class', state.organizationName!);
  });

  test('Organization Admin — DELETE citizenship class', async ({ page }) => {
    await page.goto(`/admin/organization/citizenshipclass/${state.organizationId}/delete/`);
    await page.locator('form input[type="submit"]').last().click();
    await adminAudit(page, 'DELETE', 'Citizenship class', state.organizationName!);
  });

  test('Messaging — CREATE direct conversation', async ({ page }) => {
    await page.goto('/messages/');
    const target = page.locator('select[name="participants"] option')
      .filter({ hasText: 'testuser01' }).first();
    await expect(target).toHaveCount(1);
    const userId = await target.getAttribute('value');
    expect(userId).toBeTruthy();
    state.testUserId = Number(userId);
    const csrf = await page.locator('input[name="csrfmiddlewaretoken"]').first().inputValue();
    const response = await page.request.post('/messages/create/', {
      form: { csrfmiddlewaretoken: csrf, conversation_type: 'DIRECT', participants: userId! },
    });
    expect(response.ok()).toBeTruthy();
    state.conversationId = idFrom(response.url(), /\/messages\/(\d+)\/$/);
    await assertAudit(page, 'CREATE', 'conversation', `Conversation ${state.conversationId}`);
  });

  test('Messaging — CREATE message', async ({ page }) => {
    await page.goto(`/messages/${state.conversationId}/`);
    const csrf = await page.locator('input[name="csrfmiddlewaretoken"]').first().inputValue();
    const response = await page.request.post(`/messages/${state.conversationId}/send/`, {
      form: { csrfmiddlewaretoken: csrf, body: `${RUN} Message` },
    });
    expect(response.ok()).toBeTruthy();
    // Message labels do not contain the body; verify its conversation ID in the recorded JSON.
    await page.goto(`${AUDIT}?action=CREATE&target_type=message`);
    const record = page.locator('.administration-audit-table tbody tr').first();
    await expect(record).toBeVisible();
    await record.getByRole('link', { name: /View audit record/i }).click();
    await expect(page.getByRole('heading', { name: 'Recorded Values' })).toBeVisible();
    await expect(page.locator('.administration-audit-value-panel').last())
      .toContainText(String(state.conversationId));
  });

  test('Messaging — CREATE user block', async ({ page }) => {
    await page.goto(`/messages/${state.conversationId}/`);
    await postWithCsrf(page, `/messages/block/${state.testUserId}/`);
    await page.goto(`${AUDIT}?action=CREATE&target_type=user%20block`);
    await expect(page.locator('.administration-audit-table tbody tr').first()).toBeVisible();
  });

  test('Messaging — DELETE user block', async ({ page }) => {
    await page.goto('/messages/');
    await postWithCsrf(page, `/messages/unblock/${state.testUserId}/`);
    await page.goto(`${AUDIT}?action=DELETE&target_type=user%20block`);
    await expect(page.locator('.administration-audit-table tbody tr').first()).toBeVisible();
  });

  test('Messaging — UPDATE conversation participant on leave', async ({ page }) => {
    await page.goto(`/messages/${state.conversationId}/`);
    await postWithCsrf(page, `/messages/${state.conversationId}/leave/`);
    await page.goto(`${AUDIT}?action=UPDATE&target_type=conversation%20participant`);
    await expect(page.locator('.administration-audit-table tbody tr').first()).toBeVisible();
  });

  test('Events — CREATE', async ({ page }) => {
    state.eventTitle = `${RUN} Event`;
    await page.goto('/events/create/');
    await page.locator('#id_title').fill(state.eventTitle);
    await page.locator('#id_description').fill('Audit verification event');
    await page.locator('#id_start_at').fill('2027-06-01T12:00');
    await page.locator('#id_end_at').fill('2027-06-01T13:00');
    await page.locator('#id_visibility').selectOption('MEMBERS');
    await page.getByRole('button', { name: 'Save Event' }).click();
    state.eventId = idFrom(page.url(), /\/events\/(\d+)\/$/);
    await assertAudit(page, 'CREATE', 'event', state.eventTitle);
  });

  test('Events — UPDATE', async ({ page }) => {
    await page.goto(`/events/${state.eventId}/edit/`);
    await page.locator('#id_description').fill('Audit verification event updated');
    await page.getByRole('button', { name: 'Save Event' }).click();
    await assertAudit(page, 'UPDATE', 'event', state.eventTitle!);
  });

  test('Events — DELETE', async ({ page }) => {
    await page.goto(`/events/${state.eventId}/delete/`);
    await page.locator('main form[method="post"] button[type="submit"]').click();
    await assertAudit(page, 'DELETE', 'event', state.eventTitle!);
  });

  test('Voting — CREATE draft', async ({ page }) => {
    state.voteTitle = `${RUN} Vote`;
    await page.goto('/votes/manage/create/');
    await page.locator('#id_title').fill(state.voteTitle);
    await page.locator('#id_description').fill('Audit verification draft');
    await page.getByRole('button', { name: 'Save as Draft' }).click();
    state.voteId = idFrom(page.url(), /\/votes\/manage\/(\d+)\/$/);
    await assertAudit(page, 'CREATE', 'Vote', state.voteTitle);
  });

  test('Voting — UPDATE draft', async ({ page }) => {
    await page.goto(`/votes/manage/${state.voteId}/edit/`);
    await page.locator('#id_description').fill('Audit verification draft updated');
    await page.getByRole('button', { name: 'Save as Draft' }).click();
    await assertAudit(page, 'UPDATE', 'Vote', state.voteTitle!);
  });

  test('Voting — DELETE draft', async ({ page }) => {
    await page.goto(`/votes/manage/${state.voteId}/delete/`);
    await page.locator('main form[method="post"] button[type="submit"]').click();
    await assertAudit(page, 'DELETE', 'Vote', state.voteTitle!);
  });


  test('Accounts Admin — CREATE a disposable pending account', async ({ page }) => {
    state.accountName = `${RUN}-account`.toLowerCase();
    const password = `E2E-only-${Date.now()}-Test!`;
    await page.goto('/admin/accounts/user/add/');
    await page.locator('#id_username').fill(state.accountName);
    await page.locator('#id_password1').fill(password);
    await page.locator('#id_password2').fill(password);
    await page.locator('#id_account_status').selectOption('PENDING');
    await page.locator('input[name="_save"]').click();
    await page.goto(`/admin/accounts/user/?q=${encodeURIComponent(state.accountName)}`);
    await page.getByRole('link', { name: state.accountName, exact: true }).click();
    state.accountId = idFrom(page.url(), /\/admin\/accounts\/user\/(\d+)\/change\//);
    await adminAudit(page, 'CREATE', 'user account', state.accountName);
  });

  for (const [status, action] of [
    ['MEMBER', 'APPROVE'],
    ['SUSPENDED', 'SUSPEND'],
    ['MEMBER', 'RESTORE'],
  ] as const) {
    test(`Accounts Admin — ${action}`, async ({ page }) => {
      await page.goto(`/admin/accounts/user/${state.accountId}/change/`);
      await page.locator('#id_account_status').selectOption(status);
      await page.locator('input[name="_save"]').click();
      await expect(page).toHaveURL(/\/admin\/accounts\/user\/(?:\?.*)?$/);
      await adminAudit(page, action, 'user account', state.accountName!);
    });
  }

  test('Accounts Admin — ASSIGN and REMOVE an application role', async ({ page }) => {
    await page.goto(`/admin/accounts/user/${state.accountId}/change/`);
    const choices = page.locator('#id_groups option');
    const first = choices.first();
    test.skip(await choices.count() === 0, 'No existing Django groups to assign');
    state.groupValue = (await first.getAttribute('value'))!;
    await page.locator('#id_groups').selectOption([state.groupValue]);
    await page.locator('input[name="_save"]').click();
    await adminAudit(page, 'ASSIGN', 'application role', state.accountName!);

    await page.goto(`/admin/accounts/user/${state.accountId}/change/`);
    await page.locator('#id_groups').selectOption([]);
    await page.locator('input[name="_save"]').click();
    await adminAudit(page, 'REMOVE', 'application role', state.accountName!);
  });

});
