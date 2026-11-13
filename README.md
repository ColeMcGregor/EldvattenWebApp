
# EldVatten Community Web App

A self-hosted community management and communication platform for **EldVatten**, a nonprofit educational organization focused on Viking-era historical research, re-enactment, and related cultures.

The application brings community discussions, messaging, events, voting, membership, resources, and administrative operations into one Django-based system.

> **Status:** Active development. The instructions below cover local development. Production deployment and full cross-browser acceptance are separate workstreams.

## Features

| Area | Capabilities |
| --- | --- |
| **Accounts and identity** | Registration, authentication, member approvals, account administration, access controls, personal and EldVatten names, and organizational affiliations |
| **Organization** | Citizenship classes, social ranks, chapters, households, offices, leadership assignments, Orders, governance bodies, and historical records |
| **The Tavern** | Category → Board → Thread → Post forum, subscriptions, targeted visibility, drafts, moderation, reports, search, and auditing |
| **Events** | Creation, invitations, visibility, RSVPs, attendance, calendars, and public upcoming events |
| **Actions** | Assignments, deadlines, completion tracking, and links to Tavern Threads |
| **Messaging** | Direct and group conversations, blocking, muting, membership controls, and notifications |
| **Voting** | Eligibility targeting, anonymous and identified ballots, quorum, required responses, voting lifecycles, and results |
| **Resources** | Private file uploads, external links, visibility targeting, authorized downloads, and management |
| **Notifications** | In-app and Web Push notifications, preferences, and read/unread state |
| **Directory** | Member browsing, filtering, and profiles |
| **Administration and audit** | Member and organizational management, permission-controlled operations, and audit records |
| **Public website** | Information about EldVatten, public calendar, and upcoming events |

Organization records are used throughout the application for authorization, targeting, and eligibility. **Messages are application-managed and are not end-to-end encrypted.** Features may be at different implementation or acceptance stages depending on the branch.

## Technology and architecture

| Component | Technology |
| --- | --- |
| Backend | Python 3.13, Django 5.2 |
| Database | PostgreSQL 17 |
| Frontend | Django templates, HTML, CSS, vanilla JavaScript |
| Local development | Docker and Docker Compose |
| Browser testing | Playwright (Chromium, Firefox, WebKit) |
| Source control | Git and GitHub |
| Production target | Linux, Gunicorn, nginx, Cloudflare |

Django handles authentication, authorization, routing, server-rendered pages, and application logic. PostgreSQL stores application and organizational data. The application is organized into separate Django domains within a modular monolith.

### Repository structure

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
├── Dockerfile
├── compose.yaml
├── manage.py
├── requirements.txt
├── package.json
├── package-lock.json
├── playwright.config.ts
├── .env.example
└── README.md
```

The Compose configuration uses `build: .` and therefore requires a root `Dockerfile`. If it is absent from your checkout, obtain it from the maintainer before building.

## Local development setup

Django and PostgreSQL run in Docker containers. You do **not** need to install Python or PostgreSQL directly.

### 1. Prerequisites

| Software | Purpose | Link |
| --- | --- | --- |
| Git | Source control | [Install Git](https://git-scm.com/downloads) |
| Docker Desktop | Windows/macOS containers | [Install Docker](https://www.docker.com/products/docker-desktop/) |
| Node.js 22+ | npm and Playwright | [Install Node.js](https://nodejs.org/) |
| Visual Studio Code (optional) | Recommended editor | [Install VS Code](https://code.visualstudio.com/) |

Node.js includes npm. The project recommends Node.js 22; Node.js 20 is the minimum supported by the Playwright dependencies described in the existing project configuration. Linux developers can use Docker Engine and the Docker Compose plugin instead of Docker Desktop.

On Windows, enable the Docker Desktop WSL 2 backend. If WSL 2 is not installed, run PowerShell as Administrator:

```powershell
wsl --install
```

Restart if prompted, then verify your tools:

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

Open the checkout in your preferred editor, or use `code .` in VS Code.


### 3. Configure environment variables

The application uses a file named `.env` to store configuration settings such as database credentials, security keys, and notification settings.

This file is specific to your computer and should **never be uploaded to GitHub**.

#### Step 1: Create your `.env` file

The repository includes a file named `.env.example`, which serves as a template.

Open a terminal in the project's root directory (`EldvattenWebApp`) and run:

```powershell
Copy-Item .env.example .env
```

This creates a copy named `.env` without modifying the original.

If you're using Linux or macOS, use:

```bash
cp .env.example .env
```

You should now see both files in the project root:

```text
EldvattenWebApp/
├── .env.example
├── .env
├── compose.yaml
├── manage.py
└── ...
```

If `.env` does not appear in VS Code, check whether your editor is hiding Git-ignored files. The file may still exist.

#### Step 2: Open and configure `.env`

In VS Code, open `.env` and locate the following settings. If any are missing, add them.

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

Each line follows the format `VARIABLE_NAME=value`.

Do not add spaces around the `=` sign.

#### Step 3: Configure Django

These settings control the Django application.

| Variable | What it does | What you should enter |
| --- | --- | --- |
| `DJANGO_SECRET_KEY` | Protects cryptographically signed application data. | A long, randomly generated secret. |
| `DJANGO_DEBUG` | Enables Django's development features and detailed error pages. | `True` for local development. |
| `DJANGO_ALLOWED_HOSTS` | Specifies which hostnames can access Django. | `localhost,127.0.0.1` for local development. |

**Generate a Django secret key**

Do not leave `DJANGO_SECRET_KEY` set to the example placeholder.

With the Docker image already built, you can generate a key using:

```powershell
docker compose run --rm --no-deps web python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

Copy the generated value and paste it after `DJANGO_SECRET_KEY=` in `.env`.

For example, the line should look like:

```dotenv
DJANGO_SECRET_KEY=your-generated-secret-goes-here
```

Use the actual generated value, not the example text.

**Important:** `DJANGO_DEBUG=True` must only be used for local development. Never enable it on a publicly accessible production server.

#### Step 4: Configure PostgreSQL

PostgreSQL is the database that stores application information.

Docker Compose automatically starts PostgreSQL in its own container. You do not need to install PostgreSQL separately.

| Variable | What it does | What you should enter |
| --- | --- | --- |
| `POSTGRES_DB` | Name of the database. | `eldvatten` |
| `POSTGRES_USER` | Database username. | `eldvatten` |
| `POSTGRES_PASSWORD` | Password for the database account. | A unique password you choose. |
| `POSTGRES_HOST` | Hostname Django uses to locate PostgreSQL. | `db` |
| `POSTGRES_PORT` | PostgreSQL network port. | `5432` |

For a new development environment, keep everything except the password at the suggested values:

```dotenv
POSTGRES_DB=eldvatten
POSTGRES_USER=eldvatten
POSTGRES_PASSWORD=your-chosen-database-password
POSTGRES_HOST=db
POSTGRES_PORT=5432
```

Replace `your-chosen-database-password` with an actual password.

**Why is the hostname `db` instead of `localhost`?**

Docker Compose gives each service a hostname based on its service name.

The PostgreSQL service is named `db`, so Django connects to it using `POSTGRES_HOST=db`.

Inside the Django container, `localhost` would refer to the Django container itself, not the PostgreSQL container.

**Important:** Once PostgreSQL has initialized its database volume, changing `POSTGRES_PASSWORD` in `.env` does not automatically update the existing database account's password. Choose the password before starting the containers for the first time.

#### Step 5: Configure Web Push Notifications

EldVatten uses VAPID keys to authenticate browser push notifications. These keys can be generated using Node.js.

1. Open PowerShell in the project directory and run:

   `npx web-push generate-vapid-keys`

2. Copy the generated public and private keys into your `.env` file:

   ```dotenv
   VAPID_PUBLIC_KEY=your-generated-public-key
   VAPID_PRIVATE_KEY=your-generated-private-key
   VAPID_SUBJECT=mailto:your-email@example.com
   ```

3. Replace the example email with your own contact email address.

4. Save `.env` and restart the application:

   `docker compose up -d --force-recreate web`

**Important:** Keep your private key secret and never commit it to GitHub. Retain your keys between restarts, since changing them may require users to subscribe to notifications again.

**Optional:** Leave these variables empty if you do not need to test real Web Push notifications during local development.

#### Step 6: Save and verify your configuration

Save the `.env` file using `Ctrl + S`.

Before continuing, confirm:

- [ ] `.env` exists in the repository root, alongside `compose.yaml`.
- [ ] `DJANGO_SECRET_KEY` contains a generated secret instead of the placeholder. This is for you to generate/create yourself.
- [ ] `DJANGO_DEBUG=True`.
- [ ] `DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1`.
- [ ] `POSTGRES_DB=eldvatten`.
- [ ] `POSTGRES_USER=eldvatten`.
- [ ] `POSTGRES_PASSWORD` contains your chosen password.
- [ ] `POSTGRES_HOST=db`.
- [ ] `POSTGRES_PORT=5432`.
- [ ] VAPID settings are left empty unless needed.

You can check whether Docker Compose recognizes your configuration by running:

```powershell
docker compose config --quiet
```

If the command finishes without errors, Docker Compose has successfully parsed its configuration. This does not yet verify that Django can connect to PostgreSQL.

**Security reminder:** `.env` contains passwords and security keys. It should remain on your development machine and must never be committed to GitHub. The project's `.gitignore` is intended to exclude it. One or both of us will get notified if your forget this by github themself. *PAY ATTENTION TO THIS*


### 4. Start the application

From the repository root:

```powershell
docker compose config
docker compose up --build -d
docker compose ps
```

The `web` service runs the Django development server on port `8000`; `db` runs PostgreSQL. If the database is still starting, allow it to become ready before migrating.

```powershell
docker compose exec web python manage.py migrate
docker compose exec web python manage.py check
docker compose exec web python manage.py createsuperuser
```

`createsuperuser` is for setting up an administrative login on a clean development database.

### 5. Open the application

| Destination | URL |
| --- | --- |
| Public homepage | <http://localhost:8000/> |
| Member login | <http://localhost:8000/accounts/login/> |
| Django admin | <http://localhost:8000/admin/> |

*AT THIS POINT, THE APPLICATION SHOULD BE ACCESSIBLE LOCALLY IF DOCKER, THE .ENV IS CONFIGURED, AND ALL MIGRATIONS HAVE SUCCESSFULLY BEEN COMPLETED. IF IT IS NOT, SOMETHING IS WRONG, REACH OUT TO GITHUB OWNER*

## Development data

Management commands in `core/management/commands/` populate a **disposable development database** with fictional accounts and application records.

### Seed data

Start with the main seeder, which creates fictional accounts, organizational memberships, roles, permissions, and supporting data:

```powershell
docker compose exec web python manage.py seed_dev_data
```

Then run the domain seeders you need:

| Command | Creates |
| --- | --- |
| `seed_action_data` | Actions and assignments |
| `seed_event_data` | Events and scheduling records |
| `seed_forum_data` | Tavern Categories, Boards, Threads, and Posts |
| `seed_resource_data` | Resources |
| `seed_voting_data` | Voting scenarios |

```powershell
docker compose exec web python manage.py seed_action_data
docker compose exec web python manage.py seed_event_data
docker compose exec web python manage.py seed_forum_data
docker compose exec web python manage.py seed_resource_data
docker compose exec web python manage.py seed_voting_data
```

The domain seeders can be run individually when their supporting records are already present. Use the main seeder first on a new database.

### Development accounts

| Account | Password | Purpose |
| --- | --- | --- |
| `suTest` | `testpassword` | Development superuser |
| `testuser01`–`testuser52` | `Eldvatten!123_` | Fictional member accounts |

The accounts have varied statuses, memberships, permissions, ranks, and leadership assignments for testing. **These credentials are for disposable development data only.**

### Maintenance commands

| Command | Purpose |
| --- | --- |
| `cleanup_orphaned_resource_files` | Identifies or cleans up files no longer associated with Resources |
| `cleanup_submission_throttles` | Cleans up expired submission-throttling records |

Maintenance commands are not seeders. Review their available options and effects before running them.

> **Data safety:** Seeders modify the connected database. Do not run them against production, real member information, or a shared database you need to preserve. The development seeder expects Django's debug/development configuration.

## Testing

### Django tests

Run the complete backend regression suite:

```powershell
docker compose exec web python manage.py test
```

The full suite is substantial. To test a specific area while developing, run an individual app or a group of related apps:

```powershell
docker compose exec web python manage.py test accounts
docker compose exec web python manage.py test organization
docker compose exec web python manage.py test notifications
docker compose exec web python manage.py test accounts messaging notifications organization audit
```

Django normally creates and removes a separate test database. The PostgreSQL user must have permission to create it. Backend tests cover models, services, authorization, validation, workflows, notifications, and auditing; they do not replace browser acceptance testing.

### Playwright setup

Install Node dependencies and browser binaries from the repository root:

```powershell
npm ci
npx playwright install
```

On Linux, Playwright may also need system packages:

```bash
npx playwright install --with-deps
```

Playwright authentication setup (`e2e/auth.setup.ts`) uses three seeded accounts. Create `.env.playwright` in the repository root:

```dotenv
E2E_SUTEST_PASSWORD=testpassword
E2E_TESTUSER01_PASSWORD=Eldvatten!123_
E2E_TESTUSER02_PASSWORD=Eldvatten!123_
```

Update the values if your development passwords differ. The file and the generated authentication states under `playwright/.auth/` contain credentials; do not commit or share them.

### Run browser tests

Start Django and PostgreSQL before running Playwright:

```powershell
npx playwright test --project=setup
npx playwright test --project=chromium
npx playwright test --project=firefox
npx playwright test --project=webkit
```

For a visible browser, add `--headed`, for example:

```powershell
npx playwright test --project=chromium --headed
```

The Tavern acceptance suite is in `e2e/tavern-suite.spec.ts` and requires an explicit mutation flag:

```powershell
$env:E2E_TAVERN_MUTATIONS = "1"
npx playwright test e2e/tavern-suite.spec.ts --project=chromium --headed
```

**Mutating browser tests must run only against a disposable development database.** The flag permits mutations; it does not make the connected database safe to modify. Some suites use Docker Compose to manage fixtures.

### Reports and debugging

```powershell
npx playwright show-report
npx playwright show-trace path/to/trace.zip
```

Test artifacts may be created under `test-results/`. The Playwright VS Code extension can also run and debug individual tests. Some suites require seeded accounts and organizational permissions; an empty database with a new superuser may not suffice.

## Development commands and tooling

Run these commands from the repository root:

| Task | Command |
| --- | --- |
| Start containers | `docker compose up -d` |
| Stop containers, retain data | `docker compose down` |
| Rebuild containers | `docker compose up --build -d` |
| Check container status | `docker compose ps` |
| Follow Django logs | `docker compose logs -f web` |
| Follow database logs | `docker compose logs -f db` |
| Open Django shell | `docker compose exec web python manage.py shell` |
| Run Django checks | `docker compose exec web python manage.py check` |
| Check for missing migrations | `docker compose exec web python manage.py makemigrations --check --dry-run` |
| Generate migrations | `docker compose exec web python manage.py makemigrations` |
| Apply migrations | `docker compose exec web python manage.py migrate` |

The development Compose configuration mounts the checkout into the Django container at `/app`, so most Python, template, CSS, and JavaScript changes do not require an image rebuild. Rebuild after changing dependencies or the Dockerfile.

**Database persistence:** `docker compose down` preserves volumes. `docker compose down -v` removes Compose-managed volumes, including PostgreSQL data. Only use `-v` when intentionally discarding the development database.

### Recommended VS Code extensions

| Extension | ID | Purpose |
| --- | --- | --- |
| Python | `ms-python.python` | Python support and debugging |
| Pylance | `ms-python.vscode-pylance` | Language analysis |
| Docker | `ms-azuretools.vscode-docker` | Container tools |
| Playwright Test | `ms-playwright.playwright` | Browser test execution |
| Django | `batisteo.vscode-django` | Template editing |

Install these through the Extensions panel or `code --install-extension <extension-id>`.

## Troubleshooting

| Problem | What to check |
| --- | --- |
| Docker does not start | Docker Desktop/Engine, `docker compose version`, and WSL 2 on Windows |
| Missing `Dockerfile` | `compose.yaml` uses `build: .`; obtain the root Dockerfile from the maintainer if absent |
| Database connection fails | `docker compose ps`, `docker compose logs db`, and `POSTGRES_HOST=db` |
| Port 8000 is busy | Stop the other process or update the port mapping and Playwright `baseURL` |
| Playwright login fails | Running app, seeded users, correct `.env.playwright`, matching passwords |
| Browser binaries missing | `npx playwright install` |
| Browser tests lack fixtures | Run appropriate seeders against disposable development data |
| Local files differ from GitHub | Use `git status` to identify uncommitted or unpushed changes |

For real Web Push troubleshooting, check notification permission, service-worker registration, valid VAPID keys, browser push-service support, and outbound network connectivity. Simulated push tests do not verify delivery by external push services.

## Contributing and security

Create a focused branch, keep changes scoped to the relevant domain, run affected Django and browser tests, and review changes before committing or opening a pull request.

```powershell
git switch -c feature/example-change
git add .
git diff --cached
git commit -m "feat(Templates:community): updated thread_detail to contain drafts link"
git push -u origin feature/example-change
```

Use the repository's established commit-message convention. Check `git status` and staged diffs for sensitive or accidental files.

**Never commit:**

- `.env`, `.env.playwright`, VAPID private keys, or other secrets
- Playwright authentication states (`playwright/.auth/`)
- Production database dumps or real member records
- Private uploaded media
- Test reports containing sensitive information

## Production deployment

The development Compose configuration is **not** suitable for public production use as-is.

The planned production environment uses Linux, PostgreSQL, Gunicorn, nginx, and Cloudflare, with HTTPS, hardened Django settings, static-file delivery, protected private media, logging, monitoring, health checks, backups, restore procedures, and production Web Push credentials.

```text
Browser → Cloudflare → nginx → Gunicorn → Django → PostgreSQL
```

Deployment validation must include authentication, authorization, private file access, trusted-proxy configuration, browser compatibility, push delivery, and a tested backup restoration procedure.

Run Django's deployment checks **under production settings**:

```powershell
docker compose exec web python manage.py check --deploy
```

A passing deployment check alone does not establish that the environment is secure or production-ready.

## License and copyright

Copyright © 2026 McGregor Systems LLC. All rights reserved.

This software is proprietary. Copying, modification, distribution, sublicensing, or use outside the terms authorized by the copyright holder is prohibited. Access to the repository does not, by itself, grant a license to use or distribute its contents.
