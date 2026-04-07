# Savings Fund Site

This website is separate from the BMS automation files in the project root.

## Run

From `C:\Users\patel\PycharmProjects\SavingsFundSite`:

```powershell
py -m pip install -r requirements.txt
py manage.py migrate
py manage.py runserver
```

## Render Deploy

Render runs this on Render's servers, so your computer can stay off.

Recommended setup:
- push this repo to GitHub
- create a Render Blueprint from [render.yaml](/abs/path/C:/Users/patel/PycharmProjects/SavingsFundSite/render.yaml)
- let Render create the web service and Postgres database
- set `EDITOR_ACCESS_PASSWORD` in Render before first public use

Render will give you a public URL like:
- `https://usa-mitra-mandal.onrender.com`

After that, you can keep using Codex here on your computer:
- make code changes locally
- commit and push to GitHub
- Render auto-deploys the new version

## Access Without Domain

You can access this from anywhere without buying a domain by hosting it on:
- a VPS with a public IP
- Render, Railway, or any Python app host
- a tunnel like `ngrok` or `cloudflared` for temporary access

Then open it with:
- `http://YOUR_SERVER_IP`
- or the hosting platform URL

## Production Env

Use environment variables from [.env.example](/abs/path/C:/Users/patel/PycharmProjects/SavingsFundSite/.env.example).

Important ones:
- `DJANGO_DEBUG=False`
- `DJANGO_SECRET_KEY=...`
- `DATABASE_URL=...`
- `DJANGO_ALLOWED_HOSTS=YOUR_SERVER_IP`
- `DJANGO_CSRF_TRUSTED_ORIGINS=http://YOUR_SERVER_IP`
- `EDITOR_ACCESS_PASSWORD=9898000`

## Deploy

Linux/server example:

```bash
pip install -r requirements.txt
python manage.py migrate
python manage.py collectstatic --noinput
gunicorn config.wsgi:application --bind 0.0.0.0:8000
```

If you use a reverse proxy like Nginx, point it to port `8000`.

Render example:

1. Push this repo to GitHub.
2. In Render, choose `New +` -> `Blueprint`.
3. Select the repo.
4. Render reads [render.yaml](/abs/path/C:/Users/patel/PycharmProjects/SavingsFundSite/render.yaml) and creates:
   - web service
   - Postgres database
5. In the created web service, set `EDITOR_ACCESS_PASSWORD`.
6. Deploy.

For local development after that, keep using SQLite. Render uses Postgres automatically through `DATABASE_URL`.

## Current Rules

- 18 members
- `$1000` monthly saving installment for each member
- multiple loans can be given in the same month
- loan interest is entered manually for each loan
- the member receives the net amount after interest is deducted upfront
- monthly installments repay principal only
- every borrower starts repayment next month
- all pages are public read-only
- editor changes require the admin password
- current editor password default is `9898000`
- if a member is removed, the exit share is calculated as:
  `(available cash + outstanding installments) / total active members`
