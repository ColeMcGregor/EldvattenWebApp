import { test, expect, type Page } from '@playwright/test';

// Development/test database only. Creates real records and retains audit history.
// Deliberately complements audit-verification-suite.spec.ts instead of duplicating it.
// Runs with the suTest authentication state created by e2e/auth.setup.ts.

const RUN = `AuditVerify2-${Date.now()}`;
const AUDIT_URL = '/administration/system/logs/';
const USERNAME = 'testuser01';

const data: {
  categoryId?: number;
  categoryName?: string;
  boardId?: number;
  secondBoardId?: number;
  boardName?: string;
  threadId?: number;
  threadTitle?: string;
  secondThreadId?: number;
  splitSourceId?: number;
  splitPostId?: number;
  postId?: number;
  groupConversationId?: number;
  memberId?: string;
  actionId?: number;
  actionTitle?: string;
  eventId?: number;
  eventTitle?: string;
  voteId?: number;
  voteTitle?: string;
} = {};

function extractId(value: string, pattern: RegExp): number {
  const match = value.match(pattern);
  expect(match, `Expected ${value} to match ${pattern}`).not.toBeNull();
  return Number(match![1]);
}

async function auditRecord(
  page: Page,
  action: string,
  targetType: string,
  targetLabel: string,
  source: 'WEB_APP' | 'ADMIN' = 'WEB_APP',
): Promise<void> {
  const params = new URLSearchParams({
    action,
    target_type: targetType,
    source,
  });
  await page.goto(`${AUDIT_URL}?${params.toString()}`);
  const row = page.locator('.administration-audit-table tbody tr')
    .filter({ hasText: targetLabel }).first();
  await expect(row, `Missing ${action} audit for ${targetType}: ${targetLabel}`)
    .toBeVisible();
  await expect(row).toContainText(source === 'ADMIN' ? 'Django Admin' : 'Web App');
  await row.getByRole('link', { name: /View audit record/i }).click();
  await expect(page.getByRole('heading', { name: 'Record Summary' })).toBeVisible();
  await expect(page.locator('.administration-audit-detail-grid'))
    .toContainText(targetLabel);
}

async function auditByObjectId(
  page: Page,
  action: string,
  targetType: string,
  targetId: number,
): Promise<void> {
  // For generated objects whose labels do not include the test run name
  // (for example, forum posts and event invitations).
  const params = new URLSearchParams({
    action,
    target_type: targetType,
    source: 'WEB_APP',
  });
  await page.goto(`${AUDIT_URL}?${params.toString()}`);
  const rows = page.locator('.administration-audit-table tbody tr');
  await expect(rows.first()).toBeVisible();
  const count = await rows.count();
  for (let i = 0; i < count; i++) {
    const row = rows.nth(i);
    const detail = await row.getByRole('link', { name: /View audit record/i }).getAttribute('href');
    if (!detail) continue;
    await page.goto(detail);
    const summary = page.locator('.administration-audit-detail-grid');
    if ((await summary.innerText()).includes(String(targetId))) {
      // Inspect labeled Target ID, not a coincidental number in another field.
      const targetValue = page.locator('dt').filter({ hasText: /^Target ID$/ }).locator('xpath=following-sibling::dd[1]');
      if (await targetValue.count() && (await targetValue.innerText()).trim() === String(targetId)) return;
    }
    await page.goBack();
  }
  throw new Error(`Missing ${action} audit for ${targetType} #${targetId} on first filtered page`);
}

async function csrfPost(page: Page, url: string, fields: Record<string, string> = {}): Promise<void> {
  const token = await page.locator('input[name="csrfmiddlewaretoken"]').first().inputValue();
  const response = await page.request.post(url, {
    form: { csrfmiddlewaretoken: token, ...fields },
    maxRedirects: 0,
  });
  expect([302, 303], `${url} responded with ${response.status()}`).toContain(response.status());
}

async function newThread(page: Page, boardId: number, title: string): Promise<number> {
  await page.goto(`/community/boards/${boardId}/threads/create/`);
  await page.locator('#id_title').fill(title);
  await page.locator('#id_body').fill(`${RUN} opening post`);
  await page.getByRole('button', { name: 'Create Thread' }).click();
  return extractId(page.url(), /\/community\/threads\/(\d+)\/$/);
}


async function forumPost(
  page: Page,
  threadId: number,
  body: string,
): Promise<number> {
  await page.goto(`/community/threads/${threadId}/`);

  const form = page.locator('.forum-reply-form');

  await expect(form).toBeVisible();

  await form.locator('textarea[name="body"]').fill(body);

  await form.getByRole('button', {
    name: 'Post Reply',
  }).click();

  await expect(page).toHaveURL(
    new RegExp(`/community/threads/${threadId}/#post-\\d+$`)
  );

  return extractId(
    page.url(),
    /#post-(\d+)$/,
  );
}


async function selectMember(page: Page, selector: string): Promise<string> {
  const option = page.locator(`${selector} option`).filter({ hasText: USERNAME }).first();
  await expect(option).toHaveCount(1);
  const value = await option.getAttribute('value');
  expect(value).toBeTruthy();
  return value!;
}

test.describe('Audit verification suite 2 — complementary producers', () => {
  test.describe.configure({ mode: 'serial' });
  test.use({ storageState: 'playwright/.auth/suTest.json' });

  test('Tavern — create isolated category and two boards', async ({ page }) => {
    data.categoryName = `${RUN} Category`;
    await page.goto('/community/categories/create/');
    await page.locator('#id_name').fill(data.categoryName);
    await page.locator('main form button[type="submit"]').click();
    const section = page.locator('[id^="category-"]')
      .filter({ hasText: data.categoryName }).first();
    data.categoryId = extractId((await section.getAttribute('id'))!, /^category-(\d+)$/);
    await auditRecord(page, 'CREATE', 'forum category', data.categoryName);

    for (let i = 1; i <= 2; i++) {
      await page.goto(`/community/categories/${data.categoryId}/boards/create/`);
      const name = `${RUN} Board ${i}`;
      await page.locator('#id_name').fill(name);
      await page.locator('#id_thread_creation_policy').selectOption('OPEN');
      await page.getByRole('button', { name: 'Create Board' }).click();
      const boardId = extractId(page.url(), /\/community\/boards\/(\d+)\/$/);
      if (i === 1) { data.boardId = boardId; data.boardName = name; }
      else data.secondBoardId = boardId;
      await auditRecord(page, 'CREATE', 'forum board', name);
    }
  });

  test('Tavern — board UPDATE', async ({ page }) => {
    await page.goto(`/community/boards/${data.boardId}/edit/`);
    await page.locator('#id_description').fill(`${RUN} board changed`);
    await page.getByRole('button', { name: 'Save Changes' }).click();
    await auditRecord(page, 'UPDATE', 'forum board', data.boardName!);
  });

  test('Tavern — board ARCHIVE', async ({ page }) => {
    await page.goto(`/community/boards/${data.boardId}/`);
    await csrfPost(page, `/community/boards/${data.boardId}/archive/`);
    await auditRecord(page, 'ARCHIVE', 'forum board', data.boardName!);
  });

  test('Tavern — board RESTORE', async ({ page }) => {
    await page.goto('/community/?archived=1');
    await csrfPost(page, `/community/boards/${data.boardId}/restore/`);
    await auditRecord(page, 'RESTORE', 'forum board', data.boardName!);
  });

  test('Tavern — create disposable threads', async ({ page }) => {
    data.threadTitle = `${RUN} Main Thread`;
    data.threadId = await newThread(page, data.boardId!, data.threadTitle);
    await auditRecord(page, 'CREATE', 'forum thread', data.threadTitle);
    data.secondThreadId = await newThread(page, data.secondBoardId!, `${RUN} Merge Source`);
    await auditRecord(page, 'CREATE', 'forum thread', `${RUN} Merge Source`);
    data.splitSourceId = await newThread(page, data.boardId!, `${RUN} Split Source`);
    await auditRecord(page, 'CREATE', 'forum thread', `${RUN} Split Source`);
  });

  test('Tavern — thread UPDATE', async ({ page }) => {
    await page.goto(`/community/threads/${data.threadId}/edit/`);
    await page.locator('#id_title').fill(`${RUN} Main Thread Edited`);
    data.threadTitle = `${RUN} Main Thread Edited`;
    await page.getByRole('button', { name: 'Save Changes' }).click();
    await auditRecord(page, 'UPDATE', 'forum thread', data.threadTitle);
  });

  test('Tavern — thread MOVE to second board', async ({ page }) => {
    await page.goto(`/community/threads/${data.threadId}/move/`);
    await page.locator('#id_destination_board').selectOption(String(data.secondBoardId));
    await page.locator('main form button[type="submit"]').click();
    await auditRecord(page, 'MOVE', 'forum thread', data.threadTitle!);
  });

  test('Tavern — thread MERGE (disposable source into edited thread)', async ({ page }) => {
    await page.goto(`/community/threads/${data.secondThreadId}/merge/`);
    await page.locator('#id_destination_thread').selectOption(String(data.threadId));
    await page.locator('main form button[type="submit"]').click();
    await auditRecord(page, 'MERGE', 'forum thread', `${RUN} Merge Source`);
    await auditRecord(page, 'MERGE', 'forum thread', data.threadTitle!);
  });

  test('Tavern — create an additional post for split, edit and archive tests', async ({ page }) => {
    data.splitPostId = await forumPost(page, data.splitSourceId!, `${RUN} split candidate`);
    await auditByObjectId(page, 'CREATE', 'forum post', data.splitPostId);
    data.postId = await forumPost(page, data.threadId!, `${RUN} edit candidate`);
    await auditByObjectId(page, 'CREATE', 'forum post', data.postId);
  });

  test('Tavern — post UPDATE', async ({ page }) => {
    await page.goto(`/community/posts/${data.postId}/edit/`);
    await page.locator('#id_body').fill(`${RUN} post edited`);
    await page.locator('main form button[type="submit"]').last().click();
    await auditByObjectId(page, 'UPDATE', 'forum post', data.postId!);
  });

  test('Tavern — post ARCHIVE', async ({ page }) => {
    await page.goto(`/community/threads/${data.threadId}/`);
    await csrfPost(page, `/community/posts/${data.postId}/archive/`);
    await auditByObjectId(page, 'ARCHIVE', 'forum post', data.postId!);
  });

  test('Tavern — post RESTORE', async ({ page }) => {
    await page.goto(`/community/threads/${data.threadId}/?archived=1`);
    await csrfPost(page, `/community/posts/${data.postId}/restore/`);
    await auditByObjectId(page, 'RESTORE', 'forum post', data.postId!);
  });

  test('Tavern — thread SPLIT', async ({ page }) => {
    const splitTitle = `${RUN} Split Result`;
    await page.goto(`/community/threads/${data.splitSourceId}/split/`);
    await page.locator('#id_title').fill(splitTitle);
    await page.locator('#id_destination_board').selectOption(String(data.secondBoardId));
    await page.locator('#id_posts').selectOption([String(data.splitPostId)]);
    await page.locator('main form button[type="submit"]').click();
    await auditRecord(page, 'SPLIT', 'forum thread', `${RUN} Split Source`);
    await auditRecord(page, 'CREATE', 'forum thread', splitTitle);
    await auditByObjectId(page, 'MOVE', 'forum post', data.splitPostId!);
  });

  test('Messaging — CREATE group conversation', async ({ page }) => {
    await page.goto('/messages/');
    const title = `${RUN} Group`;
    const form = page.locator('form[data-conversation-form]');
    const token = await form.locator('input[name="csrfmiddlewaretoken"]').inputValue();
    const total = await form.locator('input[name="targets-TOTAL_FORMS"]').inputValue();
    const initial = await form.locator('input[name="targets-INITIAL_FORMS"]').inputValue();
    const classOptions = form.locator('select[name="targets-0-citizenship_class"] option[value]:not([value=""])');
    test.skip(await classOptions.count() === 0, 'No organizational citizenship class available to target the group');
    const citizenshipClass = (await classOptions.first().getAttribute('value'))!;
    const response = await page.request.post('/messages/create/', {
      maxRedirects: 0,
      form: {
        csrfmiddlewaretoken: token,
        conversation_type: 'GROUP',
        title,
        'targets-TOTAL_FORMS': total,
        'targets-INITIAL_FORMS': initial,
        'targets-MIN_NUM_FORMS': '0',
        'targets-MAX_NUM_FORMS': '1000',
        'targets-0-citizenship_class': citizenshipClass,
      },
    });
    expect([302, 303], `Group creation returned ${response.status()}`).toContain(response.status());
    const redirect = response.headers()['location'] || '';
    if (/\/messages\/\d+\/$/.test(redirect)) {
      data.groupConversationId = extractId(redirect, /\/messages\/(\d+)\/$/);
    }
    await auditRecord(page, 'CREATE', 'conversation', title);
  });

  test('Actions — create targeted Action and ASSIGN a member', async ({ page }) => {
    data.actionTitle = `${RUN} Targeted Action`;
    await page.goto('/actions/create/');
    await page.locator('#id_title').fill(data.actionTitle);
    const member = await selectMember(page, 'select[name="targets-0-user"]');
    data.memberId = member;
    await page.locator('select[name="targets-0-user"]').selectOption(member);
    await page.getByRole('button', { name: 'Save Action' }).click();
    data.actionId = extractId(page.url(), /\/actions\/manage\/(\d+)\/$/);
    await auditRecord(page, 'CREATE', 'Action', data.actionTitle);
    await auditRecord(page, 'CREATE', 'ActionTarget', data.actionTitle);
    await auditRecord(page, 'ASSIGN', 'ActionAssignment', data.actionTitle);
  });

  test('Actions — REMOVE member assignment', async ({ page }) => {
    await page.goto(`/actions/manage/${data.actionId}/edit/`);
    const target = page.locator(`select[name="targets-0-user"]`);
    await expect(target).toHaveValue(data.memberId!);
    await page.locator('[data-action-target-row]')
      .filter({
        has: page.locator('select[name="targets-0-user"]'),
      })
      .locator('[data-remove-action-target]')
      .click();
    await page.getByRole('button', { name: 'Save Action' }).click();
    await auditRecord(page, 'REMOVE', 'ActionAssignment', data.actionTitle!);
    await auditRecord(page, 'DELETE', 'ActionTarget', data.actionTitle!);
  });

  test('Actions — re-ASSIGN member', async ({ page }) => {
    await page.goto(`/actions/manage/${data.actionId}/edit/`);
    const select = page.locator('select[name^="targets-"][name$="-user"]').first();
    await expect(select).toBeVisible();
    await select.selectOption(data.memberId!);
    await page.getByRole('button', { name: 'Save Action' }).click();
    await auditRecord(page, 'ASSIGN', 'ActionAssignment', data.actionTitle!);
  });

  test('Events — create disposable event with invitation to testuser01', async ({ page }) => {
    data.eventTitle = `${RUN} Invited Event`;
    await page.goto('/events/create/');
    await page.locator('#id_title').fill(data.eventTitle);
    await page.locator('#id_start_at').fill('2027-06-04T12:00');
    await page.locator('#id_end_at').fill('2027-06-04T13:00');
    await page.locator('#id_visibility').selectOption('MEMBERS');
    const userSelect = page.locator('select[name="invitation-0-user"]');
    data.memberId = await selectMember(page, 'select[name="invitation-0-user"]');
    await userSelect.selectOption(data.memberId);
    await page.getByRole('button', { name: 'Save Event' }).click();
    data.eventId = extractId(page.url(), /\/events\/(\d+)\/$/);
    await auditRecord(page, 'CREATE', 'event', data.eventTitle);
    await auditRecord(page, 'ASSIGN', 'EventInvitation', data.eventTitle);
  });

  test('Events — REMOVE invitation', async ({ page }) => {
    await page.goto(`/events/${data.eventId}/edit/`);
    const target = page.locator('select[name^="invitation-"][name$="-user"]')
      .filter({ has: page.locator(`option[value="${data.memberId}"]:checked`) }).first();
    await expect(target).toBeVisible();
    const name = await target.getAttribute('name');
    const index = name!.match(/^invitation-(\d+)-user$/)![1];
    const deleteCheckbox = page.locator(
      `input[name="invitation-${index}-DELETE"]`
    );
    await deleteCheckbox.evaluate((checkbox: HTMLInputElement) => {
      checkbox.checked = true;
      checkbox.dispatchEvent(
        new Event('change', { bubbles: true })
      );
    });
    await expect(deleteCheckbox).toBeChecked();
    await page.getByRole('button', { name: 'Save Event' }).click();
    await auditRecord(page, 'REMOVE', 'EventInvitation', data.eventTitle!);
  });

  test('Events — re-ASSIGN invitation', async ({ page }) => {
    await page.goto(`/events/${data.eventId}/edit/`);
    // Use the new blank target row rather than reusing a deleted form row.
    const blank = page.locator('select[name^="invitation-"][name$="-user"]')
      .filter({ has: page.locator('option[value=""]:checked') }).first();
    await expect(blank).toBeVisible();
    await blank.selectOption(data.memberId!);
    await page.getByRole('button', { name: 'Save Event' }).click();
    await auditRecord(page, 'ASSIGN', 'EventInvitation', data.eventTitle!);
  });

  test('Voting — create a draft with options and an eligibility target', async ({ page }) => {
    data.voteTitle = `${RUN} Openable Vote`;
    await page.goto('/votes/manage/create/');
    await page.locator('#id_title').fill(data.voteTitle);
    await page.locator('select[name="approval_rule"]').selectOption('SIMPLE_MAJORITY');
    await page.locator('input[name="options-0-label"]').fill(`${RUN} Yes`);
    await page.locator('input[name="options-1-label"]').fill(`${RUN} No`);
    const voter = await selectMember(page, 'select[name="targets-0-user"]');
    await page.locator('select[name="targets-0-user"]').selectOption(voter);
    await page.getByRole('button', { name: 'Save as Draft' }).click();
    data.voteId = extractId(page.url(), /\/votes\/manage\/(\d+)\/$/);
    await auditRecord(page, 'CREATE', 'Vote', data.voteTitle);
    await auditRecord(page, 'CREATE', 'VoteOption', `${RUN} Yes`);
    await auditRecord(page, 'CREATE', 'VoteEligibilityTarget', data.voteTitle);
  });

  test('Voting — OPEN and freeze eligible users', async ({ page }) => {
    await page.goto(`/votes/manage/${data.voteId}/`);
    await csrfPost(page, `/votes/manage/${data.voteId}/open/`);
    await auditRecord(page, 'UPDATE', 'Vote', data.voteTitle!);
    await auditRecord(page, 'ASSIGN', 'VoteEligibleUser', data.voteTitle!);
  });

  test('Voting — CLOSE vote', async ({ page }) => {
    await page.goto(`/votes/manage/${data.voteId}/`);
    await csrfPost(page, `/votes/manage/${data.voteId}/close/`);
    await auditRecord(page, 'UPDATE', 'Vote', data.voteTitle!);
  });
});
