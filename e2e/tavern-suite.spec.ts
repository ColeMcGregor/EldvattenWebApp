import { execFileSync } from 'node:child_process';

import {

  test,

  expect,

  type Page,

} from '@playwright/test';

const memberState = 'playwright/.auth/testuser01.json';

const administratorState = 'playwright/.auth/suTest.json';

const tavernUrl = '/community/';

const createdCategories = new Set<string>();

// Mutating browser acceptance tests must run against the disposable development database.

function requireDisposableDatabase() {

  if (process.env.E2E_TAVERN_MUTATIONS !== '1') {

    throw new Error('Set E2E_TAVERN_MUTATIONS=1 to enable database-mutating Tavern tests.');

  }

}

function runDjango(script: string): string {

  requireDisposableDatabase();

  return execFileSync('docker', [

    'compose', 'exec', '-T', 'web', 'python', 'manage.py', 'shell', '-c',

    `from django.conf import settings\nif not settings.DEBUG: raise RuntimeError('Tavern browser tests require DEBUG=True')\n${script}`,

  ], { encoding: 'utf8', timeout: 30000 }).trim();

}

// Remove only categories created by this test. Threads protect their Board,

// so delete descendants in dependency order before removing parent records.

// The cleanup runs after failures too, and never touches existing seed data.

test.afterEach(async () => {

  const names = [...createdCategories];

  createdCategories.clear();

  if (names.length === 0) return;

  const cleanupScript = `from django.db import transaction

from community.models import ForumCategory, ForumBoard, ForumThread

names = ${JSON.stringify(names)}

with transaction.atomic():

    categories = ForumCategory.objects.filter(

        name__in=[value for name in names for value in (name, name + " Edited")]

    )

    boards = ForumBoard.objects.filter(category__in=categories)

    ForumThread.objects.filter(board__in=boards).delete()

    boards.delete()

    categories.delete()`;

  runDjango(cleanupScript);

});

function uniqueName(label: string): string {

  const value = `PW Tavern ${label} ${Date.now()} ${Math.floor(Math.random() * 100000)}`;

  if (label === 'Category') createdCategories.add(value);

  return value;

}

async function openTavern(page: Page) {

  await page.goto(tavernUrl);

  await expect(

    page.getByRole('heading', {

      name: 'The Tavern',

      exact: true,

    })

  ).toBeVisible();

}

async function checkBreadcrumbs(page: Page) {

  const breadcrumbs = page.getByRole('navigation', {

    name: 'Breadcrumb',

  });

  await expect(breadcrumbs).toBeVisible();

  await expect(

    breadcrumbs.getByRole('link', {

      name: 'The Tavern',

    })

  ).toBeVisible();

  return breadcrumbs;

}

async function openFirstVisibleBoard(page: Page) {

  await openTavern(page);

  const boards = page.locator(

    '.forum-board-row .forum-board-heading a'

  );

  expect(

    await boards.count(),

    'At least one visible board is required'

  ).toBeGreaterThan(0);

  const name = (await boards.first().innerText()).trim();

  await boards.first().click();

  await expect(

    page.getByRole('heading', {

      level: 1,

      name,

      exact: true,

    })

  ).toBeVisible();

  return {

    name,

    url: page.url(),

  };

}

async function openFirstVisibleThread(page: Page) {

  await openTavern(page);

  const boardUrls = await page

    .locator('.forum-board-row .forum-board-heading a')

    .evaluateAll(links =>

      links.map(link => (link as HTMLAnchorElement).href)

    );

  for (const boardUrl of boardUrls) {

    await page.goto(boardUrl);

    const threads = page.locator(

      '.forum-thread-row .forum-thread-heading a'

    );

    if (await threads.count() === 0) {

      continue;

    }

    const boardName = (

      await page.locator(

        '.forum-page-heading h1'

      ).innerText()

    ).trim();

    const threadName = (

      await threads.first().innerText()

    ).trim();

    await threads.first().click();

    await expect(

      page.getByRole('heading', {

        level: 1,

        name: threadName,

        exact: true,

      })

    ).toBeVisible();

    return {

      boardName,

      threadName,

      url: page.url(),

    };

  }

  throw new Error(

    'At least one accessible thread is required'

  );

}

async function findWritableBoard(page: Page) {

  await openTavern(page);

  const boardUrls = await page

    .locator('.forum-board-row .forum-board-heading a')

    .evaluateAll(links =>

      links.map(link => (link as HTMLAnchorElement).href)

    );

  for (const boardUrl of boardUrls) {

    await page.goto(boardUrl);

    const create = page.getByRole('link', {

      name: 'Create Thread',

      exact: true,

    });

    if (await create.count()) {

      return boardUrl;

    }

  }

  throw new Error(

    'No board permits this member to create threads'

  );

}

async function submitAndExpectNavigation(

  page: Page,

  buttonName: string

) {

  const previousUrl = page.url();

  await page.getByRole('button', {

    name: buttonName,

    exact: true,

  }).click();

  await expect

    .poll(() => page.url())

    .not.toBe(previousUrl);

}

async function fillAttachment(

  page: Page,

  prefix: string,

  label: string,

  url: string

) {

  await page.locator(

    `#id\\_${prefix}-0-label`

  ).fill(label);

  await page.locator(

    `#id\\_${prefix}-0-url`

  ).fill(url);

  await page.locator(

    `#id\\_${prefix}-0-display_order`

  ).fill('0');

}

async function openPostMenu(

  page: Page,

  postIndex: number

) {

  const post = page.locator(

    '.forum-post'

  ).nth(postIndex);

  await expect(post).toBeVisible();

  await post.locator(

    '.forum-post-menu summary'

  ).click();

  return post;

}

// ============================================================

// Member navigation and reading

// ============================================================

test.describe('Tavern member navigation', () => {

  test.use({

    storageState: memberState,

  });

  test('Member can open The Tavern', async ({ page }) => {

    await openTavern(page);

    await expect(

      page.getByRole('navigation', {

        name: 'EldVatten application navigation',

      })

    ).toBeVisible();

    await expect(

      page.locator('.forum-category-list')

    ).toBeVisible();

    await expect(

      page.locator('.forum-search-form')

    ).toBeVisible();

  });

  test('Member can open boards and use breadcrumbs', async ({ page }) => {

    const board = await openFirstVisibleBoard(page);

    const breadcrumbs = await checkBreadcrumbs(page);

    await expect(

      page.locator('#threads')

    ).toBeVisible();

    await breadcrumbs.getByRole('link', {

      name: 'The Tavern',

    }).click();

    await expect(page).toHaveURL(/\/community\/$/);

    await expect(

      page.locator('.forum-board-heading a', {

        hasText: board.name,

      }).first()

    ).toBeVisible();

  });

  test('Thread breadcrumb returns to its board', async ({ page }) => {

    const thread = await openFirstVisibleThread(page);

    const breadcrumbs = await checkBreadcrumbs(page);

    const boardLink = breadcrumbs.getByRole('link', {

      name: thread.boardName,

      exact: true,

    });

    await expect(boardLink).toHaveAttribute(

      'href',

      /#threads$/

    );

    await boardLink.click();

    await expect(page).toHaveURL(/#threads$/);

    await expect(

      page.locator('#threads')

    ).toBeVisible();

  });

  test('Member can navigate to a post permalink', async ({ page }) => {

    await openFirstVisibleThread(page);

    const post = page.locator('.forum-post').first();

    await expect(post).toBeVisible();

    const permalink = post.locator(

      '.forum-post-number'

    );

    await permalink.click();

    await expect(page).toHaveURL(/#post-\d+$/);

    await expect(post).toBeVisible();

  });

  test('Member can search The Tavern', async ({ page }) => {

    await openTavern(page);

    await page.getByRole('searchbox', {

      name: 'Search The Tavern',

    }).fill('test');

    await submitAndExpectNavigation(page, 'Search');

    await expect(page).toHaveURL(

      /\/community\/search\/\?q=test/

    );

    await expect(

      page.locator('body')

    ).toContainText('test');

  });

  test('Member does not see category management controls', async ({ page }) => {

    await openTavern(page);

    await expect(

      page.getByRole('link', {

        name: 'Create Category',

      })

    ).toHaveCount(0);

    await expect(

      page.locator('.forum-category-actions')

    ).toHaveCount(0);

  });

  test('Member can open the My Drafts screen', async ({ page }) => {

    await page.goto('/community/drafts/');

    await expect(

      page.getByRole('heading', {

        name: 'My Drafts',

        exact: true,

      })

    ).toBeVisible();

    await expect(

      page.getByRole('link', {

        name: 'Return to The Tavern',

      })

    ).toBeVisible();

    await page.getByRole('link', {

      name: 'Return to The Tavern',

    }).click();

    await expect(page).toHaveURL(/\/community\/$/);

  });

  test('Member can follow and unfollow a thread', async ({ page }) => {

    const thread = await openFirstVisibleThread(page);

    const follow = page.getByRole('button', {

      name: 'Follow',

      exact: true,

    });

    const unfollow = page.getByRole('button', {

      name: 'Unfollow',

      exact: true,

    });

    if (await unfollow.count()) {

      await unfollow.click();

      await expect(follow).toBeVisible();

      await follow.click();

      await expect(unfollow).toBeVisible();

    } else {

      await expect(follow).toBeVisible();

      await follow.click();

      await expect(unfollow).toBeVisible();

      await unfollow.click();

      await expect(follow).toBeVisible();

    }

    await expect(page).toHaveURL(

      new RegExp(`/community/threads/\\d+/`)

    );

    expect(thread.threadName.length).toBeGreaterThan(0);

  });

  test('Member can subscribe and unsubscribe from a board', async ({ page }) => {

    await openFirstVisibleBoard(page);

    const subscribe = page.getByRole('button', {

      name: 'Subscribe',

      exact: true,

    });

    const unsubscribe = page.getByRole('button', {

      name: 'Unsubscribe',

      exact: true,

    });

    if (await unsubscribe.count()) {

      await unsubscribe.click();

      await expect(subscribe).toBeVisible();

      await subscribe.click();

      await expect(unsubscribe).toBeVisible();

    } else {

      await expect(subscribe).toBeVisible();

      await subscribe.click();

      await expect(unsubscribe).toBeVisible();

      await unsubscribe.click();

      await expect(subscribe).toBeVisible();

    }

  });

  test('Member cannot directly open category management', async ({ page }) => {

    await page.goto('/community/categories/create/');

    expect([

      403,

      404,

    ]).toContain(

      (await page.request.get(

        '/community/categories/create/'

      )).status()

    );

  });

});

// ============================================================

// Member drafts

// ============================================================

test.describe('Tavern draft workflows', () => {

  test.use({

    storageState: memberState,

  });

  test('Member can create, resume, edit, and delete a thread draft', async ({ page }) => {

    requireDisposableDatabase();

    const boardUrl = await findWritableBoard(page);

    await page.goto(boardUrl);

    await page.getByRole('link', {

      name: 'Create Thread',

      exact: true,

    }).click();

    const title = uniqueName('Thread Draft');

    const revisedTitle = `${title} Revised`;

    await page.locator('#id_title').fill(title);

    await page.locator('#id_body').fill(

      'Playwright draft body.'

    );

    await page.getByRole('button', {

      name: 'Save Draft',

    }).click();

    await expect(page).toHaveURL(

      /\/community\/drafts\/$/

    );

    const draft = page.locator('.my-post-item', {

      hasText: title,

    });

    await expect(draft).toBeVisible();

    await draft.getByRole('link', {

      name: 'Continue Writing',

    }).click();

    await expect(

      page.locator('#id_title')

    ).toHaveValue(title);

    await expect(

      page.locator('#id_body')

    ).toHaveValue('Playwright draft body.');

    await page.locator('#id_title').fill(revisedTitle);

    await page.getByRole('button', {

      name: 'Save Draft',

    }).click();

    await expect(

      page.locator('.my-post-item', {

        hasText: revisedTitle,

      })

    ).toHaveCount(1);

    const revisedDraft = page.locator('.my-post-item', {

      hasText: revisedTitle,

    });

    page.once('dialog', dialog => dialog.accept());

    await revisedDraft.getByRole('button', {

      name: 'Delete Draft',

    }).click();

    await expect(

      page.locator('.my-post-item', {

        hasText: revisedTitle,

      })

    ).toHaveCount(0);

  });

});

// ============================================================

// Category, board, thread, and post management

// ============================================================

test.describe('Tavern administration and moderation', () => {

  test.use({

    storageState: administratorState,

  });

  test('Administrator can manage a complete isolated Tavern hierarchy', async ({ page }) => {

    requireDisposableDatabase();

    const categoryName = uniqueName('Category');

    const revisedCategoryName = `${categoryName} Edited`;

    const boardName = uniqueName('Board');

    const revisedBoardName = `${boardName} Edited`;

    const threadName = uniqueName('Thread');

    const revisedThreadName = `${threadName} Edited`;

    const destinationName = uniqueName('Destination');

    const splitName = uniqueName('Split');

    // Category creation

    await openTavern(page);

    await page.getByRole('link', {

      name: 'Create Category',

    }).click();

    await expect(

      page.getByRole('heading', {

        name: 'Create Category',

      })

    ).toBeVisible();

    await page.locator('#id_name').fill(categoryName);

    await page.locator('#id_description').fill(

      'Playwright category acceptance fixture.'

    );

    await page.locator('#id_display_order').fill('9000');

    await page.getByRole('button', {

      name: 'Create Category',

    }).click();

    await expect(

      page.locator('.forum-category', {

        hasText: categoryName,

      })

    ).toBeVisible();

    // Category editing

    const category = page.locator('.forum-category', {

      hasText: categoryName,

    });

    await category.getByRole('link', {

      name: 'Edit',

      exact: true,

    }).click();

    await page.locator('#id_name').fill(revisedCategoryName);

    await page.getByRole('button', {

      name: 'Save Changes',

    }).click();

    const editedCategory = page.locator('.forum-category', {

      hasText: revisedCategoryName,

    });

    await expect(editedCategory).toBeVisible();

    // Board creation

    await editedCategory.getByRole('link', {

      name: 'Create Board',

    }).click();

    await expect(

      page.getByRole('heading', {

        name: 'Create Board',

      })

    ).toBeVisible();

    await page.locator('#id_name').fill(boardName);

    await page.locator('#id_description').fill(

      'Playwright board acceptance fixture.'

    );

    await page.locator('#id_display_order').fill('9000');

    await page.getByRole('button', {

      name: 'Create Board',

    }).click();

    await expect(

      page.getByRole('heading', {

        level: 1,

        name: boardName,

      })

    ).toBeVisible();

    const boardUrl = page.url();

    // Board editing

    await page.getByRole('link', {

      name: 'Edit Board',

    }).click();

    await page.locator('#id_name').fill(revisedBoardName);

    await page.getByRole('button', {

      name: 'Save Changes',

    }).click();

    await expect(

      page.getByRole('heading', {

        level: 1,

        name: revisedBoardName,

      })

    ).toBeVisible();

    // Board locking

    await page.getByRole('button', {

      name: 'Lock Board',

    }).click();

    await expect(

      page.getByRole('button', {

        name: 'Unlock Board',

      })

    ).toBeVisible();

    await page.getByRole('button', {

      name: 'Unlock Board',

    }).click();

    await expect(

      page.getByRole('button', {

        name: 'Lock Board',

      })

    ).toBeVisible();

    // Thread creation

    await page.getByRole('link', {

      name: 'Create Thread',

    }).click();

    await page.locator('#id_title').fill(threadName);

    await page.locator('#id_body').fill(

      'Opening post created by Playwright.'

    );

    await page.getByRole('button', {

      name: 'Create Thread',

    }).click();

    await expect(

      page.getByRole('heading', {

        level: 1,

        name: threadName,

      })

    ).toBeVisible();

    const threadUrl = page.url();

    // Thread editing

    await page.getByRole('link', {

      name: 'Edit Thread',

    }).click();

    await page.locator('#id_title').fill(revisedThreadName);

    await page.getByRole('button', {

      name: 'Save Changes',

    }).click();

    await expect(

      page.getByRole('heading', {

        level: 1,

        name: revisedThreadName,

      })

    ).toBeVisible();

    // Thread following

    const follow = page.getByRole('button', {

      name: 'Follow',

      exact: true,

    });

    const unfollow = page.getByRole('button', {

      name: 'Unfollow',

      exact: true,

    });

    if (await follow.count()) {

      await follow.click();

    }

    await expect(unfollow).toBeVisible();

    await unfollow.click();

    await expect(follow).toBeVisible();

    // Thread pinning

    await page.locator(

      '.forum-moderation-actions summary'

    ).click();

    await page.getByRole('button', {

      name: 'Pin',

      exact: true,

    }).click();

    await expect(

      page.locator('.forum-page-title-line')

    ).toContainText('Pinned');

    await page.locator(

      '.forum-moderation-actions summary'

    ).click();

    await page.getByRole('button', {

      name: 'Unpin',

    }).click();

    // Thread locking

    await page.locator(

      '.forum-moderation-actions summary'

    ).click();

    await page.getByRole('button', {

      name: 'Lock',

      exact: true,

    }).click();

    await expect(

      page.locator('.forum-page-title-line')

    ).toContainText('Locked');

    await page.locator(

      '.forum-moderation-actions summary'

    ).click();

    await page.getByRole('button', {

      name: 'Unlock',

      exact: true,

    }).click();

    // Reply creation

    await expect(

      page.locator('#reply')

    ).toBeVisible();

    await page.locator('#id_body').fill(

      'Playwright reply for post management.'

    );

    await page.getByRole('button', {

      name: 'Post Reply',

    }).click();

    await expect(

      page.locator('.forum-post-body', {

        hasText: 'Playwright reply for post management.',

      })

    ).toBeVisible();

    // Reply editing

    const replyPost = page.locator('.forum-post', {

      hasText: 'Playwright reply for post management.',

    });

    await replyPost.locator(

      '.forum-post-menu summary'

    ).click();

    await replyPost.getByRole('link', {

      name: 'Edit',

      exact: true,

    }).click();

    await page.locator('#id_body').fill(

      'Playwright edited reply.'

    );

    await page.getByRole('button', {

      name: 'Save Changes',

    }).click();

    await expect(

      page.locator('.forum-post-body', {

        hasText: 'Playwright edited reply.',

      })

    ).toBeVisible();

    // Post archive and restoration

    const editedPost = page.locator('.forum-post', {

      hasText: 'Playwright edited reply.',

    });

    await editedPost.locator(

      '.forum-post-menu summary'

    ).click();

    await editedPost.getByRole('button', {

      name: 'Archive',

      exact: true,

    }).click();

    await expect(

      page.locator('.forum-post-archived')

    ).not.toHaveCount(0);

    const archivedPost = page.locator(

      '.forum-post-archived'

    ).last();

    await archivedPost.locator(

      '.forum-post-menu summary'

    ).click();

    await archivedPost.getByRole('button', {

      name: 'Restore',

      exact: true,

    }).click();

    await expect(

      page.locator('.forum-post-body', {

        hasText: 'Playwright edited reply.',

      })

    ).toBeVisible();

    // Thread archive and restoration

    await page.getByRole('button', {

      name: 'Archive Thread',

    }).click();

    await page.goto(threadUrl + '?archived=1');

    await expect(

      page.locator('.forum-page-title-line')

    ).toContainText('Archived');

    await page.getByRole('button', {

      name: 'Restore Thread',

    }).click();

    await expect(

      page.getByRole('heading', {

        level: 1,

        name: revisedThreadName,

      })

    ).toBeVisible();

    // Create destination thread

    await page.goto(boardUrl);

    await page.getByRole('link', {

      name: 'Create Thread',

    }).click();

    await page.locator('#id_title').fill(destinationName);

    await page.locator('#id_body').fill(

      'Destination opening post.'

    );

    await page.getByRole('button', {

      name: 'Create Thread',

    }).click();

    const destinationUrl = page.url();

    await expect(

      page.getByRole('heading', {

        level: 1,

        name: destinationName,

      })

    ).toBeVisible();

    // Verify navigation to Move, Merge, and Split forms

    await page.goto(threadUrl);

    await page.locator(

      '.forum-moderation-actions summary'

    ).click();

    await page.getByRole('link', {

      name: 'Move Thread',

    }).click();

    await expect(

      page.getByRole('heading', {

        level: 1,

        name: 'Move Thread',

      })

    ).toBeVisible();

    await expect(

      page.locator('#id_destination_board')

    ).toBeVisible();

    await page.getByRole('link', {

      name: 'Cancel',

    }).click();

    await page.locator(

      '.forum-moderation-actions summary'

    ).click();

    await page.getByRole('link', {

      name: 'Merge Thread',

    }).click();

    await expect(

      page.locator('#id_destination_thread')

    ).toBeVisible();

    await page.getByRole('link', {

      name: 'Cancel',

    }).click();

    await page.locator(

      '.forum-moderation-actions summary'

    ).click();

    await page.getByRole('link', {

      name: 'Split Thread',

    }).click();

    await expect(

      page.getByRole('heading', {

        name: 'Split Thread',

      })

    ).toBeVisible();

    await expect(

      page.locator('#id_posts')

    ).toBeVisible();

    await page.getByRole('link', {

      name: 'Cancel',

    }).click();

    await page.locator(

      '.forum-moderation-actions summary'

    ).click();

    await page.getByRole('link', {

      name: 'Move Posts',

    }).click();

    await expect(

      page.locator('#id_destination_thread')

    ).toBeVisible();

    await expect(

      page.locator('#id_posts')

    ).toBeVisible();

    await page.getByRole('link', {

      name: 'Cancel',

    }).click();

    // Category archive and restoration

    await openTavern(page);

    const managedCategory = page.locator('.forum-category', {

      hasText: revisedCategoryName,

    });

    await managedCategory.getByRole('button', {

      name: 'Archive',

    }).click();

    await page.goto('/community/?archived=1');

    const archivedCategory = page.locator('.forum-category', {

      hasText: revisedCategoryName,

    });

    await expect(archivedCategory).toContainText('Archived');

    await archivedCategory.getByRole('button', {

      name: 'Restore',

    }).click();

    await expect(

      page.locator('.forum-category', {

        hasText: revisedCategoryName,

      })

    ).toBeVisible();

    // Board archive and restoration

    await page.goto(boardUrl);

    await page.getByRole('button', {

      name: 'Archive Board',

    }).click();

    await page.goto(boardUrl + '?archived=1');

    await expect(

      page.locator('.forum-page-title-line')

    ).toContainText('Archived');

    await page.getByRole('button', {

      name: 'Restore Board',

    }).click();



    await expect(

      page.getByRole('heading', {

        level: 1,

        name: revisedBoardName,

      })

    ).toBeVisible();

    // Archive the isolated fixture

    await page.getByRole('button', {

      name: 'Archive Board',

    }).click();

    await page.goto('/community/');

    const finalCategory = page.locator('.forum-category', {

      hasText: revisedCategoryName,

    });

    await finalCategory.getByRole('button', {

      name: 'Archive',

    }).click();

    expect(destinationUrl).toContain('/community/threads/');

    expect(splitName.length).toBeGreaterThan(0);

  });

});

// ============================================================

// Independent, isolated management acceptance scenarios

// ============================================================

type TavernFixture = {

  category: string;

  boardUrl: string;

  boardId: string;

};

async function createManagedFixture(page: Page): Promise<TavernFixture> {

  requireDisposableDatabase();

  const category = uniqueName('Category');

  const boardName = uniqueName('Board');

  await openTavern(page);

  await page.getByRole('link', { name: 'Create Category' }).click();

  await page.locator('#id_name').fill(category);

  await page.locator('#id_display_order').fill('9999');

  await page.getByRole('button', { name: 'Create Category' }).click();

  await page.locator('.forum-category', { hasText: category })

    .getByRole('link', { name: 'Create Board' }).click();

  await page.locator('#id_name').fill(boardName);

  await page.locator('#id_display_order').fill('9999');

  await page.getByRole('button', { name: 'Create Board' }).click();

  await expect(page.getByRole('heading', { level: 1, name: boardName })).toBeVisible();

  const boardUrl = page.url();

  const boardId = new URL(boardUrl).pathname.match(/boards\/(\d+)\//)?.[1];

  if (!boardId) throw new Error(`Cannot determine board ID: ${boardUrl}`);

  return { category, boardUrl, boardId };

}

async function addBoardInCategory(page: Page, fixture: TavernFixture): Promise<TavernFixture> {

  const boardName = uniqueName('Board Destination');

  await openTavern(page);

  await page.locator('.forum-category', { hasText: fixture.category })

    .getByRole('link', { name: 'Create Board' }).click();

  await page.locator('#id_name').fill(boardName);

  await page.locator('#id_display_order').fill('9999');

  await page.getByRole('button', { name: 'Create Board' }).click();

  const boardUrl = page.url();

  const boardId = new URL(boardUrl).pathname.match(/boards\/(\d+)\//)?.[1];

  if (!boardId) throw new Error(`Cannot determine board ID: ${boardUrl}`);

  return { ...fixture, boardUrl, boardId };

}

async function makeThread(page: Page, boardUrl: string, title = uniqueName('Thread')) {

  await page.goto(boardUrl);

  await page.getByRole('link', { name: 'Create Thread', exact: true }).click();

  await page.locator('#id_title').fill(title);

  await page.locator('#id_body').fill(`Opening body for ${title}`);

  await page.getByRole('button', { name: 'Create Thread' }).click();

  await expect(page.getByRole('heading', { level: 1, name: title })).toBeVisible();

  const threadUrl = page.url();

  const threadId = new URL(threadUrl).pathname.match(/threads\/(\d+)\//)?.[1];

  if (!threadId) throw new Error(`Cannot determine thread ID: ${threadUrl}`);

  return { threadUrl, threadId, title };

}

async function makeReply(page: Page, threadUrl: string, body = uniqueName('Reply')) {

  await page.goto(threadUrl);

  await page.locator('#reply #id_body').fill(body);

  await page.getByRole('button', { name: 'Post Reply' }).click();

  const post = page.locator('.forum-post', { hasText: body });

  await expect(post).toBeVisible();

  const postId = (await post.getAttribute('id'))?.replace('post-', '');

  if (!postId) throw new Error(`Cannot determine post ID for ${body}`);

  return { postId, body };

}

async function openModeration(page: Page) {

  const menu = page.locator('.forum-moderation-actions');

  if (!(await menu.evaluate(el => (el as HTMLDetailsElement).open))) {

    await menu.locator('summary').click();

  }

}

async function selectOptionContaining(page: Page, selector: string, labelText: string) {

  const select = page.locator(selector);

  const options = await select.locator('option').evaluateAll(items =>

    items.map(item => ({

      text: (item.textContent || '').trim(),

      value: (item as HTMLOptionElement).value,

    }))

  );

  const option = options.find(item => item.text.includes(labelText) && item.value);

  if (!option) throw new Error(`No option containing ${labelText} at ${selector}`);

  await select.selectOption(option.value);

  return option.value;

}

async function csrfHeaders(page: Page) {

  const token = (await page.context().cookies())

    .find(cookie => cookie.name === 'csrftoken')?.value;

  if (!token) throw new Error('Django CSRF cookie was not present');

  return { 'X-CSRFToken': token };

}

async function memberPage(browser: import('@playwright/test').Browser) {

  const context = await browser.newContext({ storageState: memberState });

  const page = await context.newPage();

  return { page, context };

}

async function secondMemberPage(browser: import('@playwright/test').Browser) {

  const context = await browser.newContext({

    storageState: 'playwright/.auth/testuser02.json',

  });

  const page = await context.newPage();

  return { page, context };

}

test.describe('Tavern isolated moderation operations', () => {

  test.use({ storageState: administratorState });

  test('Moderator moves a thread to a different board and changes its breadcrumb', async ({ page }) => {

    const source = await createManagedFixture(page);

    const destination = await addBoardInCategory(page, source);

    const thread = await makeThread(page, source.boardUrl);

    await openModeration(page);

    await page.getByRole('link', { name: 'Move Thread', exact: true }).click();

    await page.locator('#id_destination_board').selectOption(destination.boardId);

    await page.getByRole('button', { name: 'Move Thread', exact: true }).click();

    await expect(page).toHaveURL(new RegExp(`/threads/${thread.threadId}/`));

    await expect(page.getByRole('navigation', { name: 'Breadcrumb' })

      .locator(`a[href*="/boards/${destination.boardId}/"]`)).toBeVisible();

    await page.goto(source.boardUrl);

    await expect(page.locator('.forum-thread-row', { hasText: thread.title })).toHaveCount(0);

    await page.goto(destination.boardUrl);

    await expect(page.locator('.forum-thread-row', { hasText: thread.title })).toHaveCount(1);

  });

  test('Moderator moves a selected post into another thread', async ({ page }) => {

    const fixture = await createManagedFixture(page);

    const source = await makeThread(page, fixture.boardUrl);

    const moved = await makeReply(page, source.threadUrl);

    const destination = await makeThread(page, fixture.boardUrl);

    await page.goto(source.threadUrl);

    await openModeration(page);

    await page.getByRole('link', { name: 'Move Posts' }).click();

    await page.locator('#id_destination_thread').selectOption(destination.threadId);

    await page.locator('#id_posts').selectOption(moved.postId);

    await page.getByRole('button', { name: 'Move Posts' }).click();

    await expect(page).toHaveURL(new RegExp(`/threads/${destination.threadId}/`));

    await expect(page.locator(`#post-${moved.postId}`)).toBeVisible();

    await page.goto(source.threadUrl);

    await expect(page.locator(`#post-${moved.postId}`)).toHaveCount(0);

  });

  test('Moderator splits a selected reply into a new thread', async ({ page }) => {

    const fixture = await createManagedFixture(page);

    const source = await makeThread(page, fixture.boardUrl);

    const moved = await makeReply(page, source.threadUrl);

    const splitTitle = uniqueName('Split Thread');

    await openModeration(page);

    await page.getByRole('link', { name: 'Split Thread' }).click();

    await page.locator('#id_title').fill(splitTitle);

    await page.locator('#id_destination_board').selectOption(fixture.boardId);

    await page.locator('#id_posts').selectOption(moved.postId);

    await page.getByRole('button', { name: 'Split Thread' }).click();

    await expect(page.getByRole('heading', { level: 1, name: splitTitle })).toBeVisible();

    await expect(page.locator(`#post-${moved.postId}`)).toBeVisible();

    await page.goto(source.threadUrl);

    await expect(page.locator(`#post-${moved.postId}`)).toHaveCount(0);

  });

  test('Moderator merges a source thread into a destination and archives the source', async ({ page }) => {

    const fixture = await createManagedFixture(page);

    const source = await makeThread(page, fixture.boardUrl);

    const reply = await makeReply(page, source.threadUrl);

    const destination = await makeThread(page, fixture.boardUrl);

    await page.goto(source.threadUrl);

    await openModeration(page);

    await page.getByRole('link', { name: 'Merge Thread' }).click();

    await page.locator('#id_destination_thread').selectOption(destination.threadId);

    await page.getByRole('button', { name: 'Merge Thread' }).click();

    await expect(page).toHaveURL(new RegExp(`/threads/${destination.threadId}/`));

    await expect(page.locator(`#post-${reply.postId}`)).toBeVisible();

    const sourceArchived = runDjango(

      `from community.models import ForumThread\n` +

      `print(bool(ForumThread.objects.get(pk=${source.threadId}).archived_at))`

    ).split('\n').at(-1)?.trim();

    expect(sourceArchived).toBe('True');

  });

  test('Moderator can review a post report submitted by a member', async ({ page, browser }) => {

    const fixture = await createManagedFixture(page);

    const thread = await makeThread(page, fixture.boardUrl);

    const postId = (await page.locator('.forum-post').first().getAttribute('id'))?.replace('post-', '');

    if (!postId) throw new Error('Opening post was not rendered');

    const reason = uniqueName('Report Reason');

    const member = await memberPage(browser);

    try {

      await member.page.goto(thread.threadUrl);

      const post = member.page.locator(`#post-${postId}`);

      await post.locator('.forum-post-menu summary').click();

      await post.getByRole('link', { name: 'Report' }).click();

      await member.page.locator('#id_reason').fill(reason);

      await member.page.getByRole('button', { name: /Report|Submit/ }).click();

      await expect(member.page).toHaveURL(new RegExp(`/threads/${thread.threadId}/`));

    } finally {

      await member.context.close();

    }

    const reportId = runDjango(

      `from community.models import ForumPostReport\n` +

      `print(ForumPostReport.objects.get(reason=${JSON.stringify(reason)}).pk)`

    ).split('\n').at(-1)?.trim();

    if (!reportId || !/^\d+$/.test(reportId)) throw new Error('Report was not persisted');

    const response = await page.request.post(`/community/reports/${reportId}/review/`, {

      form: { status: 'RESOLVED', resolution_note: 'Reviewed by Playwright' },

      headers: await csrfHeaders(page),

    });

    expect(response.status()).toBe(200); // Following the redirect returns the thread page.

    const status = runDjango(

      `from community.models import ForumPostReport\n` +

      `print(ForumPostReport.objects.get(pk=${reportId}).status)`

    ).split('\n').at(-1)?.trim();

    expect(status).toBe('RESOLVED');

  });

});

test.describe('Tavern isolated member publication and visibility', () => {

  test.use({ storageState: administratorState });

  test('Member resumes and publishes a reply draft with its link', async ({ page, browser }) => {

    const fixture = await createManagedFixture(page);

    const thread = await makeThread(page, fixture.boardUrl);

    const member = await memberPage(browser);

    try {

      const body = uniqueName('Reply Draft');

      await member.page.goto(thread.threadUrl);

      await member.page.locator('#reply #id_body').fill(body);

      await fillAttachment(member.page, 'attachments', 'Member Link', 'https\://example.com/member-link');

      await member.page.getByRole('button', { name: 'Save Draft' }).click();

      await expect(member.page).toHaveURL(/\/community\/drafts\/$/);

      const draft = member.page.locator('.my-post-item', { hasText: body });

      await expect(draft).toHaveCount(1);

      await draft.getByRole('link', { name: 'Continue Writing' }).click();

      await expect(member.page.locator('#reply #id_body')).toHaveValue(body);

      await expect(member.page.locator('#id_attachments-0-url'))

        .toHaveValue('https\://example.com/member-link');

      await member.page.getByRole('button', { name: 'Post Reply' }).click();

      await expect(member.page.locator('.forum-post', { hasText: body })).toBeVisible();

      await expect(member.page.locator('.forum-post', { hasText: body }))

        .toContainText('Member Link');

      await member.page.goto('/community/drafts/');

      await expect(member.page.locator('.my-post-item', { hasText: body })).toHaveCount(0);

    } finally {

      await member.context.close();

    }

  });

  test('Member resumes and publishes a thread draft with its link', async ({ page, browser }) => {

    const fixture = await createManagedFixture(page);

    const member = await memberPage(browser);

    try {

      const title = uniqueName('Thread Draft');

      await member.page.goto(fixture.boardUrl);

      await member.page.getByRole('link', { name: 'Create Thread' }).click();

      await member.page.locator('#id_title').fill(title);

      await member.page.locator('#id_body').fill('Saved opening post');

      await fillAttachment(member.page, 'attachments', 'Thread Link', 'https\://example.com/thread-link');

      await member.page.getByRole('button', { name: 'Save Draft' }).click();

      await expect(member.page).toHaveURL(/\/community\/drafts\/$/);

      const draft = member.page.locator('.my-post-item', { hasText: title });

      await expect(draft).toHaveCount(1);

      await draft.getByRole('link', { name: 'Continue Writing' }).click();

      await expect(member.page.locator('#id_title')).toHaveValue(title);

      await expect(member.page.locator('#id_attachments-0-url'))

        .toHaveValue('https\://example.com/thread-link');

      await member.page.getByRole('button', { name: 'Create Thread' }).click();

      await expect(member.page.getByRole('heading', { level: 1, name: title })).toBeVisible();

      await expect(member.page.locator('.forum-post-attachments')).toContainText('Thread Link');

      await member.page.goto('/community/drafts/');

      await expect(member.page.locator('.my-post-item', { hasText: title })).toHaveCount(0);

    } finally {

      await member.context.close();

    }

  });

  test('Member quotes another post and publishes the reply', async ({ page, browser }) => {

    const fixture = await createManagedFixture(page);

    const thread = await makeThread(page, fixture.boardUrl);

    const openingPostId = (await page.locator('.forum-post').first().getAttribute('id'))?.replace('post-', '');

    if (!openingPostId) throw new Error('No opening post');

    const member = await memberPage(browser);

    try {

      await member.page.goto(thread.threadUrl);

      const post = member.page.locator(`#post-${openingPostId}`);

      await post.locator('.forum-post-menu summary').click();

      await post.getByRole('link', { name: 'Quote' }).click();

      await expect(member.page).toHaveURL(/quote_post=\d+/);

      await expect(member.page.locator('input[name="quoted_post_id"]'))

        .toHaveValue(openingPostId);

      const replyBody = uniqueName('Quoted Reply');

      await member.page.locator('#reply #id_body').fill(replyBody);

      await member.page.getByRole('button', { name: 'Post Reply' }).click();

      await expect(member.page.locator('.forum-post', { hasText: replyBody })).toBeVisible();

    } finally {

      await member.context.close();

    }

  });

  test('Staff-only board hides thread creation from a regular member', async ({ page, browser }) => {

    const fixture = await createManagedFixture(page);

    await page.goto(fixture.boardUrl);

    await page.getByRole('link', { name: 'Edit Board' }).click();

    await page.locator('#id_thread_creation_policy').selectOption('STAFF_ONLY');

    await page.getByRole('button', { name: 'Save Changes' }).click();

    const member = await memberPage(browser);

    try {

      await member.page.goto(fixture.boardUrl);

      await expect(member.page.getByRole('link', { name: 'Create Thread' })).toHaveCount(0);

      const forbidden = await member.page.request.get(

        `/community/boards/${fixture.boardId}/threads/create/`,

        { maxRedirects: 0 }

      );

      expect(forbidden.status()).toBe(403);

    } finally {

      await member.context.close();

    }

  });

  test('Board user target allows one member and hides the board from another', async ({ page, browser }) => {

    const fixture = await createManagedFixture(page);

    await page.goto(fixture.boardUrl);

    await page.getByRole('link', { name: 'Edit Board' }).click();

    await selectOptionContaining(page, '#id_targets-0-user', 'testuser01');

    await page.getByRole('button', { name: 'Save Changes' }).click();

    const allowed = await memberPage(browser);

    const denied = await secondMemberPage(browser);

    try {

      await allowed.page.goto(fixture.boardUrl);

      await expect(allowed.page.locator('.forum-board-page')).toBeVisible();

      const deniedResponse = await denied.page.goto(fixture.boardUrl);

      expect([403, 404]).toContain(deniedResponse?.status());

      await denied.page.goto('/community/');

      await expect(denied.page.locator(`.forum-board-row#board-${fixture.boardId}`))

        .toHaveCount(0);

    } finally {

      await allowed.context.close();

      await denied.context.close();

    }

  });

  test('Invalid creation forms show errors and do not create a thread', async ({ page }) => {

    const fixture = await createManagedFixture(page);

    await page.goto(fixture.boardUrl);

    await page.getByRole('link', { name: 'Create Thread' }).click();

    await page.locator('#id_title').fill('');

    await page.locator('#id_body').fill('Invalid thread without title');

    await page.getByRole('button', { name: 'Create Thread' }).click();

    await expect(page.locator('#id_title')).toBeVisible();

    await expect(page).toHaveURL(/threads\/create\//);

    const threadList = await page.request.get(fixture.boardUrl);

    expect(await threadList.text()).not.toContain('Invalid thread without title');

  });

});

test.describe('Tavern anonymous authorization', () => {

  test.use({ storageState: { cookies: [], origins: [] } });

  test('Anonymous visitors are redirected when they request member Tavern pages', async ({ page }) => {

    for (const path of ['/community/', '/community/drafts/', '/community/categories/create/']) {

      const response = await page.request.get(path, { maxRedirects: 0 });

      expect([302, 403]).toContain(response.status());

    }

  });

});

// ============================================================

// Additional access-control and state-transition checks

// ============================================================

test.describe('Tavern restricted operations', () => {

  test.use({ storageState: administratorState });

  test('A member cannot open privileged moderation endpoints directly', async ({ page, browser }) => {

    const fixture = await createManagedFixture(page);

    const thread = await makeThread(page, fixture.boardUrl);

    const member = await memberPage(browser);

    try {

      const paths = [

        `/community/boards/${fixture.boardId}/edit/`,

        `/community/threads/${thread.threadId}/move/`,

        `/community/threads/${thread.threadId}/merge/`,

        `/community/threads/${thread.threadId}/split/`,

        `/community/threads/${thread.threadId}/move-posts/`,

      ];

      for (const path of paths) {

        const response = await member.page.request.get(path, { maxRedirects: 0 });

        expect([403, 404], `Unexpected permission at ${path}`).toContain(response.status());

      }

    } finally {

      await member.context.close();

    }

  });

  test('Another member cannot resume a draft they do not own', async ({ page, browser }) => {

    const fixture = await createManagedFixture(page);

    const owner = await memberPage(browser);

    const stranger = await secondMemberPage(browser);

    try {

      const title = uniqueName('Private Draft');

      await owner.page.goto(fixture.boardUrl);

      await owner.page.getByRole('link', { name: 'Create Thread' }).click();

      await owner.page.locator('#id_title').fill(title);

      await owner.page.locator('#id_body').fill('Owner-only unsent text');

      await owner.page.getByRole('button', { name: 'Save Draft' }).click();

      const draft = owner.page.locator('.my-post-item', { hasText: title });

      await expect(draft).toBeVisible();

      const link = await draft.getByRole('link', { name: 'Continue Writing' }).getAttribute('href');

      if (!link) throw new Error('Draft resume URL is missing');

      const response = await stranger.page.goto(link);

      expect([403, 404]).toContain(response?.status());

      await owner.page.goto('/community/drafts/');

      owner.page.once('dialog', dialog => dialog.accept());

      await owner.page.locator('.my-post-item', { hasText: title })

        .getByRole('button', { name: 'Delete Draft' }).click();

      await expect(owner.page.locator('.my-post-item', { hasText: title })).toHaveCount(0);

    } finally {

      await owner.context.close();

      await stranger.context.close();

    }

  });

  test('Locking a thread prevents a regular member from replying', async ({ page, browser }) => {

    const fixture = await createManagedFixture(page);

    const thread = await makeThread(page, fixture.boardUrl);

    await openModeration(page);

    await page.getByRole('button', { name: 'Lock', exact: true }).click();

    const member = await memberPage(browser);

    try {

      await member.page.goto(thread.threadUrl);

      await expect(member.page.locator('#reply')).toHaveCount(0);

      const response = await member.page.request.post(

        `/community/threads/${thread.threadId}/post/`,

        { form: { body: 'Must not publish in a locked thread' }, headers: await csrfHeaders(member.page), maxRedirects: 0 }

      );

      expect([403, 404]).toContain(response.status());

    } finally {

      await member.context.close();

    }

  });

});
