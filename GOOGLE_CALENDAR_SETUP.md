# Google Calendar Integration Setup Guide

## Overview

This guide explains how to set up Google Calendar integration for InmuebleBot, allowing the inmobiliaria to manage property visit appointments directly from their Google Calendar.

## Architecture

```
User → WhatsApp/Streamlit → InmuebleBot → Google Calendar API
                                            ↓
                                    Real-time sync
                                            ↓
                                    InmuebleBot Calendar
                                            ↓
                                    Your Google Calendar
```

## Setup Steps

### 1. Create a Google Cloud Project

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project or select an existing one
3. Enable the Google Calendar API:
   - Go to "APIs & Services" → "Library"
   - Search for "Google Calendar API"
   - Click "Enable"

### 2. Create a Service Account

A service account allows server-to-server authentication without user login.

1. Go to "APIs & Services" → "Credentials"
2. Click "Create Credentials" → "Service Account"
3. Give it a name (e.g., "InmuebleBot Calendar")
4. Click "Done"

### 3. Generate Service Account Key

1. Click on your new service account
2. Go to "Keys" tab
3. Click "Add Key" → "JSON"
4. Download the JSON file
5. Save it securely (this is your credentials file)

### 4. Share Your Google Calendar with the Service Account

1. Open Google Calendar in your browser
2. Click the gear icon → "Settings"
3. Go to "Integrate calendar" → "Calendar ID"
4. Copy your Calendar ID (or use "primary" for main calendar)
5. Share the calendar with the service account email:
   - In Google Calendar, click "Share with specific people"
   - Add the service account email (found in the JSON file under `client_email`)
   - Give "Make changes to events" permissions

### 5. Configure InmuebleBot

1. Copy the downloaded JSON file to your server:
   ```bash
   mkdir -p /app/credentials
   cp downloaded-service-account.json /app/credentials/google-service-account.json
   ```

2. Update your `.env` file:
   ```env
   GOOGLE_CREDENTIALS_PATH=/app/credentials/google-service-account.json
   GOOGLE_CALENDAR_ID=your-calendar-id@example.com
   ```

3. Rebuild the Docker container:
   ```bash
   docker-compose build app
   docker-compose up -d
   ```

## Testing the Integration

### Test 1: Check if Calendar is Configured

```bash
docker-compose exec app python -c "
from app.services.calendar_service import calendar_service
print('Calendar configured:', calendar_service.is_configured)
"
```

### Test 2: Get Upcoming Events

```bash
docker-compose exec app python -c "
import asyncio
from app.services.calendar_service import calendar_service

async def test():
    events = await calendar_service.get_upcoming_events(days_ahead=7)
    print(f'Found {len(events)} upcoming events')
    for e in events[:3]:
        print(f'  - {e.get(\"summary\")}: {e.get(\"start\")}')

asyncio.run(test())
"
```

### Test 3: Check Availability

```bash
docker-compose exec app python -c "
import asyncio
from app.services.calendar_service import calendar_service

async def test():
    result = await calendar_service.check_availability(
        property_id=1,
        date_str='2026-04-25',
        time_str='10:00',
        duration_hours=1
    )
    print(f'Available: {result.get(\"available\")}')
    if not result.get('available'):
        print(f'Conflicts: {result.get(\"conflicting_events\")}')

asyncio.run(test())
"
```

### Test 4: Create a Test Event

```bash
docker-compose exec app python -c "
import asyncio
from datetime import datetime, timezone
from app.services.calendar_service import calendar_service

async def test():
    start = datetime(2026, 4, 25, 10, 0, tzinfo=timezone.utc)
    end = datetime(2026, 4, 25, 11, 0, tzinfo=timezone.utc)
    
    result = await calendar_service.create_visit_event(
        user_phone='+595981234567',
        property_id=1,
        property_title='Casa de prueba',
        start_time=start,
        end_time=end,
        notes='Test de integración'
    )
    
    if result.get('success'):
        print(f'Event created: {result.get(\"event_id\")}')
        print(f'Link: {result.get(\"html_link\")}')
    else:
        print(f'Error: {result.get(\"error\")}')

asyncio.run(test())
"
```

## User Experience Flow

### When a User Wants to Book a Visit:

1. User: "Quiero agendar una visita para mañana a las 10am"
2. Bot: Checks Google Calendar availability
3. Bot: "Sí, hay disponible. ¿Quieres confirmar?"
4. User: "Sí"
5. Bot: Creates appointment + Google Calendar event
6. Bot: "¡Cita agendada! [Link a Google Calendar]"

### When the Inmobiliaria Manages Availability:

1. They can block time slots directly in Google Calendar
2. InmuebleBot will automatically see those as unavailable
3. They can move/reschedule visits in Google Calendar
4. Changes sync back to InmuebleBot

## Troubleshooting

### Error: "Calendar not configured"

- Check `GOOGLE_CREDENTIALS_PATH` is set correctly
- Verify the JSON file exists at that path
- Check Docker volume mount: `volumes: - ./credentials:/app/credentials`

### Error: "Permission denied"

- The service account email needs access to the calendar
- Share the calendar with the service account email found in the JSON file

### Error: "Calendar is busy"

- There's already an event at that time
- The time slot conflicts with an existing Google Calendar event

## Sharing Calendar with the Inmobiliaria

The inmobiliaria can:
1. Open their Google Calendar
2. See all scheduled visits
3. Block time slots they don't want visitors
4. Move/reschedule visits directly
5. Add personal events (marked as "busy" will appear as unavailable)

## Security Considerations

- The service account JSON file contains sensitive credentials
- Store it securely and don't commit to git
- Use Docker volumes to mount the file
- Set appropriate file permissions: `chmod 600 credentials.json`

## API Reference

### CalendarService Methods

```python
# Check if a time slot is available
calendar_service.check_availability(property_id, date_str, time_str)

# Get available time slots for a date
calendar_service.get_available_slots(date_str, start_hour=9, end_hour=18)

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