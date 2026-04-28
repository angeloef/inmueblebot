"""
Celery Application Configuration.
Configures Celery with Redis as broker and result backend.
Includes beat schedule for periodic tasks.
"""
from celery import Celery
from celery.schedules import crontab
from loguru import logger

from app.core.config import get_settings


settings = get_settings()

# Celery configuration
celery_app = Celery(
    "inmueblebot",
    broker=settings.REDIS_URL.replace("redis://", "redis://"),
    backend=settings.REDIS_URL.replace("redis://", "redis://"),
    include=[
        "app.tasks.reminders",
        "app.tasks.followups",
        "app.tasks.lead_scoring",
    ]
)

# Configuration options
celery_app.conf.update(
    # Task settings
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="America/Asuncion",
    enable_utc=True,
    
    # Retry settings
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    task_default_retry_delay=60,  # 1 minute
    task_max_retries=3,
    
    # Result backend settings
    result_expires=3600,  # 1 hour
    result_persistent=True,
    
    # Worker settings
    worker_prefetch_multiplier=1,
    worker_max_tasks_per_child=1000,
    
    # Beat schedule
    beat_schedule={
        # Check appointments every 30 minutes for upcoming reminders
        "check-upcoming-appointments": {
            "task": "app.tasks.reminders.check_upcoming_appointments",
            "schedule": 1800.0,  # 30 minutes
        },
        
        # Daily follow-ups at 10 AM
        "daily-property-followups": {
            "task": "app.tasks.followups.send_property_followups",
            "schedule": crontab(hour=10, minute=0),
        },
        
        # Inactive user follow-ups at 11 AM
        "daily-inactive-followups": {
            "task": "app.tasks.followups.send_inactive_user_followups",
            "schedule": crontab(hour=11, minute=0),
        },
        
        # Nightly lead scoring at 2 AM
        "nightly-lead-scoring": {
            "task": "app.tasks.lead_scoring.update_all_lead_scores",
            "schedule": crontab(hour=2, minute=0),
        },
        
        # Clean old sessions daily at 3 AM
        "cleanup-old-sessions": {
            "task": "app.tasks.maintenance.cleanup_old_sessions",
            "schedule": crontab(hour=3, minute=0),
        },
    },
)

# Log startup
logger.info(f"Celery app configured with broker: {settings.REDIS_URL}")

if __name__ == "__main__":
    celery_app.start()
