# SaaS Backend — Production-Ready Multi-Tenant Django REST API

A fully production-ready multi-tenant SaaS backend built with **Django**, **Django REST Framework**, **PostgreSQL**, **Redis**, and **Celery**.

---

## 🏗 Architecture

```
saas_backend/
├── config/                     # Django project config
│   ├── settings/
│   │   ├── base.py             # Shared settings
│   │   ├── dev.py              # Development overrides
│   │   └── prod.py             # Production hardening
│   ├── urls.py                 # Root URL configuration
│   ├── wsgi.py
│   └── asgi.py
├── apps/
│   ├── core/                   # Shared base models, pagination, exceptions, permissions, mixins
│   ├── users/                  # Custom User model + JWT auth
│   ├── organizations/          # Multi-tenant Organizations + Memberships
│   ├── tasks/                  # Task management (CRUD, assign, status, comments, tags)
│   └── notifications/          # Event-driven notification system + Celery tasks
├── services/                   # Business logic layer (thin views, fat services)
│   ├── auth_service.py
│   ├── organization_service.py
│   ├── task_service.py
│   └── notification_service.py
├── middleware/
│   └── tenant_middleware.py    # Resolves Organization from every request
├── celery_app/
│   └── celery.py               # Celery application + autodiscovery
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
└── manage.py
```

---

## ⚙️ Tech Stack

| Layer | Technology |
|---|---|
| Framework | Django 4.2 + DRF 3.15 |
| Auth | SimpleJWT (access + refresh + blacklist) |
| Database | PostgreSQL 15 |
| Cache / Broker | Redis 7 |
| Task Queue | Celery 5.4 + django-celery-beat |
| API Docs | drf-spectacular (Swagger + ReDoc) |
| Container | Docker + Docker Compose |

---

## 🚀 Quick Start

### With Docker (recommended)

```bash
# 1. Clone and configure
cp .env.example .env
# Edit .env with your values

# 2. Build and start all services
docker compose up --build

# 3. Create a superuser
docker compose exec web python manage.py createsuperuser

# 4. Open API docs
open http://localhost:8000/api/docs/
```

### Without Docker

```bash
# 1. Create a virtual environment
python -m venv venv
source venv/bin/activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure environment
cp .env.example .env
# Edit DB_HOST, REDIS_URL, etc.

# 4. Run migrations
python manage.py migrate

# 5. Create superuser
python manage.py createsuperuser

# 6. Start dev server
python manage.py runserver

# 7. Start Celery worker (separate terminal)
celery -A celery_app worker --loglevel=info

# 8. Start Celery beat (separate terminal)
celery -A celery_app beat --loglevel=info
```

---

## 🔑 API Overview

All endpoints are versioned under `/api/v1/`.

Interactive docs: `http://localhost:8000/api/docs/`

### Authentication

| Method | Endpoint | Description |
|---|---|---|
| POST | `/api/v1/auth/register/` | Register new user |
| POST | `/api/v1/auth/login/` | Obtain JWT tokens |
| POST | `/api/v1/auth/token/refresh/` | Refresh access token |
| POST | `/api/v1/auth/logout/` | Blacklist refresh token |

### Users

| Method | Endpoint | Description |
|---|---|---|
| GET | `/api/v1/users/me/` | Get my profile |
| PATCH | `/api/v1/users/me/update/` | Update my profile |
| POST | `/api/v1/users/me/change-password/` | Change password |

### Organizations

| Method | Endpoint | Description |
|---|---|---|
| GET | `/api/v1/organizations/` | List my organizations |
| POST | `/api/v1/organizations/` | Create organization |
| GET | `/api/v1/organizations/{id}/` | Get organization |
| PATCH | `/api/v1/organizations/{id}/` | Update organization (admin only) |
| DELETE | `/api/v1/organizations/{id}/` | Delete organization (owner only) |

### Members

Pass `X-Organization-Slug: <slug>` header to resolve the tenant.

| Method | Endpoint | Description |
|---|---|---|
| GET | `/api/v1/members/` | List members |
| POST | `/api/v1/members/invite/` | Invite member (admin) |
| PATCH | `/api/v1/members/{id}/role/` | Change role (admin) |
| DELETE | `/api/v1/members/{id}/remove/` | Remove member (admin) |
| POST | `/api/v1/members/leave/` | Leave organization |

### Tasks

Pass `X-Organization-Slug: <slug>` header to resolve the tenant.

| Method | Endpoint | Description |
|---|---|---|
| GET | `/api/v1/tasks/` | List tasks (filterable) |
| POST | `/api/v1/tasks/` | Create task |
| GET | `/api/v1/tasks/{id}/` | Get task detail |
| PATCH | `/api/v1/tasks/{id}/` | Update task |
| DELETE | `/api/v1/tasks/{id}/` | Delete task |
| PATCH | `/api/v1/tasks/{id}/status/` | Update status |
| PATCH | `/api/v1/tasks/{id}/assign/` | Assign task |
| POST | `/api/v1/tasks/{id}/comments/` | Add comment |
| GET | `/api/v1/tasks/{id}/comments/list/` | List comments |
| GET | `/api/v1/tasks/stats/` | Task statistics |

**Task filters:** `?status=todo&priority=high&assigned_to=<uuid>&is_overdue=true`

### Notifications

| Method | Endpoint | Description |
|---|---|---|
| GET | `/api/v1/notifications/` | List notifications (`?unread=true`) |
| GET | `/api/v1/notifications/stats/` | Unread count |
| POST | `/api/v1/notifications/mark-read/` | Mark as read |
| DELETE | `/api/v1/notifications/clear-read/` | Delete read notifications |
| GET | `/api/v1/notifications/preferences/` | Get preferences |
| PATCH | `/api/v1/notifications/preferences/update/` | Update preferences |

---

## 🏢 Multi-Tenancy

Every request is resolved to an `Organization` (tenant) via the `TenantMiddleware`.

**Resolution order:**
1. `X-Organization-Slug` request header *(preferred)*
2. `?org=<slug>` query parameter
3. JWT token `organization_slug` claim

All data models include an `organization` FK. The `TenantQuerysetMixin` automatically filters querysets so users can only see data in their org.

---

## 🔐 RBAC

| Role | Capabilities |
|---|---|
| **Admin** | Full access: manage members, update org, assign/delete any task |
| **Member** | Read org data, create/manage own tasks, view all tasks |

---

## ⚡ Celery Tasks

| Task | Trigger | Description |
|---|---|---|
| `send_email_notification` | On every notification | Sends email to recipient |
| `send_bulk_notification` | System announcements | Fan-out to all org members |
| `cleanup_old_notifications` | Periodic (daily) | Deletes read notifications > 90 days |
| `send_overdue_task_notifications` | Periodic (every 4h) | Notifies assignees of overdue tasks |

---

## 🧪 Running Tests

```bash
# Install test dependencies
pip install pytest pytest-django factory-boy

# Run all tests
pytest

# With coverage
pytest --cov=apps --cov=services --cov-report=html
```

---

## 🔧 Environment Variables

See `.env.example` for all available configuration options.

Key variables:

```
SECRET_KEY          Django secret key
DEBUG               True/False
DB_*                PostgreSQL connection
REDIS_URL           Redis connection
CELERY_BROKER_URL   Celery broker (Redis)
JWT_ACCESS_TOKEN_LIFETIME_MINUTES
JWT_REFRESH_TOKEN_LIFETIME_DAYS
```

---

## 📊 Admin Panel

Available at `/admin/` — all models are registered with rich list displays, filters, search, and inline editing.

---

## 🌐 API Documentation

- **Swagger UI**: `http://localhost:8000/api/docs/`
- **ReDoc**: `http://localhost:8000/api/redoc/`
- **OpenAPI Schema**: `http://localhost:8000/api/schema/`

---

## 🐳 Services (Docker Compose) 

| Service | Port | Description |
|---|---|---|
| `web` | 8000 | Django + Gunicorn |
| `db` | 5432 | PostgreSQL 15 |
| `redis` | 6379 | Redis 7 |
| `celery_worker` | — | Celery worker |
| `celery_beat` | — | Celery periodic scheduler |
| `flower` | 5555 | Celery monitoring UI |
