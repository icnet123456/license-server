# License Server

Flask + PostgreSQL license server with:

- online license activation
- trial devices
- admin dashboard
- PostgreSQL persistence

## Required Environment Variables

- `DATABASE_URL`
- `ADMIN_USERNAME`
- `ADMIN_PASSWORD`

## Admin Dashboard

Open:

`/admin/licenses`

## Main APIs

- `POST /api/create-license`
- `POST /api/check-license`
- `POST /api/check-device`
- `POST /api/start-trial`
- `POST /api/check-trial`
