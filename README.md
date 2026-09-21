# EldvattenWebApp

A private community operations web app for the Eldvatten SCA group.

The project supports community communication, event coordination, governance, membership management, organization records, notifications, and administrative workflows in one self-hosted system.

The project is being developed as a volunteer effort and is intended to run on a Linux server owned by the group.


## Technology

The application uses a conventional server-rendered web stack focused on maintainability and long-term handoff:

- Django 5.2
- PostgreSQL 17
- Django templates
- HTML
- CSS
- Vanilla JavaScript
- Docker Compose
- Linux deployment
- Gunicorn
- nginx
- Cloudflare in front of the public server


## Application Structure

### Identity and Access

The application maintains Eldvatten user accounts and organization records.

Access is controlled by backend-enforced permissions and organization membership. Relevant organization data includes:

- citizenship status
- chapters
- households
- offices
- social ranks
- governance bodies
- orders
- community groups
- household leadership

Administrative access is separate from normal member access.


### The Tavern

The Tavern is Eldvatten's internal discussion forum.

Its structure is:

Category
└── Board
    └── Thread
        └── Post

The Tavern supports or is being built to support:

categories and boards
threads and posts
unread tracking
thread and board subscriptions
targeted visibility
targeted thread-creation permissions
pinned threads
locked boards and threads
archived content
thread movement
post movement
thread merging and splitting
post editing
post reporting
quotes
link attachments
drafts
search
notifications
moderation
audit logging

Forum access can be restricted using existing Eldvatten organization data rather than a separate forum-specific permission system.

Events

The event system is separate from Tavern discussions.

Events are structured application objects rather than forum posts. Event functionality is intended to support event coordination and related member workflows.

Actions

Actions are structured tasks or responsibilities that require member attention.

They remain separate from Tavern discussions so actionable work does not become buried in forum content.

Notifications

The notification system surfaces changes and items that require user attention.

Notifications can link users back to the authoritative object, such as a Forum thread, event, action, or other application record.

Messaging

The application includes direct and group messaging.

Messaging is separate from The Tavern and is intended for conversations that do not belong in persistent community discussion.

Messages must not be treated as private or end-to-end encrypted communication. The user interface will make this clear to users.

Audit and Administration

Important administrative and moderation changes are recorded through the audit system.

Audit records are intended to provide accountability for actions such as:

creation
editing
movement
locking
archiving
restoration
moderation
other administrative changes

Administrative activity within the application must not be assumed to be private.

Public Website

A public-facing Eldvatten website is planned.

Its content and structure will require additional input from Eldvatten leadership before implementation is finalized.

Development Status

The core application architecture, identity system, organization models, permissions, notifications, messaging infrastructure, audit system, and substantial Tavern backend functionality are in place.

Current development work is focused on completing the Tavern forum interface and integrating its existing backend capabilities into the final user experience.

Development will continue across the following major areas:

Identity and access
Organization, groups, offices, chapters, households, and governance
Public website
Tavern forum
Events
Actions
Notifications
Messaging
Audit and administrative tooling
Archive and export tooling
Accessibility, responsive behavior, testing, deployment, and system hardening
Deployment

The production system is intended to be self-hosted on Eldvatten-controlled Linux infrastructure.

The planned production request path is approximately:

User
  ↓
Cloudflare
  ↓
nginx
  ↓
Gunicorn
  ↓
Django
  ↓
PostgreSQL

Application services are managed through Docker Compose.

Project Priorities

The project favors:

maintainability
clear architecture
backend-enforced permissions
conventional and widely understood technology
minimal unnecessary dependencies
long-term handoff to future maintainers
accessibility
auditable administrative actions
separation between discussion content and structured business data
Copyright

Copyright © 2026 McGregor Systems LLC
All rights reserved.

This source code is proprietary and may not be copied,
modified, distributed, sublicensed, or used outside the
terms expressly authorized by the copyright holder.
