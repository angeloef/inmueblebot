# Google Calendar Integration Setup Guide

## Overview

This guide explains how to set up Google Calendar integration for InmuebleBot, allowing property visit appointments to sync with Google Calendar.

The system uses **OAuth 2.0** (not service accounts) for Google Calendar access. Credentials are loaded from:

1. **Render Secret Files** (`/etc/secrets/token.json` + `/etc/secrets/client_secrets.json`) — **recommended for production**
2. **Environment variables** (`GOOGLE_TOKEN_JSON` + `GOOGLE_CREDENTIALS_JSON`) — alternative for Render dashboard
3. **Local files** (`credentials/token.json` + `credentials/client_secrets.json`) — local development only

## Architecture

```
User → WhatsApp → InmuebleBot → Google Calendar API (OAuth 2.0)
                                      ↓
                              Appointment in DB + Calendar event
                                      ↓
                              Real-time sync across dashboard
```

**Three-layer sync:** Local DB appointment ↔ Google Calendar event ↔ Dashboard display.

## Prerequisites

1. A Google Cloud Project with the Calendar API enabled
2. OAuth 2.0 credentials (client_secrets.json) from Google Cloud Console
3. An OAuth token (token.json) obtained through the OAuth flow

## Setup Steps

### 1. Create a Google Cloud Project

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project or select an existing one
3. Enable the Google Calendar API:
   - Go to "APIs & Services" → "Library"
   - Search for "Google Calendar API"
   - Click "Enable"

### 2. Create OAuth 2.0 Credentials

1. Go to "APIs & Services" → "Credentials"
2. Click "Create Credentials" → "OAuth client ID"
3. Choose "Desktop application" (or "Web application" with `http://localhost:8000` as redirect URI)
4. Download the JSON file and save it as `credentials/client_secrets.json`

### 3. Obtain the OAuth Token

```bash
# Run the OAuth flow locally to generate token.json
python -c "
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
import os, json

SCOPES = ['https://www.googleapis.com/auth/calendar']
creds = None

# Check if token exists
if os.path.exists('credentials/token.json'):
    with open('credentials/token.json', 'r') as f:
        creds = json.load(f)
    from google.oauth2.credentials import Credentials
    creds = Credentials.from_authorized_user_info(creds, SCOPES)

# Refresh or create
if creds and creds.expired and creds.refresh_token:
    creds.refresh(Request())
elif not creds or not creds.valid:
    flow = InstalledAppFlow.from_client_secrets_file('credentials/client_secrets.json', SCOPES)
    creds = flow.run_local_server(port=0)

# Save
token_data = {
    'token': creds.token,
    'refresh_token': creds.refresh_token,
    'token_uri': creds.token_uri,
    'client_id': creds.client_id,
    'client_secret': creds.client_secret,
    'scopes': creds.scopes,
    'expiry': creds.expiry.isoformat(),
}
with open('credentials/token.json', 'w') as f:
    json.dump(token_data, f, indent=2)
print('✅ token.json generated')
"
```

### 4. Production Deployment on Render

**Option A: Render Secret Files (recommended)**

1. In Render Dashboard → your app → **Environment** → **Secret Files**
2. Create file `token.json` with the **entire contents** of your local `credentials/token.json`
3. Create file `client_secrets.json` with the **entire contents** of your local `credentials/client_secrets.json`
4. The service looks for these at `/etc/secrets/token.json` and `/etc/secrets/client_secrets.json`

**Option B: Environment Variables (alternative)**

1. In Render Dashboard → **Environment Variables**, add:
   - `GOOGLE_TOKEN_JSON` → paste entire contents of `credentials/token.json`
   - `GOOGLE_CREDENTIALS_JSON` → paste entire contents of `credentials/client_secrets.json`
   - Set both to `sync: false` (manage in dashboard, not in repo)

### 5. Local Development

For local dev, just ensure both files exist:
```bash
ls -la credentials/
# Should show: client_secrets.json  token.json
```

The service resolves paths in this priority:
1. `GOOGLE_TOKEN_PATH` / `GOOGLE_CREDENTIALS_PATH` env var
2. `/etc/secrets/<file>` (Render Secret Files)
3. `/app/credentials/<file>` (Docker container path)
4. `<project_root>/credentials/<file>` (local dev, gitignored)

## Testing the Integration

### Check if Calendar is Configured

```bash
cd /mnt/c/Users/angelo/Documents/alemai/inmueblebot
python3 -c "
from app.services.calendar_service import calendar_service
print('Calendar configured:', calendar_service.is_configured)
"
```

### Create a Test Event

```bash
cd /mnt/c/Users/angelo/Documents/alemai/inmueblebot
python3 -c "
import asyncio
from datetime import datetime, timezone
from app.services.calendar_service import calendar_service

async def test():
    start = datetime(2026, 5, 25, 10, 0, tzinfo=timezone.utc)
    end = datetime(2026, 5, 25, 11, 0, tzinfo=timezone.utc)
    result = await calendar_service.create_visit_event(
        user_phone='+595****4567',
        property_id=1,
        property_title='Casa de prueba',
        start_time=start,
        end_time=end,
        notes='Test'
    )
    if result.get('success'):
        print(f'Event created: {result.get(\"event_id\")}')
    else:
        print(f'Error: {result.get(\"error\")}')

asyncio.run(test())
"
```

## User Experience Flow

### When a User Wants to Book a Visit:

1. User: "Quiero agendar una visita para mañana a las 10am"
2. Bot: Checks local DB + Google Calendar availability
3. Bot: "Sí, hay disponible. ¿Quieres confirmar?"
4. User: "Sí"
5. Bot: Creates appointment in DB + Google Calendar event
6. Bot: "¡Cita agendada! [detalles]"

If Google Calendar is not configured, the bot:
- Still creates the appointment in the local DB
- Shows a note: "⚠️ La sincronización con el calendario no está disponible"
- Logs a warning for operators

### When the Inmobiliaria Manages Availability:

1. They can block time slots directly in Google Calendar
2. InmuebleBot will automatically see those as unavailable
3. They can move/reschedule visits in Google Calendar
4. Changes sync back to InmuebleBot (via calendar_event_id)

## Security

- **NEVER** commit `token.json` or `client_secrets.json` to git (both are `.gitignore`d)
- On Render, use **Secret Files** (mounted at `/etc/secrets/`) — never paste credentials in code
- Online token refresh is encrypted via HTTPS to Google's OAuth endpoints
- If a token is compromised, revoke it at: https://myaccount.google.com/permissions
- The `credentials/` directory is in `.gitignore` and should not be tracked

## Troubleshooting

### "Calendar not configured"
- Check that files exist at one of the supported paths
- On Render, verify Secret Files were created correctly
- Check logs: `[Calendar] NOT CONFIGURED` message tells you what's missing

### "Token expired" — Auto-refresh should handle this
The service auto-refreshes tokens when they expire:
- If refresh fails, delete `token.json` and re-run the OAuth flow
- On Render, upload a fresh `token.json` via Secret Files

### OAuth token refresh fails
- The `client_secrets.json` might be mismatched with the token
- Re-run the OAuth flow to generate fresh credentials
- Ensure the Google Cloud project still has the Calendar API enabled

## API Reference

```python
# Check if calendar is configured (env vars, files, or both)
calendar_service.is_configured  # -> bool

# Reset cached service (e.g., after uploading new credentials)
calendar_service.reset()

# Check if a time slot is available
calendar_service.check_availability(property_id, date_str, time_str)

# Create a visit event
calendar_service.create_visit_event(
    user_phone, property_id, property_title,
    start_time, end_time, notes
)

# Reschedule a visit
calendar_service.reschedule_visit(event_id, new_start_time, new_end_time)

# Cancel a visit
calendar_service.cancel_visit(event_id, reason)

# Get upcoming events
calendar_service.get_upcoming_events(days_ahead=7)
```

## Configuration Reference (config.py)

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `GOOGLE_TOKEN_PATH` | `Optional[str]` | `None` | Path to token.json (env var override) |
| `GOOGLE_CREDENTIALS_PATH` | `Optional[str]` | `None` | Path to client_secrets.json (env var override) |
| `GOOGLE_CALENDAR_ID` | `str` | `"primary"` | Calendar ID to use |
| `GOOGLE_TOKEN_JSON` | `Optional[str]` | `None` | Entire token.json as JSON string (env var) |
| `GOOGLE_CREDENTIALS_JSON` | `Optional[str]` | `None` | Entire client_secrets.json as JSON string (env var) |

## render.yaml Configuration

```yaml
envVars:
  - key: GOOGLE_TOKEN_JSON
    sync: false     # Set in Render dashboard
  - key: GOOGLE_CREDENTIALS_JSON
    sync: false     # Set in Render dashboard
```
