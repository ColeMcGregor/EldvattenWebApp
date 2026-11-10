# EldvattenWebApp

A self-hosted community management and communication platform for the EldVatten SCA group.

EldvattenWebApp provides a centralized system for community discussions, messaging, events, governance, membership management, notifications, and administrative operations.

The application uses a server-rendered architecture and is designed for long-term maintainability, security, and self-hosted deployment.

## Technology Stack

| Component | Technology |
|---|---|
| Backend | Python 3.13, Django 5.2 |
| Database | PostgreSQL 17 |
| Frontend | Django Templates, HTML, CSS, Vanilla JavaScript |
| Application Server | Gunicorn |
| Reverse Proxy | nginx |
| Containers | Docker, Docker Compose |
| Hosting | Linux |
| External Networking | Cloudflare |
| Browser Testing | Playwright |

## Features

### Identity and Access Management

- User registration and authentication
- Membership approval and account management
- Role-based access control (RBAC)
- Backend-enforced permissions
- Organizational membership and affiliations
- Administrative account management

### Organization Management

Organizational records include:

- Citizenship classes and social ranks
- Chapters and households
- Offices and leadership positions
- Governance bodies
- Orders and ranks
- Community groups
- Membership and sponsorship records

Organizational data supports permission checks and targeted content visibility across the application.

### The Tavern

The Tavern is the community's internal discussion forum.

Forum hierarchy:

```text
Category
└── Board
    └── Thread
        └── Post
```

Features include:

- Category, board, thread, and post management
- Targeted visibility and thread-creation permissions
- Unread tracking and subscriptions
- Thread pinning and locking
- Content archiving and restoration
- Thread and post movement
- Thread merging and splitting
- Post editing, quoting, and reporting
- Link attachments and drafts
- Search and moderation
- Notifications and audit logging

### Events and Calendar

- Event creation and management
- Event visibility and invitation targeting
- Member invitations and RSVP tracking
- Attendance recording
- Calendar-based event organization

### Actions

- Structured task and responsibility management
- Member and organization-based assignments
- Assignment tracking and completion status
- Deadlines and required actions
- Links to relevant Tavern discussions

### Messaging

- Direct messaging
- Group conversations
- Conversation membership management
- User blocking
- Conversation muting
- Message notifications

Messages are application-managed and are not end-to-end encrypted.

### Voting and Governance

- Vote creation and management
- Eligibility targeting
- Voting options and ballots
- Anonymous and identified voting
- Quorum and approval rules
- Vote opening, closing, and result tracking

### Resources

- Resource library
- File uploads and external links
- Organization-based visibility controls
- Private file storage and permission-checked access
- Administrative resource management

### Notifications

- In-app notifications
- Web push notifications
- Notifications linked to relevant application records
- Member attention and activity tracking

### Administration and Audit Logging

- Administrative interfaces
- Member and organization management
- Moderation tools
- Audit logging for significant application operations
- Audit history, filtering, and record inspection
- Administrative access controls

### Public Website

The public-facing website provides general information about EldVatten, separate from the authenticated community application.

## Architecture

The application uses a Django modular monolith with separate application modules for major functional areas.

The primary application directories include:

```text
accounts/
actions/
administration/
audit/
community/
core/
events/
messaging/
notifications/
organization/
resources/
voting/
```

Django handles application logic, permissions, routing, database access, and server-rendered templates.

PostgreSQL provides persistent storage for application and organizational data.

Production traffic follows this general architecture:

```text
Client Browser
     |
     v
Cloudflare
     |
     v
nginx
     |
     v
Gunicorn
     |
     v
Django
     |
     v
PostgreSQL
```

Application services are containerized and managed through Docker Compose.

## Testing

The project includes Django automated tests and Playwright browser tests.

Django tests cover application logic, permissions, data models, and backend functionality.

Playwright tests cover browser-level application workflows, including authentication, administrative operations, and audit verification.

Run the Django test suite:

```bash
docker compose exec web python manage.py test
```

Run Playwright tests from the project directory after installing the Node.js development dependencies and starting the application:

```bash
npx playwright install
npx playwright test --project=chromium
```

Playwright uses test accounts and credentials configured in `.env.playwright`. Run tests that modify application data against a dedicated development or test database.

## Local Development with Docker

The following instructions describe how to run EldvattenWebApp locally using Docker Compose.

### Prerequisites

Install the following software:

- Git
- Docker Engine with Docker Compose, or Docker Desktop
- Node.js and npm for Playwright browser testing

Docker handles the Python, Django, and PostgreSQL environments. A separate local Python or PostgreSQL installation is not required.

### 1. Clone the Repository

```bash
git clone https://github.com/ColeMcGregor/EldvattenWebApp.git
cd EldvattenWebApp
```

### 2. Configure Environment Variables

Copy the example environment configuration into a local `.env` file:

```bash
cp .env.example .env
```

On Windows PowerShell:

```powershell
Copy-Item .env.example .env
```

Configure the environment variables in `.env`:

```dotenv
DJANGO_SECRET_KEY=replace-with-a-unique-secret-key
DJANGO_DEBUG=True
DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1

POSTGRES_DB=eldvatten
POSTGRES_USER=eldvatten
POSTGRES_PASSWORD=replace-with-a-local-password
POSTGRES_HOST=db
POSTGRES_PORT=5432

VAPID_PUBLIC_KEY=your-vapid-public-key
VAPID_PRIVATE_KEY=your-vapid-private-key
VAPID_SUBJECT=mailto:your-email@example.com
```

Use a unique Django secret key and database password. Configure valid VAPID credentials when testing web push notifications.

The `.env` file contains local secrets and must not be committed to version control.

### 3. Build and Start the Containers

From the repository root:

```bash
docker compose up --build -d
```

Docker Compose builds the Django application image, starts PostgreSQL, and starts the Django development server.

The local Compose configuration exposes the application on port `8000`.

Check container status:

```bash
docker compose ps
```

View application logs:

```bash
docker compose logs -f web
```

### 4. Initialize the Database

Apply the Django database migrations:

```bash
docker compose exec web python manage.py migrate
```

This initializes the database schema and applies the application's migrations.

### 5. Create an Administrator Account

```bash
docker compose exec web python manage.py createsuperuser
```

Follow the prompts to create a local superuser.

### 6. Start Using the Application

Open the application in a browser:

http://localhost:8000/

The Django administrative interface is available at:

http://localhost:8000/admin/

Sign in using the superuser credentials created in the previous step.

### 7. Running Development Commands

Run Django management commands inside the `web` container.

For example, to run the automated Django tests:

```bash
docker compose exec web python manage.py test
```

To open a Django shell:

```bash
docker compose exec web python manage.py shell
```

To generate migrations after model changes:

```bash
docker compose exec web python manage.py makemigrations
```

Apply them with:

```bash
docker compose exec web python manage.py migrate
```

### 8. Development Workflow

The local Docker Compose configuration mounts the repository into the Django container.

Changes to application files are therefore available inside the container without rebuilding the image for every source-code modification.

Rebuild the image after modifying container configuration or Python dependencies:

```bash
docker compose up --build -d
```

Django's development server handles application reloads during normal development.

### 9. Stopping the Application

Stop the running containers:

```bash
docker compose down
```

The PostgreSQL database uses a persistent Docker volume, so application data survives normal container shutdowns and restarts.

To completely reset the local container environment, including its database volume:

```bash
docker compose down -v
```

**Warning:** The `-v` option removes the project's persistent Docker volumes and deletes the local database data.

### Local Development Notes

- Docker Compose provides the local application and database environment.
- nginx and Cloudflare are not required for local development.
- The local Compose configuration uses Django's development server rather than the production Gunicorn configuration.
- Development environment variables should not be reused for production.
- Never use real member information in disposable development databases.
- Browser tests that create, modify, or delete records should run against dedicated test data.

## License and Copyright

Copyright © 2026 McGregor Systems LLC. All rights reserved.

This software is proprietary. Copying, modification, distribution, sublicensing, or use outside the terms authorized by the copyright holder is prohibited.

Access to the repository does not grant a license to use or distribute its contents.