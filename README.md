
# EldVatten Community Web App

A self-hosted community management and communication platform for **EldVatten**, a nonprofit educational organization focused on Viking-era historical research, re-enactment, and related cultures.

EldVatten brings community discussion, messaging, events, governance, membership, notifications, resources, and administrative operations into one server-rendered Django application.

> **Project status:** Active development. This README describes the local development environment and the project's functionality and intended architecture. It is **not** a declaration that production deployment or complete browser acceptance has been verified.

## Quick start

The standard development environment runs Django and PostgreSQL in Docker Compose. You do **not** need a local Python or PostgreSQL installation.

### 1. Install prerequisites

| Software | Purpose | Link |
| --- | --- | --- |
| Git | Clone and manage source code | [Download Git](https://git-scm.com/downloads) |
| Docker Desktop | Run development containers on Windows/macOS | [Download Docker Desktop](https://www.docker.com/products/docker-desktop/) |
| Node.js 22+ | npm and Playwright browser tests | [Download Node.js](https://nodejs.org/) |
| Visual Studio Code (optional) | Recommended editor | [Download VS Code](https://code.visualstudio.com/) |

npm comes with Node.js. Node.js 20 is the minimum supported by the checked-in Playwright dependencies; Node.js 22 is the recommended baseline.

On Linux, use Docker Engine with the Docker Compose plugin instead of Docker Desktop.

**Windows:** Enable Docker Desktop's WSL 2 backend. If necessary, install WSL 2 from an elevated PowerShell terminal, then restart when prompted:

```powershell
wsl --install
```

Check that the tools are available:

```powershell
git --version
docker --version
docker compose version
node --version
npm --version
```

### 2. Clone the repository

```powershell
git clone https://github.com/ColeMcGregor/EldvattenWebApp.git
cd EldvattenWebApp
```

Optionally open it in VS Code with `code .`.

**Check for the root `Dockerfile` before building.** The development `compose.yaml` uses `build: .`, which requires a Dockerfile in the repository root. During a November 12, 2026 review, that file was not retrievable from the default GitHub branch. If your checkout does not contain it, obtain the development Dockerfile from the maintainer. Files on the maintainer's machine may not yet be committed.

### 3. Configure the local environment

Copy the example environment file:

```powershell
Copy-Item .env.example .env
```

On Linux/macOS, use `cp .env.example .env`.

Edit `.env` for your local environment. The relevant settings include:

```dotenv
DJANGO_SECRET_KEY=replace-with-a-long-random-local-secret
DJANGO_DEBUG=True
DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1

POSTGRES_DB=eldvatten
POSTGRES_USER=eldvatten
POSTGRES_PASSWORD=replace-with-a-unique-local-password
POSTGRES_HOST=db
POSTGRES_PORT=5432

VAPID_PUBLIC_KEY=
VAPID_PRIVATE_KEY=
VAPID_SUBJECT=
```

- Generate a unique `DJANGO_SECRET_KEY`; never reuse a production key.
- `DJANGO_DEBUG=True` is for **development only**.
- `POSTGRES_HOST=db` refers to the database service *inside* the Compose network. Do not replace it with `localhost` unless you deliberately run Django outside Compose and configure database access accordingly.
- VAPID settings may remain empty for ordinary development without real browser push subscriptions. Actual Web Push requires valid keys and network access to the browser's push provider.
- `.env` contains secrets, is excluded from Git, and must not be committed.

**Database password caveat:** Changing `POSTGRES_PASSWORD` after PostgreSQL has initialized its persistent volume does not automatically change the existing database user's password.

### 4. Start the containers

Ensure Docker is running, then execute from the repository root:

```powershell
docker compose config
docker compose up --build -d
docker compose ps
```

The development Compose setup starts:

| Service | Purpose |
| --- | --- |
| `web` | Django development server at `0.0.0.0:8000` |
| `db` | PostgreSQL database |

For logs:

```powershell
docker compose logs -f web
docker compose logs -f db
```

### 5. Initialize Django

```powershell
docker compose exec web python manage.py migrate
docker compose exec web python manage.py check
docker compose exec web python manage.py createsuperuser
```

If PostgreSQL is still initializing, let it become ready before running migrations. The `createsuperuser` command is intended for a fresh database; follow its prompts.

### 6. Open the application

| Destination | Local URL |
| --- | --- |
| Public homepage | <http://localhost:8000/> |
| Member login | <http://localhost:8000/accounts/login/> |
| Django admin | <http://localhost:8000/admin/> |

The local development environment does not require nginx, Cloudflare, or HTTPS termination.

---

## Architecture and features

### Technology stack

| Component | Technology |
| --- | --- |
| Backend | Python 3.13, Django 5.2 |
| Database | PostgreSQL 17 |
| Frontend | Django templates, HTML, CSS, vanilla JavaScript |
| Containers | Docker, Docker Compose |
| Browser tests | Playwright (Chromium, Firefox, WebKit) |
| Source control | Git, GitHub |
| Production target | Linux, Gunicorn, nginx, Cloudflare |

Django owns authentication, authorization, routing, application logic, data access, and server-rendered views. PostgreSQL stores persistent application and organizational data.

### Application areas

The following describes the application's feature areas; individual changes may still be under development or awaiting acceptance on a given branch.

| Area | Capabilities |
| --- | --- |
| **Accounts and identity** | Registration, authentication, membership approval, account administration, role-based access, personal and EldVatten identities, organizational affiliations |
| **Organization** | Citizenship classes, social ranks, chapters, households, offices, leadership assignments, governance bodies, Orders and ranks, memberships, sponsorships, historical records |
| **The Tavern** | Hierarchical forum, visibility targeting, subscriptions, unread tracking, drafts, moderation, reporting, search, notifications, auditing |
| **Events** | Event creation and visibility, invitations, RSVPs, attendance, calendar views, public upcoming Events |
| **Actions** | Assignments, deadlines, completion and lifecycle tracking, links to Tavern Threads |
| **Messaging** | Direct and group conversations, membership controls, blocking, muting, notifications |
| **Voting** | Eligibility, ballots, anonymous or identified voting, quorum, approval rules, opening/closing votes, results |
| **Resources** | Resource library, private uploads, external links, targeted visibility, authorized downloads and management |
| **Notifications** | In-app and Web Push notifications, preferences, read/unread state, links to application records |
| **Directory** | Member browsing, filtering and member profiles |
| **Administration and audit** | Account and organizational management, moderation, permission boundaries, audit recording and inspection |
| **Public website** | General EldVatten information and public-facing Event/calendar content |

**The Tavern** uses the hierarchy `Category → Board → Thread → Post`. Threads and Posts support management, editing, archives/restoration, movement, merging/splitting where applicable, quotation and reporting.

**Messaging is not end-to-end encrypted.** Messages are managed by the application.

Organization records are also used by access-control, targeting, and eligibility services throughout the application.

### Repository layout

```text
EldvattenWebApp/
├── accounts/
├── actions/
├── administration/
├── audit/
├── community/
├── config/
├── core/
├── events/
├── feedback/
├── messaging/
├── notifications/
├── organization/
├── resources/
├── voting/
├── static/
├── templates/
├── e2e/
├── manage.py
├── requirements.txt
├── compose.yaml
├── package.json
├── package-lock.json
├── playwright.config.ts
├── .env.example
└── README.md
```

The development Compose configuration also requires a root `Dockerfile`; confirm it exists in your checkout.

### Intended production request path

```text
Browser → Cloudflare → nginx → Gunicorn → Django → PostgreSQL
```

This is a **deployment target**, not the local development setup. Production requires separate configuration and security validation; see [Production deployment](#production-deployment).

---


## Development Data

### Populate a Disposable Development Database

The application provides Django management commands for populating the database with fictional development data.

These commands are located in `core/management/commands/` and are intended for local development, testing, and demonstrating application functionality.

#### Primary Development Seeder

The `seed_dev_data.py` command creates fictional user accounts, organizational memberships, roles, permissions, and related development records.

Run:

```powershell
docker compose exec web python manage.py seed_dev_data
```

This establishes the primary development data used throughout the application.

#### Domain-Specific Seeders

Additional commands populate individual application domains with fictional records.

| Command | Purpose |
| --- | --- |
| `seed_action_data` | Creates fictional Actions, assignments, and related task records. |
| `seed_event_data` | Creates fictional Events and associated scheduling data. |
| `seed_forum_data` | Populates The Tavern with Categories, Boards, Threads, and Posts. |
| `seed_resource_data` | Creates fictional Resources for testing browsing and management. |
| `seed_voting_data` | Creates fictional Voting records covering different voting scenarios. |

Run the relevant commands from the repository root:

```powershell
docker compose exec web python manage.py seed_action_data
docker compose exec web python manage.py seed_event_data
docker compose exec web python manage.py seed_forum_data
docker compose exec web python manage.py seed_resource_data
docker compose exec web python manage.py seed_voting_data
```

Run the primary development seeder first when setting up a fresh database so that the fictional accounts and organizational records are available to domain-specific seeders.

Each command can also be invoked individually when its required supporting data is present.

#### Maintenance Commands

The same directory contains two database and file-maintenance utilities:

| Command | Purpose |
| --- | --- |
| `cleanup_orphaned_resource_files` | Identifies and cleans up Resource files that are no longer associated with active database records. |
| `cleanup_submission_throttles` | Removes obsolete submission-throttling records. |

These utilities are separate from development-data generation and should only be run when their maintenance behavior is required.

### Development Data Safety

**Warning:** Seeding commands modify the connected database and may create or update substantial amounts of data.

- Use these commands only against a disposable development database.
- Never execute development seeders against production or real member data.
- Confirm that Docker Compose is connected to the intended database before running them.
- Keep development credentials separate from production credentials.
- Development seeders should be run with Django's development configuration (`DJANGO_DEBUG=True`).

The generated records are fictional and intended for testing. They are not production data.

The primary development seeder and the domain-specific seeders may have dependencies on existing accounts, organizational records, or other application data. Review the relevant command implementation when running them against a partially populated database.



### Seeded test accounts

| Account | Development password | Purpose |
| --- | --- | --- |
| `suTest` | `testpassword` | Development superuser |
| `testuser01` through `testuser52` | `Eldvatten!123_` | Fictional development members |

The seed data varies account statuses, organizational memberships, roles, permissions, social ranks, citizenship, and leadership assignments. The source README also identifies EldVatten names among seeded fields; verify the current local implementation and migrations when using this feature.

These credentials are intentionally known and **must never be used in production**.

---


FROM HERE THE APPLICATION SHOULD BE ACCESSIBLE FROM LOCALHOST:8000 IF ALL WAS DONE RIGHT. 


### Django tests

Run the full backend test suite:

```powershell
docker compose exec web python manage.py test               (over 700 tests so be careful)
```

Run individual domains or a related group:

```powershell
docker compose exec web python manage.py test accounts
docker compose exec web python manage.py test organization
docker compose exec web python manage.py test notifications
docker compose exec web python manage.py test accounts messaging notifications organization audit
```

The Django test runner normally creates and deletes a separate test database. The configured PostgreSQL user must be allowed to create it.

These tests cover models, application services, authentication, authorization, validation, workflows, notifications, administrative operations, audit logging, and cross-domain integrations. Passing tests do not, by themselves, establish complete browser or production acceptance.

### Install Playwright

From the repository root:

```powershell
npm ci
npx playwright install
```

Playwright is configured for Chromium, Firefox, and WebKit. On Linux, additional OS dependencies may be needed; after reviewing the package changes, you can use:

```bash
npx playwright install --with-deps
```

### Configure browser-test credentials

The authentication setup in `e2e/auth.setup.ts` uses `suTest`, `testuser01`, and `testuser02`.

Create `.env.playwright` at the repository root:

```dotenv
E2E_SUTEST_PASSWORD=testpassword
E2E_TESTUSER01_PASSWORD=Eldvatten!123_
E2E_TESTUSER02_PASSWORD=Eldvatten!123_
```

Adjust these values if the development credentials have changed. `.env.playwright` is Git-ignored and must not be committed.

The setup creates authenticated session files under `playwright/.auth/` (for example, `suTest.json`). **These files contain authentication state and must not be committed or shared.**

Start Django and PostgreSQL before running browser tests.

### Run Playwright

```powershell
# Generate authenticated browser state
npx playwright test --project=setup

# Run browser projects
npx playwright test --project=chromium
npx playwright test --project=firefox
npx playwright test --project=webkit

# Run Chromium with a visible browser
npx playwright test --project=chromium --headed
```


### Reports and debugging

```powershell
npx playwright show-report
npx playwright show-trace path/to/trace.zip
```

Playwright traces and related artifacts may be written to `test-results/`. The Playwright VS Code extension can also run and debug individual tests.

Browser tests may require the seeded users, permissions, and records. Creating a superuser alone may not satisfy every acceptance test.

---

## Everyday development commands

Run these from the repository root:

| Task | Command |
| --- | --- |
| Start services | `docker compose up -d` |
| Stop services (keep data) | `docker compose down` |
| Rebuild services | `docker compose up --build -d` |
| Show service status | `docker compose ps` |
| Follow Django logs | `docker compose logs -f web` |
| Open Django shell | `docker compose exec web python manage.py shell` |
| Check configuration | `docker compose exec web python manage.py check` |
| Check for missing migrations | `docker compose exec web python manage.py makemigrations --check --dry-run` |
| Generate migrations | `docker compose exec web python manage.py makemigrations` |
| Apply migrations | `docker compose exec web python manage.py migrate` |

The Compose setup mounts the checkout into Django using `.:/app`, so most Python, template, CSS, and JavaScript edits appear in the container without rebuilding. The development server reloads ordinary Python changes. Rebuild after changing dependencies or container build settings.

**Data persistence:** PostgreSQL uses a Docker volume. `docker compose down` preserves it; **`docker compose down -v` deletes Compose-managed volumes, including database data**. Use `-v` only when intentionally resetting disposable development data.

### Recommended VS Code extensions

| Extension | ID | Purpose |
| --- | --- | --- |
| Python | `ms-python.python` | Python tooling and debugging |
| Pylance | `ms-python.vscode-pylance` | Python analysis |
| Docker | `ms-azuretools.vscode-docker` | Container management |
| Playwright Test | `ms-playwright.playwright` | Browser test execution/debugging |
| Django | `batisteo.vscode-django` | Template syntax support |

Install from the VS Code Extensions view or with `code --install-extension <extension-id>` if `code` is on your `PATH`. VS Code is optional; `.vscode/` is excluded from Git tracking in the source README's reviewed configuration.

---

## Troubleshooting

| Problem | What to check |
| --- | --- |
| Docker does not start | Docker Desktop/Engine, `docker compose version`, WSL 2 backend on Windows |
| Dockerfile missing | `compose.yaml` requires a root `Dockerfile` because it uses `build: .`; request it from the maintainer if absent |
| Django cannot connect to PostgreSQL | `docker compose ps`, `docker compose logs db`, and `POSTGRES_HOST=db` inside Compose |
| Port 8000 already in use | Stop the conflicting process or adjust the host-port mapping and Playwright `baseURL` |
| Playwright login fails | Running Django, seeded users, `.env.playwright`, matching credentials, `http://localhost:8000` |
| Playwright browsers missing | Run `npx playwright install` |
| Browser tests lack required records | Seed a **disposable** development database; verify expected permissions and fixtures |
| Local files differ from GitHub | Run `git status`; uncommitted/unpushed files are unavailable to other contributors |


## Contributing and security

For collaborative work:

1. Create a focused Git branch, such as `git switch -c feature/example-change`.
2. Keep changes scoped to the relevant application area.
3. Run appropriate Django tests and any relevant Playwright checks.
4. Review your diff and staged files carefully.
5. Submit a pull request when collaborating.

EXPECTED commit message formatting:

```
git commit -m "feat(Templates:community): updated thread_detail to contain drafts link"
```

**Do not commit:**

- `.env`, `.env.playwright`, VAPID private keys, or other secrets.
- Playwright authentication state files.
- Production database exports or real member information.
- Private uploaded media.
- Test logs or reports containing sensitive data.

The repository's `.gitignore` is intended to exclude common local secrets and outputs. Inspect `git status` and the staged diff rather than relying on ignore rules alone.


## Production deployment

**The development Compose configuration is not a production deployment.** The target environment includes Linux hosting, PostgreSQL, Gunicorn, nginx, Cloudflare, HTTPS, hardened Django settings, static-file delivery, protected private media, logging and monitoring, health checks, backups and tested restoration, appropriate rate limiting, and real Web Push configuration.

Run Django's deployment checks against **actual production settings** as part of validation:

```powershell
docker compose exec web python manage.py check --deploy
```

A passing check is not sufficient on its own. Production validation must also cover authorization, private uploads/downloads, proxy trust, browser compatibility, push delivery, backups, and restoration. Do not treat the development settings (`DJANGO_DEBUG=True`, `runserver`) as production-ready.

---

## License and copyright

Copyright © 2026 McGregor Systems LLC. All rights reserved.

This software is proprietary. Copying, modification, distribution, sublicensing, or use outside the terms authorized by the copyright holder is prohibited. Access to the repository does not, by itself, grant a license to use or distribute the contents.

**Maintainer action required:** The source README reports that `package.json` declares `"license": "ISC"`, which conflicts with the proprietary notice above. Reconcile the package metadata and intended license before distributing the project to additional parties.
