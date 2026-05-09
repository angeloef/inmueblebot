"""
Google Calendar Service for InmuebleBot.
Manages appointment scheduling through Google Calendar API.
"""
import os
import json
import asyncio
from datetime import datetime, timedelta, timezone as tz
from typing import Optional, List, Dict, Any
from loguru import logger
import pytz

from app.core.config import get_settings


class CalendarService:
    """
    Google Calendar API integration for scheduling visits.
    
    Uses OAuth2 with stored tokens (client_secrets.json + token.json).
    All API calls are executed in a thread pool to avoid blocking the event loop.
    """
    
    def __init__(self):
        self._credentials = None
        self._service = None
        self._calendar_id = None
        self._token_path = None
        self._client_secrets_path = None
        self._resolve_credential_paths()
    
    def reset(self):
        """Reset cached service so it re-initializes on next access. Call this when credentials might have changed."""
        self._service = None
        self._credentials = None
        self._resolve_credential_paths()
        logger.info("[Calendar] Service cache reset — will re-initialize on next access")

    def _resolve_credential_paths(self):
        """
        Resolve credential file paths from settings (with local-dev fallback).

        Priority:
        1. Settings-provided path (GOOGLE_TOKEN_PATH / GOOGLE_CREDENTIALS_PATH from .env)
        2. /app/credentials/<file> (Docker container path)
        3. /etc/secrets/<file> (Render Secret Files mount point)
        4. Relative to project root (local dev outside Docker)
        """
        settings = get_settings()
        
        # Resolve token path
        token_candidates = []
        if settings.GOOGLE_TOKEN_PATH:
            token_candidates.append(settings.GOOGLE_TOKEN_PATH)
        token_candidates.append("/app/credentials/token.json")
        token_candidates.append("/etc/secrets/token.json")
        token_candidates.append("/etc/secrets/google_token.json")
        
        # Local dev fallback
        py_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.abspath(os.path.join(py_dir, "..", ".."))
        token_candidates.append(os.path.join(project_root, "credentials", "token.json"))
        
        self._token_path = self._first_existing(token_candidates) or "/app/credentials/token.json"
        
        # Resolve client secrets path
        secrets_candidates = []
        if settings.GOOGLE_CREDENTIALS_PATH:
            secrets_candidates.append(settings.GOOGLE_CREDENTIALS_PATH)
        secrets_candidates.append("/app/credentials/client_secrets.json")
        secrets_candidates.append("/etc/secrets/client_secrets.json")
        secrets_candidates.append("/etc/secrets/google_credentials.json")
        secrets_candidates.append(os.path.join(project_root, "credentials", "client_secrets.json"))
        
        self._client_secrets_path = self._first_existing(secrets_candidates) or "/app/credentials/client_secrets.json"
    
    @staticmethod
    def _first_existing(paths: List[str]) -> Optional[str]:
        """Return the first path that exists on disk, or None."""
        for p in paths:
            if os.path.exists(p):
                return p
        return None
    
    def _load_credentials_from_env(self) -> tuple:
        """Try loading credentials from env vars (Render dashboard) instead of files."""
        settings = get_settings()
        
        # Try GOOGLE_TOKEN_JSON env var (entire token as JSON string)
        token_json = getattr(settings, 'GOOGLE_TOKEN_JSON', None)
        if not token_json:
            token_json = os.environ.get('GOOGLE_TOKEN_JSON')
        
        # Try GOOGLE_CREDENTIALS_JSON env var
        creds_json = getattr(settings, 'GOOGLE_CREDENTIALS_JSON', None)
        if not creds_json:
            creds_json = os.environ.get('GOOGLE_CREDENTIALS_JSON')
        
        return token_json, creds_json
    
    @property
    def is_configured(self) -> bool:
        """Check if Google Calendar is configured (files or env vars)."""
        token_json, creds_json = self._load_credentials_from_env()
        if token_json and creds_json:
            return True
        return os.path.exists(self._client_secrets_path) and os.path.exists(self._token_path)
    
    def _get_calendar_id(self) -> Optional[str]:
        """Get the calendar ID."""
        return "primary"
    
    async def _execute_async(self, request):
        """Execute a Google API request in a thread pool to avoid blocking the event loop."""
        return await asyncio.to_thread(request.execute)
    
    def _load_token(self):
        """Load OAuth token from file."""
        if os.path.exists(self._token_path):
            with open(self._token_path, 'r') as f:
                return json.load(f)
        return None
    
    def _save_token(self, credentials) -> None:
        """Save OAuth credentials to token file after refresh."""
        from google.oauth2.credentials import Credentials
        if isinstance(credentials, Credentials):
            token_data = {
                'token': credentials.token,
                'refresh_token': credentials.refresh_token,
                'token_uri': credentials.token_uri,
                'client_id': credentials.client_id,
                'client_secret': credentials.client_secret,
                'scopes': credentials.scopes,
                'expiry': credentials.expiry.isoformat() if credentials.expiry else None,
            }
            with open(self._token_path, 'w') as f:
                json.dump(token_data, f, indent=2)
            logger.info("[Calendar] Saved refreshed token")
    
    def _build_service(self):
        """Build Google Calendar service using OAuth2."""
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build
        
        # Try file-based credentials first
        token_data = None
        client_secrets_loaded = os.path.exists(self._client_secrets_path)
        
        if client_secrets_loaded:
            token_data = self._load_token()
        
        # Fall back to env var credentials if files don't exist
        if not token_data or not client_secrets_loaded:
            token_json, creds_json = self._load_credentials_from_env()
            if token_json and creds_json:
                logger.info("[Calendar] Loading credentials from environment variables")
                try:
                    token_data = json.loads(token_json)
                    # Mark as loaded from env var so we proceed
                    client_secrets_loaded = True
                except json.JSONDecodeError as e:
                    logger.error(f"[Calendar] Failed to parse GOOGLE_TOKEN_JSON env var: {e}")
                    return None
            else:
                if not client_secrets_loaded:
                    logger.warning("[Calendar] client_secrets.json not found")
                if not token_data:
                    logger.warning("[Calendar] No token found (files or env vars)")
                logger.warning(
                    f"[Calendar] NOT CONFIGURED — appointments will be DB-only. "
                    f"To enable: set GOOGLE_CREDENTIALS_JSON + GOOGLE_TOKEN_JSON env vars "
                    f"or place files at {self._client_secrets_path} and {self._token_path}"
                )
                return None
        
        try:
            credentials = Credentials.from_authorized_user_info(
                token_data,
                scopes=['https://www.googleapis.com/auth/calendar']
            )
            
            # Refresh token if expired
            if credentials.expired and credentials.refresh_token:
                import google.auth.transport.requests
                credentials.refresh(google.auth.transport.requests.Request())
                self._save_token(credentials)
                logger.info("[Calendar] OAuth token refreshed")
            
            service = build('calendar', 'v3', credentials=credentials, cache_discovery=False)
            self._calendar_id = self._get_calendar_id()
            logger.info("[Calendar] Service initialized with OAuth2")
            return service
        except Exception as e:
            logger.error(f"[Calendar] Failed to initialize OAuth2 service: {e}")
            return None
    
    @property
    def service(self):
        if self._service is None:
            self._service = self._build_service()
            if self._service is None:
                # Try one more time with fresh path resolution (files might have appeared)
                self._resolve_credential_paths()
                self._service = self._build_service()
        return self._service
    
    async def check_availability(
        self,
        property_id: int,
        date_str: str,
        time_str: str = "10:00",
        duration_hours: int = 1
    ) -> Dict[str, Any]:
        """
        Check if a time slot is available in Google Calendar.
        
        Args:
            property_id: ID of the property
            date_str: Date in format "YYYY-MM-DD" or "DD/MM/YYYY"
            time_str: Time in "HH:MM" format
            duration_hours: Duration of the visit
            
        Returns:
            Dict with:
            - available: bool
            - start_time: datetime
            - end_time: datetime  
            - conflicting_events: List of conflicting events (if any)
        """
        if not self.service:
            return {"available": True, "error": "Calendar not configured"}
        
        try:
            start_dt = self._parse_datetime(date_str, time_str)
            end_dt = start_dt + timedelta(hours=duration_hours)
            
            time_min = start_dt.isoformat()
            time_max = end_dt.isoformat()
            
            events_result = await self._execute_async(
                self.service.events().list(
                    calendarId=self._calendar_id,
                    timeMin=time_min,
                    timeMax=time_max,
                    singleEvents=True,
                    orderBy='startTime'
                )
            )
            
            events = events_result.get('items', [])
            
            if events:
                return {
                    "available": False,
                    "start_time": start_dt,
                    "end_time": end_dt,
                    "conflicting_events": [
                        {
                            "summary": e.get("summary", "Sin título"),
                            "start": e.get("start", {}),
                            "end": e.get("end", {})
                        }
                        for e in events
                    ]
                }
            
            return {
                "available": True,
                "start_time": start_dt,
                "end_time": end_dt,
                "conflicting_events": []
            }
            
        except Exception as e:
            logger.error(f"[Calendar] Error checking availability: {e}")
            return {"available": True, "error": str(e)}
    
    async def create_visit_event(
        self,
        user_phone: str,
        property_id: int,
        property_title: str,
        start_time: datetime,
        end_time: datetime,
        notes: str = None
    ) -> Dict[str, Any]:
        """
        Create a Google Calendar event for a property visit.
        
        Args:
            user_phone: User's WhatsApp number
            property_id: ID of the property
            property_title: Title of the property
            start_time: Visit start time
            end_time: Visit end time
            notes: Optional notes
            
        Returns:
            Dict with:
            - success: bool
            - event_id: Google Calendar event ID
            - html_link: Link to the event
            - error: Error message (if any)
        """
        if not self.service:
            return {"success": False, "error": "Calendar not configured"}
        
        try:
            event = {
                'summary': f'🏠 Visita: {property_title}',
                'description': (
                    f'Visita programada por InmuebleBot\n'
                    f'Cliente: {user_phone}\n'
                    f'Propiedad ID: {property_id}\n'
                    f'Notas: {notes or "Sin notas"}'
                ),
                'start': {
                    'dateTime': start_time.isoformat(),
                    'timeZone': 'America/Argentina/Buenos_Aires'
                },
                'end': {
                    'dateTime': end_time.isoformat(),
                    'timeZone': 'America/Argentina/Buenos_Aires'
                },
                'reminders': {
                    'useDefault': False,
                    'overrides': [
                        {'method': 'email', 'minutes': 60},
                        {'method': 'popup', 'minutes': 30}
                    ]
                }
            }
            
            created_event = await self._execute_async(
                self.service.events().insert(
                    calendarId=self._calendar_id,
                    body=event
                )
            )
            
            logger.info(f"[Calendar] Created event: {created_event.get('id')}")
            
            return {
                "success": True,
                "event_id": created_event.get('id'),
                "html_link": created_event.get('htmlLink'),
                "summary": created_event.get('summary')
            }
            
        except Exception as e:
            logger.error(f"[Calendar] Error creating event: {e}")
            return {"success": False, "error": str(e)}
    
    async def reschedule_visit(
        self,
        event_id: str,
        new_start_time: datetime,
        new_end_time: datetime,
        notes: str = None
    ) -> Dict[str, Any]:
        """
        Reschedule a Google Calendar event.
        
        Args:
            event_id: Google Calendar event ID
            new_start_time: New start time
            new_end_time: New end time
            notes: Optional notes to add
            
        Returns:
            Dict with success status and updated event info
        """
        if not self.service:
            return {"success": False, "error": "Calendar not configured"}
        
        try:
            event = await self._execute_async(
                self.service.events().get(
                    calendarId=self._calendar_id,
                    eventId=event_id
                )
            )
            
            event['start']['dateTime'] = new_start_time.isoformat()
            event['end']['dateTime'] = new_end_time.isoformat()
            
            if notes:
                event['description'] = f"{event.get('description', '')}\n\nReprogramado: {notes}"
            
            updated = await self._execute_async(
                self.service.events().update(
                    calendarId=self._calendar_id,
                    eventId=event_id,
                    body=event
                )
            )
            
            logger.info(f"[Calendar] Rescheduled event: {event_id}")
            
            return {
                "success": True,
                "event_id": updated.get('id'),
                "html_link": updated.get('htmlLink')
            }
            
        except Exception as e:
            logger.error(f"[Calendar] Error rescheduling event: {e}")
            return {"success": False, "error": str(e)}
    
    async def cancel_visit(
        self,
        event_id: str,
        reason: str = None
    ) -> Dict[str, Any]:
        """
        Cancel a Google Calendar event.
        
        Args:
            event_id: Google Calendar event ID
            reason: Reason for cancellation
            
        Returns:
            Dict with success status
        """
        if not self.service:
            return {"success": False, "error": "Calendar not configured"}
        
        try:
            event = await self._execute_async(
                self.service.events().get(
                    calendarId=self._calendar_id,
                    eventId=event_id
                )
            )
            
            event['description'] = f"{event.get('description', '')}\n\n❌ CANCELADO: {reason or 'Sin razón especificada'}"
            event['status'] = 'cancelled'
            
            updated = await self._execute_async(
                self.service.events().update(
                    calendarId=self._calendar_id,
                    eventId=event_id,
                    body=event
                )
            )
            
            logger.info(f"[Calendar] Cancelled event: {event_id}")
            
            return {"success": True}
            
        except Exception as e:
            logger.error(f"[Calendar] Error cancelling event: {e}")
            return {"success": False, "error": str(e)}
    
    async def get_upcoming_events(
        self,
        days_ahead: int = 7,
        max_results: int = 50
    ) -> List[Dict[str, Any]]:
        """
        Get upcoming events from the calendar.
        
        Args:
            days_ahead: Number of days to look ahead
            max_results: Maximum number of events to return
            
        Returns:
            List of event dictionaries
        """
        if not self.service:
            return []
        
        try:
            now = datetime.now(tz.utc).isoformat()
            future = (datetime.now(tz.utc) + timedelta(days=days_ahead)).isoformat()
            
            events_result = await self._execute_async(
                self.service.events().list(
                    calendarId=self._calendar_id,
                    timeMin=now,
                    timeMax=future,
                    maxResults=max_results,
                    singleEvents=True,
                    orderBy='startTime'
                )
            )
            
            events = events_result.get('items', [])
            return [
                {
                    "id": e.get('id'),
                    "summary": e.get('summary'),
                    "description": e.get('description'),
                    "start": e.get('start', {}).get('dateTime'),
                    "end": e.get('end', {}).get('dateTime'),
                    "status": e.get('status')
                }
                for e in events
                if e.get('status') != 'cancelled'
            ]
            
        except Exception as e:
            logger.error(f"[Calendar] Error getting events: {e}")
            return []
    
    async def get_available_slots(
        self,
        date_str: str,
        start_hour: int = 9,
        end_hour: int = 18,
        duration_hours: int = 1
    ) -> List[Dict[str, str]]:
        """
        Get available time slots for a given date.
        
        Args:
            date_str: Date in "YYYY-MM-DD" format
            start_hour: Business day start hour (default 9)
            end_hour: Business day end hour (default 18)
            duration_hours: Duration of each slot (default 1)
            
        Returns:
            List of available time slots:
            [{"time": "10:00", "available": True}, ...]
        """
        if not self.service:
            return []
        
        try:
            from datetime import time as dt_time
            
            base_date = datetime.strptime(date_str, "%Y-%m-%d").date()
            slots = []
            
            for hour in range(start_hour, end_hour):
                slot_start = datetime.combine(base_date, dt_time(hour))
                slot_end = slot_start + timedelta(hours=duration_hours)
                
                time_min = slot_start.isoformat()
                time_max = slot_end.isoformat()
                
                events_result = await self._execute_async(
                    self.service.events().list(
                        calendarId=self._calendar_id,
                        timeMin=time_min,
                        timeMax=time_max,
                        singleEvents=True,
                        maxResults=1
                    )
                )
                
                events = events_result.get('items', [])
                slots.append({
                    "time": f"{hour:02d}:00",
                    "available": len(events) == 0,
                    "start": slot_start.isoformat(),
                    "end": slot_end.isoformat()
                })
            
            return slots
            
        except Exception as e:
            logger.error(f"[Calendar] Error getting slots: {e}")
            return []
    
    def _parse_datetime(self, date_str: str, time_str: str = "10:00") -> datetime:
        """Parse date and time strings into datetime object with Argentina/Asunción timezone."""
        formats = ["%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"]
        
        dt = None
        for fmt in formats:
            try:
                dt = datetime.strptime(date_str, fmt)
                break
            except ValueError:
                continue
        
        if dt is None:
            raise ValueError(f"Unable to parse date: {date_str}")
        
        time_parts = time_str.split(":")
        hour = int(time_parts[0])
        minute = int(time_parts[1]) if len(time_parts) > 1 else 0
        
        ba_tz = pytz.timezone("America/Argentina/Buenos_Aires")
        return ba_tz.localize(dt.replace(hour=hour, minute=minute, second=0))


calendar_service = CalendarService()
