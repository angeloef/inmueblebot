from typing import Optional
from datetime import datetime
import httpx


class CalendarClient:
    def __init__(self, credentials: Optional[dict] = None):
        self.credentials = credentials

    async def create_event(
        self,
        title: str,
        start_time: datetime,
        end_time: datetime,
        description: Optional[str] = None,
        attendees: Optional[list[str]] = None
    ) -> dict:
        if not self.credentials:
            return {"status": "disabled"}

        event = {
            "summary": title,
            "description": description,
            "start": {"dateTime": start_time.isoformat()},
            "end": {"dateTime": end_time.isoformat()},
            "attendees": [{"email": email} for email in (attendees or [])]
        }

        return {"status": "created", "event": event}

    async def delete_event(self, event_id: str) -> dict:
        return {"status": "deleted"}


calendar_client = CalendarClient()