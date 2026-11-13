import { execFileSync } from 'node:child_process';
import {
  test,
  expect,
  type Browser,
  type Page,
} from '@playwright/test';

const MEMBER_STATE = 'playwright/.auth/testuser01.json';
const OTHER_STATE = 'playwright/.auth/testuser02.json';
const NOTIFICATIONS_URL = '/notifications/';
const FEED_URL = '/accounts/my-eldvatten/?section=notifications';
const SETTINGS_URL = '/notifications/settings/';
const RUN = `PW Notifications ${Date.now()}`;

type Fixture = {
  unread: number;
  read: number;
  message: number;
  noTarget: number;
  other: number;
  baseline: { id: number; is_read: boolean; read_at: string | null }[];
  pushPromptSeen: boolean;
};

let fixture: Fixture;

// These tests alter a disposable development database. Never run against production.
function requireDisposableDatabase(): void {
  if (process.env.E2E_NOTIFICATIONS_MUTATIONS !== '1') {
    throw new Error(
      'Set E2E_NOTIFICATIONS_MUTATIONS=1 only for a disposable DEBUG=True database.',
    );
  }
}

function django(script: string): string {
  requireDisposableDatabase();
  return execFileSync('docker', [
    'compose', 'exec', '-T', 'web', 'python', 'manage.py', 'shell', '-c',
    `from django.conf import settings\nif not settings.DEBUG: raise RuntimeError('Notifications E2E requires DEBUG=True')\n${script}`,
  ], { encoding: 'utf8', timeout: 30_000 }).trim();
}

function djangoJson<T>(script: string): T {
  const output = django(script);
  const line = output.split(/\r?\n/).find((part) => part.startsWith('E2E_JSON:'));
  if (!line) throw new Error(`Missing fixture output: ${output}`);
  return JSON.parse(line.slice('E2E_JSON:'.length)) as T;
}

function notification(title: string) {
  return `${RUN} ${title}`;
}

async function useMember(browser: Browser, state = MEMBER_STATE): Promise<{
  context: BrowserContext;
  page: Page;
}> {
  const context = await browser.newContext({ storageState: state });
  return { context, page: await context.newPage() };
}

// Browser fetch rather than Playwright APIRequestContext: includes same-origin CSRF cookie.
async function postJson(page: Page, url: string, data: unknown) {
  return page.evaluate(async ({ url, data }) => {
    const csrfCookie = document.cookie.split(';').map((v) => v.trim())
      .find((v) => v.startsWith('csrftoken='));
    const csrfToken = csrfCookie ? decodeURIComponent(csrfCookie.slice(10)) : '';
    const response = await fetch(url, {
      method: 'POST',
      credentials: 'same-origin',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': csrfToken,
      },
      body: JSON.stringify(data),
    });
    const contentType = response.headers.get('content-type') || '';
    const body = contentType.includes('application/json')
      ? await response.json()
      : await response.text();

    return { status: response.status, body };
  }, { url, data });
}

async function postBrowser(page: Page, url: string): Promise<{ status: number; location: string | null }> {
  return page.evaluate(async (url) => {
    const token = document.cookie.split(';').map((value) => value.trim())
      .find((value) => value.startsWith('csrftoken='));
    const response = await fetch(url, {
      method: 'POST',
      credentials: 'same-origin',
      redirect: 'manual',
      headers: { 'X-CSRFToken': token ? decodeURIComponent(token.slice(10)) : '' },
    });
    return { status: response.status, location: response.headers.get('Location') };
  }, url);
}

function notificationFeedArticle(page: Page, title: string) {
  return page.locator('.notification-item').filter({ hasText: title });
}

async function resetFixtures(): Promise<void> {
  const baseline = JSON.stringify(fixture.baseline);
  django(`import json
from datetime import datetime
from notifications.models import Notification
baseline = json.loads(${JSON.stringify(baseline)})
for record in baseline:
    read_at = datetime.fromisoformat(record['read_at']) if record['read_at'] else None
    Notification.objects.filter(pk=record['id']).update(is_read=record['is_read'], read_at=read_at)
Notification.objects.filter(pk__in=${JSON.stringify([fixture.unread, fixture.read, fixture.message, fixture.noTarget, fixture.other])}).update(is_read=False, read_at=None)
Notification.objects.filter(pk=${fixture.read}).update(is_read=True)`);
}

test.describe('Notifications — authenticated UI and Web Push acceptance', () => {
  test.describe.configure({ mode: 'serial' });
  test.use({ storageState: MEMBER_STATE, serviceWorkers: 'allow' });

  test.beforeAll(() => {
    fixture = djangoJson<Fixture>(`
import json
from django.contrib.auth import get_user_model
from notifications.models import Notification
User = get_user_model()
member = User.objects.get(username='testuser01')
other = User.objects.get(username='testuser02')
run = ${JSON.stringify(RUN)}
baseline = [dict(id=n.pk, is_read=n.is_read, read_at=n.read_at.isoformat() if n.read_at else None) for n in Notification.objects.filter(user=member)]
entries = {
    'unread': Notification.objects.create(user=member, notification_type='EVENT', title=run + ' Event', message='An upcoming gathering', target_url='/events/'),
    'read': Notification.objects.create(user=member, notification_type='ACTION', title=run + ' Action', message='Already reviewed', is_read=True),
    'message': Notification.objects.create(user=member, notification_type='MESSAGE', title=run + ' Message', message='A new message', target_url='/messages/'),
    'noTarget': Notification.objects.create(user=member, notification_type='SYSTEM', title=run + ' Notice', message='No destination'),
    'other': Notification.objects.create(user=other, notification_type='SYSTEM', title=run + ' Other Private', message='Must stay private'),
}
print('E2E_JSON:' + json.dumps({**{key: value.pk for key, value in entries.items()}, 'baseline': baseline, 'pushPromptSeen': member.push_prompt_seen}))`);
  });

  test.beforeEach(async () => {
    await resetFixtures();
  });

  test.afterAll(() => {
    if (!fixture) return;
    django(`import json\nfrom datetime import datetime\nfrom notifications.models import Notification, PushSubscription\nNotification.objects.filter(pk__in=${JSON.stringify([fixture.unread, fixture.read, fixture.message, fixture.noTarget, fixture.other])}).delete()\nPushSubscription.objects.filter(user__username='testuser01', endpoint__startswith=${JSON.stringify(`https://example.invalid/${RUN}`)}).delete()\nfrom django.contrib.auth import get_user_model\nget_user_model().objects.filter(username='testuser01').update(push_prompt_seen=${fixture.pushPromptSeen ? 'True' : 'False'})\nbaseline = json.loads(${JSON.stringify(JSON.stringify(fixture.baseline))})\nfor record in baseline:\n    read_at = datetime.fromisoformat(record['read_at']) if record['read_at'] else None\n    Notification.objects.filter(pk=record['id']).update(is_read=record['is_read'], read_at=read_at)`);
  });

  test('legacy Notifications URL redirects to the integrated My EldVatten feed', async ({ page }) => {
    await page.goto(NOTIFICATIONS_URL);
    await expect(page).toHaveURL(/\/accounts\/my-eldvatten\/\?section=notifications/);
    await expect(page.getByRole('heading', { name: 'Notifications', exact: true })).toBeVisible();
    await expect(notificationFeedArticle(page, notification('Event'))).toBeVisible();
    await expect(notificationFeedArticle(page, notification('Action'))).toBeVisible();
    await expect(page.locator('.notification-feed')).not.toContainText(notification('Other Private'));
    const countText = await page.locator('.notification-unread-count').innerText();
    expect(Number(countText.match(/(\d+)\s+unread/)?.[1])).toBeGreaterThanOrEqual(3);
  });

  test('anonymous visitors are redirected to login for notification surfaces', async ({ browser }) => {
    const context = await browser.newContext({
      storageState: { cookies: [], origins: [] },
      serviceWorkers: 'block',
    });
    try {
      expect(await context.cookies()).toHaveLength(0);
      for (const url of [NOTIFICATIONS_URL, SETTINGS_URL, FEED_URL]) {
        const response = await context.request.get(url, {
          maxRedirects: 0,
        });
        expect(response.status(), `Anonymous GET ${url}`).toBe(302);
        expect(response.headers().location, `Anonymous GET ${url}`)
          .toContain('/accounts/login/');
      }
    } finally {
      await context.close();
    }
  });

  test('another member cannot see or modify owned notification', async ({ browser }) => {
    const { context, page } = await useMember(browser, OTHER_STATE);
    try {
      await page.goto(FEED_URL);
      await expect(page.locator('.notification-feed')).toContainText(notification('Other Private'));
      await expect(page.locator('body')).not.toContainText(notification('Event'));
      const opened = await page.request.get(
        `/notifications/${fixture.unread}/open/`,
        { maxRedirects: 0 },
      );
      expect(opened.status()).toBe(404);

      // Use the real browser's CSRF cookie to reach Django's ownership check,
      // rather than accidentally testing the CSRF middleware.
      for (const suffix of ['read', 'unread']) {
        const result = await postBrowser(page, `/notifications/${fixture.unread}/${suffix}/`);
        expect(result.status, `Unauthorized ${suffix}`).toBe(404);
      }
    } finally {
      await context.close();
    }
  });

  test('opening a notification from the feed marks it read', async ({ page }) => {
    await page.goto(FEED_URL);
    const item = notificationFeedArticle(page, notification('Event'));
    await expect(item).toHaveClass(/\bunread\b/);
    await item.locator('a.notification-item-open').click();
    await expect(page).toHaveURL(/\/events\//);
    await page.goto(FEED_URL);
    await expect(notificationFeedArticle(page, notification('Event'))).not.toHaveClass(/\bunread\b/);
  });

  test('marking a notification unread restores unread styling', async ({ page }) => {
    await page.goto(FEED_URL);
    await notificationFeedArticle(page, notification('Action'))
      .getByRole('button', { name: 'Mark Unread' }).click();
    await expect(notificationFeedArticle(page, notification('Action'))).toHaveClass(/\bunread\b/);
  });

  test('read-state changes do not occur through GET', async ({ page }) => {
    await page.goto(FEED_URL);
    for (const url of [
      `/notifications/${fixture.unread}/read/`,
      `/notifications/${fixture.read}/unread/`,
      '/notifications/read-all/',
    ]) {
      const response = await page.request.get(url, { maxRedirects: 0 });
      expect(response.status()).toBe(302);
    }
    await page.reload();
    await expect(notificationFeedArticle(page, notification('Event'))).toHaveClass(/\bunread\b/);
    await expect(notificationFeedArticle(page, notification('Action'))).not.toHaveClass(/\bunread\b/);
  });

  test('mark all read preserves another member’s notifications', async ({ page, browser }) => {
    await page.goto(FEED_URL);
    await page.getByRole('button', { name: 'Mark All Read' }).click();
    await expect(page.locator('.notification-unread-count')).toContainText('0 unread');
    const { context, page: other } = await useMember(browser, OTHER_STATE);
    try {
      await other.goto(FEED_URL);
      await expect(notificationFeedArticle(other, notification('Other Private'))).toHaveClass(/\bunread\b/);
    } finally {
      await context.close();
    }
  });

  test('opening linked notification follows its destination and persists read state', async ({ page }) => {
    await page.goto(FEED_URL);
    await notificationFeedArticle(page, notification('Event')).locator('a.notification-item-open').click();
    await expect(page).toHaveURL(/\/events\//);
    await page.goto(FEED_URL);
    await expect(notificationFeedArticle(page, notification('Event'))).not.toHaveClass(/\bunread\b/);
  });

  test('open notification rejects an external return URL', async ({ page }) => {
    await page.goto(FEED_URL);
    await page.goto(`/notifications/${fixture.noTarget}/open/?next=${encodeURIComponent('https://example.invalid/phishing')}`);
    await expect(page).toHaveURL(/\/accounts\/my-eldvatten\/\?section=notifications/);
    await expect(notificationFeedArticle(page, notification('Notice'))).not.toHaveClass(/\bunread\b/);
  });

  test('notification without a target remains accessible within My EldVatten', async ({ page }) => {
    await page.goto(FEED_URL);
    const item = notificationFeedArticle(page, notification('Notice'));
    await expect(item).toBeVisible();
    await item.locator('a.notification-item-open').click();
    await expect(page).toHaveURL(/\/accounts\/my-eldvatten\/\?section=notifications/);
    await expect(notificationFeedArticle(page, notification('Notice'))).not.toHaveClass(/\bunread\b/);
  });

  test('My EldVatten feed shows notification types, counts and current member data', async ({ page }) => {
    await page.goto(FEED_URL);
    await expect(page.getByRole('heading', { name: 'Notifications', exact: true })).toBeVisible();
    await expect(notificationFeedArticle(page, notification('Event'))).toBeVisible();
    await expect(notificationFeedArticle(page, notification('Message'))).toBeVisible();
    await expect(page.locator('.notification-feed')).not.toContainText(notification('Other Private'));
    const count = Number((await page.locator('.notification-unread-count').innerText()).match(/(\d+)\s+unread/)?.[1]);
    expect(count).toBeGreaterThanOrEqual(3);
  });

  test('My EldVatten unread and read filters separate states', async ({ page }) => {
    await page.goto(`${FEED_URL}&state=unread`);
    await expect(notificationFeedArticle(page, notification('Event'))).toBeVisible();
    await expect(notificationFeedArticle(page, notification('Action'))).toHaveCount(0);
    await page.goto(`${FEED_URL}&state=read`);
    await expect(notificationFeedArticle(page, notification('Action'))).toBeVisible();
    await expect(notificationFeedArticle(page, notification('Event'))).toHaveCount(0);
  });

  test('My EldVatten type filters show matching notifications only', async ({ page }) => {
    await page.goto(`${FEED_URL}&type=MESSAGE`);
    await expect(notificationFeedArticle(page, notification('Message'))).toBeVisible();
    await expect(notificationFeedArticle(page, notification('Event'))).toHaveCount(0);
    await expect(page.locator('.notification-filter-link.active').filter({ hasText: 'Message' })).toHaveCount(1);
  });

  test('My EldVatten link opens destination and returns with read state', async ({ page }) => {
    await page.goto(FEED_URL);
    await notificationFeedArticle(page, notification('Event')).locator('a.notification-item-open').click();
    await expect(page).toHaveURL(/\/events\//);
    await page.goto(FEED_URL);
    await expect(notificationFeedArticle(page, notification('Event'))).not.toHaveClass(/\bunread\b/);
  });

  test('My EldVatten mark unread and mark all read preserve filter navigation', async ({ page }) => {
    await page.goto(`${FEED_URL}&state=read&type=ACTION`);
    await notificationFeedArticle(page, notification('Action')).getByRole('button', { name: 'Mark Unread' }).click();
    await expect(page).toHaveURL(/state=read/);
    await expect(notificationFeedArticle(page, notification('Action'))).toHaveCount(0);
    await page.goto(FEED_URL);
    await page.getByRole('button', { name: 'Mark All Read' }).click();
    await expect(page.locator('.notification-unread-count')).toContainText('0 unread');
  });

  test('notification preferences save and reload with category-specific choices', async ({ page }) => {
    await page.goto(SETTINGS_URL);
    await expect(page.getByRole('heading', {
      name: 'Notification Settings', exact: true,
    })).toBeVisible();
    const setting = page.locator('#id_message_push');
    await expect(setting).toBeVisible();
    const before = await setting.isChecked();
    try {
      await setting.setChecked(!before);
      await page.getByRole('button', { name: 'Save notification settings' }).click();
      await expect(page).toHaveURL(/\/notifications\/settings\//);
      await expect(page.locator('#id_message_push')).toBeChecked({ checked: !before });
    } finally {
      // Restore the preference even if an assertion above fails.
      await page.goto(SETTINGS_URL);
      await page.locator('#id_message_push').setChecked(before);
      await page.getByRole('button', { name: 'Save notification settings' }).click();
    }
  });

  test('preference update endpoint requires POST', async ({ page }) => {
    await page.goto(SETTINGS_URL);
    const response = await page.request.get('/notifications/settings/update/');
    expect(response.status()).toBe(405);
  });

  test('settings page explains browser notification state without a subscription', async ({ browser }) => {
    const { context, page } = await useMember(browser);
    try {
      await page.goto(SETTINGS_URL);
      await expect(page.locator('#device-push-status'))
        .not.toContainText('Checking notification status...');
      await expect(page.locator('#device-push-status'))
        .toContainText('not enabled on this device');
      await expect(page.locator('#enable-device-push-button')).toBeVisible();
      await expect(page.locator('#disable-device-push-button')).toBeHidden();
    } finally {
      await context.close();
    }
  });

  test('push public key is available to authenticated browser', async ({ page }) => {
    await page.goto(SETTINGS_URL);
    const response = await page.request.get('/notifications/push/public-key/');
    expect(response.status()).toBe(200);
    const json = await response.json();
    expect(json).toHaveProperty('public_key');
  });

  test('push subscription HTTP endpoints reject invalid payloads', async ({ page }) => {
    await page.goto(SETTINGS_URL);
    const invalid = await postJson(page, '/notifications/push/subscribe/', { endpoint: '' });
    expect(invalid.status).toBe(400);
    const pause = await postJson(page, '/notifications/push/pause/', { endpoint: 'abc', hours: 25 });
    expect(pause.status).toBe(400);
    const enabled = await postJson(page, '/notifications/push/enabled/', { endpoint: 'abc', enabled: 'yes' });
    expect(enabled.status).toBe(400);
    const active = await postJson(page, '/notifications/push/active/', { endpoint: 'abc', active: 'yes' });
    expect(active.status).toBe(400);
  });

  test('push subscription API registers, updates, disables and reactivates an isolated device', async ({ page }) => {
    await page.goto(SETTINGS_URL);
    const endpoint = `https://example.invalid/${RUN}/device`;
    const subscription = {
      endpoint,
      keys: { p256dh: 'isolated-public-key', auth: 'isolated-auth-key' },
      device_name: 'Playwright notification acceptance device',
    };
    const created = await postJson(page, '/notifications/push/subscribe/', subscription);
    expect(created.status).toBe(200);
    expect(created.body).toMatchObject({ success: true, created: true });
    const repeated = await postJson(page, '/notifications/push/subscribe/', subscription);
    expect(repeated.body).toMatchObject({ success: true, created: false });
    const status = await postJson(page, '/notifications/push/status/', { endpoint });
    expect(status.body).toMatchObject({ registered: true, enabled: true, active: true });
    const disabled = await postJson(page, '/notifications/push/enabled/', { endpoint, enabled: false });
    expect(disabled.body).toMatchObject({ enabled: false, active: false });
    const blockedActivation = await postJson(page, '/notifications/push/active/', { endpoint, active: true });
    expect(blockedActivation.status).toBe(409);
    const restored = await postJson(page, '/notifications/push/enabled/', { endpoint, enabled: true });
    expect(restored.body).toMatchObject({ enabled: true, active: true });
    const paused = await postJson(page, '/notifications/push/pause/', { endpoint, hours: 2 });
    expect(paused.body.success).toBe(true);
    const pausedStatus = await postJson(page, '/notifications/push/status/', { endpoint });
    expect(pausedStatus.body.paused).toBe(true);
    const reset = await postJson(page, '/notifications/push/pause/reset/', { endpoint });
    expect(reset.body.success).toBe(true);
    const finalStatus = await postJson(page, '/notifications/push/status/', { endpoint });
    expect(finalStatus.body.paused).toBe(false);
  });

  test('push API isolates subscriptions between members', async ({ browser }) => {
    const { context, page } = await useMember(browser, OTHER_STATE);
    try {
      await page.goto(SETTINGS_URL);
      const endpoint = `https://example.invalid/${RUN}/device`;
      const status = await postJson(page, '/notifications/push/status/', { endpoint });
      expect(status.body.registered).toBe(false);
      const change = await postJson(page, '/notifications/push/enabled/', { endpoint, enabled: false });
      expect(change.status).toBe(404);
    } finally {
      await context.close();
    }
  });

  test('notification settings and push API endpoints enforce login', async ({ browser }) => {
    const context = await browser.newContext({
      storageState: { cookies: [], origins: [] },
      serviceWorkers: 'block',
    });
    const page = await context.newPage();
    try {
      const settings = await page.request.get(SETTINGS_URL, { maxRedirects: 0 });
      expect(settings.status()).toBe(302);
      expect(settings.headers().location).toContain('/accounts/login/');
      // Django's CSRF middleware rejects an anonymous POST without a token
      // before the login_required decorator gets control.
      const api = await page.request.post('/notifications/push/status/', {
        data: { endpoint: 'test' },
        maxRedirects: 0,
      });
      expect(api.status()).toBe(403);

      // With a valid CSRF token, the same anonymous API request must
      // reach the authentication check and redirect to login.
      await page.goto('/accounts/login/');
      const csrfToken = await page.locator('input[name=csrfmiddlewaretoken]').inputValue();
      const authenticatedGuard = await page.request.post('/notifications/push/status/', {
        data: { endpoint: 'test' },
        headers: { 'X-CSRFToken': csrfToken },
        maxRedirects: 0,
      });
      expect(authenticatedGuard.status()).toBe(302);
      expect(authenticatedGuard.headers().location).toContain('/accounts/login/');
    } finally {
      await context.close();
    }
  });

  test('Chromium notification-click handler requests destination navigation and focus', async ({ page, browserName }) => {
    test.skip(browserName !== 'chromium', 'Worker event inspection is Chromium-only.');
    await page.context().grantPermissions(['notifications']);
    await page.goto(SETTINGS_URL);
    await page.evaluate(async () => {
      await navigator.serviceWorker.register('/service-worker.js', { scope: '/' });
      await navigator.serviceWorker.ready;
    });
    await expect.poll(() => page.context().serviceWorkers().length).toBeGreaterThan(0);
    const worker = page.context().serviceWorkers()[0];

    // A manually dispatched event has no trusted user activation, so Chromium
    // rejects an actual WindowClient.focus(). Stub only that privileged browser
    // boundary while running EldVatten's real notificationclick event handler.
    const result = await worker.evaluate(async () => {
      const clientRegistry = (self as any).clients as { matchAll: (...args: any[]) => Promise<any[]> };
      const originalMatchAll = clientRegistry.matchAll;
      const navigations: string[] = [];
      let focusRequested = false;
      let notificationClosed = false;
      const pending: Promise<unknown>[] = [];

      try {
        clientRegistry.matchAll = (async () => [{
          navigate: async (url: string) => {
            navigations.push(url);
          },
          focus: async () => {
            focusRequested = true;
          },
        }]);

        const event = new Event('notificationclick');
        Object.defineProperty(event, 'notification', {
          value: {
            data: { target_url: '/events/' },
            close: () => { notificationClosed = true; },
          },
        });
        Object.defineProperty(event, 'waitUntil', {
          value: (promise: Promise<unknown>) => pending.push(promise),
        });

        self.dispatchEvent(event);
        await Promise.all(pending);
        return { navigations, focusRequested, notificationClosed };
      } finally {
        clientRegistry.matchAll = originalMatchAll;
      }
    });

    expect(result.navigations).toEqual(['/events/']);
    expect(result.focusRequested).toBe(true);
    expect(result.notificationClosed).toBe(true);
  });

  test('Chromium registers and activates EldVatten service worker', async ({ page, browserName }) => {
    test.skip(browserName !== 'chromium', 'Chromium service worker acceptance.');
    await page.context().grantPermissions(['notifications']);
    await page.goto(SETTINGS_URL);
    const scope = await page.evaluate(async () => {
      const registration = await navigator.serviceWorker.register('/service-worker.js', { scope: '/' });
      await navigator.serviceWorker.ready;
      return registration.scope;
    });
    expect(scope).toBe(new URL('/', page.url()).toString());
    await expect.poll(async () => page.context().serviceWorkers().length).toBeGreaterThan(0);
  });

  test('Chromium DevTools delivers a push payload to the real service worker', async ({ page, browserName }) => {
    test.skip(browserName !== 'chromium', 'CDP ServiceWorker.deliverPushMessage is Chromium-only.');
    await page.context().grantPermissions(['notifications']);
    await page.goto(SETTINGS_URL);
    await page.evaluate(async () => {
      await navigator.serviceWorker.register('/service-worker.js', { scope: '/' });
      await navigator.serviceWorker.ready;
    });
    const cdp = await page.context().newCDPSession(page);
    const origin = new URL(page.url()).origin;
    let registrationId: string | undefined;
    const registrations = new Promise<string>((resolve, reject) => {
      const timer = setTimeout(() => reject(new Error('CDP service worker registration not reported')), 10_000);
      cdp.on('ServiceWorker.workerRegistrationUpdated', (event: {
        registrations: { registrationId: string; scopeURL: string; isDeleted: boolean }[];
      }) => {
        const item = event.registrations.find((r) => r.scopeURL === `${origin}/` && !r.isDeleted);
        if (item) {
          clearTimeout(timer);
          resolve(item.registrationId);
        }
      });
    });
    try {
      await cdp.send('ServiceWorker.enable');
      registrationId = await registrations;
      const title = notification('CDP Push');
      await cdp.send('ServiceWorker.deliverPushMessage', {
        origin,
        registrationId,
        data: JSON.stringify({
          title,
          message: 'Browser push event delivered',
          target_url: '/events/',
        }),
      });
      await expect.poll(async () => page.evaluate(async (title) => {
        const registration = await navigator.serviceWorker.ready;
        const notices = await registration.getNotifications();
        return notices.filter((n) => n.title === title).length;
      }, title)).toBe(1);
      const details = await page.evaluate(async (title) => {
        const notices = await (await navigator.serviceWorker.ready).getNotifications();
        const notice = notices.find((n) => n.title === title);
        if (!notice) return null;
        const value = { title: notice.title, body: notice.body, target: notice.data?.target_url };
        notice.close();
        return value;
      }, title);
      expect(details).toEqual({ title, body: 'Browser push event delivered', target: '/events/' });
    } finally {
      await cdp.detach();
    }
  });
});
