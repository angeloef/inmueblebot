"""
Google Calendar Service for InmuebleBot.
Manages appointment scheduling through Google Calendar API.
"""
import os
import json
from datetime import datetime, timedelta, timezone as tz
from typing import Optional, List, Dict, Any
from uuid import UUID
from loguru import logger

from app.core.config import get_settings


class CalendarService:
    """
    Google Calendar API integration for scheduling visits.
    
    Uses OAuth2 with stored tokens (client_secrets.json + token.json).
    """
    
    def __init__(self):
        self._credentials = None
        self._service = None
        self._calendar_id = None
        self._token_path = "/app/credentials/token.json"
        self._client_secrets_path = "/app/credentials/client_secrets.json"
    
    @property
    def is_configured(self) -> bool:
        """Check if Google Calendar is configured."""
        return os.path.exists(self._client_secrets_path) and os.path.exists(self._token_path)
    
    def _get_calendar_id(self) -> Optional[str]:
        """Get the calendar ID."""
        return "primary"
    
    def _load_token(self):
        """Load OAuth token from file."""
        if os.path.exists(self._token_path):
            with open(self._token_path, 'r') as f:
                return json.load(f)
        return None
    
    def _build_service(self):
        """Build Google Calendar service using OAuth2."""
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build
        
        if not os.path.exists(self._client_secrets_path):
            logger.warning("[Calendar] client_secrets.json not found")
            return None
        
        token_data = self._load_token()
        if not token_data:
            logger.warning("[Calendar] token.json not found or empty")
            return None
        
        try:
            credentials = Credentials.from_authorized_user_info(
                token_data,
                scopes=['https://www.googleapis.com/auth/calendar']
            )
            
            service = build('calendar', 'v3', credentials=credentials, cache_discovery=False)
            self._calendar_id = self._get_calendar_id()
            logger.info("[Calendar] Service initialized with OAuth2")
            return service
        except Exception as e:
            logger.error(f"[Calendar] Failed to initialize OAuth2 service: {e}")
            return None
            self._calendar_id = self._get_calendar_id()
            logger.info(f"[Calendar] Service initialized for calendar: {self._calendar_id}")
            return service
        except Exception as e:
            logger.error(f"[Calendar] Failed to initialize service: {e}")
            return None
    
    @property
    def service(self):
        if self._service is None:
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
            
            events_result = self.service.events().list(
                calendarId=self._calendar_id,
                timeMin=time_min,
                timeMax=time_max,
                singleEvents=True,
                orderBy='startTime'
            ).execute()
            
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
                    'timeZone': 'America/Asuncion'
                },
                'end': {
                    'dateTime': end_time.isoformat(),
                    'timeZone': 'America/Asuncion'
                },
                'reminders': {
                    'useDefault': False,
                    'overrides': [
                        {'method': 'email', 'minutes': 60},
                        {'method': 'popup', 'minutes': 30}
                    ]
                }
            }
            
            created_event = self.service.events().insert(
                calendarId=self._calendar_id,
                body=event
            ).execute()
            
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
            event = self.service.events().get(
                calendarId=self._calendar_id,
                eventId=event_id
            ).execute()
            
            event['start']['dateTime'] = new_start_time.isoformat()
            event['end']['dateTime'] = new_end_time.isoformat()
            
            if notes:
                event['description'] = f"{event.get('description', '')}\n\nReprogramado: {notes}"
            
            updated = self.service.events().update(
                calendarId=self._calendar_id,
                eventId=event_id,
                body=event
            ).execute()
            
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
            event = self.service.events().get(
                calendarId=self._calendar_id,
                eventId=event_id
            ).execute()
            
            event['description'] = f"{event.get('description', '')}\n\n❌ CANCELADO: {reason or 'Sin reason especificada'}"
            event['status'] = 'cancelled'
            
            updated = self.service.events().update(
                calendarId=self._calendar_id,
                eventId=event_id,
                body=event
            ).execute()
            
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
            
            events_result = self.service.events().list(
                calendarId=self._calendar_id,
                timeMin=now,
                timeMax=future,
                maxResults=max_results,
                singleEvents=True,
                orderBy='startTime'
            ).execute()
            
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
                
                events_result = self.service.events().list(
                    calendarId=self._calendar_id,
                    timeMin=time_min,
                    timeMax=time_max,
                    singleEvents=True,
                    maxResults=1
                ).execute()
                
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
        """Parse date and time strings into datetime object."""
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
        
        return dt.replace(hour=hour, minute=minute, second=0, tzinfo=tz.utc)


calendar_service = CalendarService()