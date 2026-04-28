"""
Tests para las tareas de Celery.
Ejecutar: pytest tests/test_tasks.py -v
"""
import pytest


class TestCeleryApp:
    """Tests para la configuración de Celery."""
    
    def test_celery_app_exists(self):
        """Verifica que la app de Celery existe."""
        from celery_app import celery_app
        assert celery_app is not None
    
    def test_beat_schedule_exists(self):
        """Verifica que el beat schedule está configurado."""
        from celery_app import celery_app
        schedule = celery_app.conf.beat_schedule
        assert "check-upcoming-appointments" in schedule
        assert "daily-property-followups" in schedule
        assert "nightly-lead-scoring" in schedule
    
    def test_celery_uses_redis(self):
        """Verifica que Celery usa Redis."""
        from celery_app import celery_app
        assert "redis" in celery_app.conf.broker_url


class TestNotificationService:
    """Tests para el servicio de notificaciones."""
    
    def test_notification_service_exists(self):
        """Verifica que el servicio existe."""
        from app.services.notification_service import notification_service
        assert notification_service is not None
    
    def test_send_whatsapp_method_exists(self):
        """Verifica que el método existe."""
        from app.services.notification_service import NotificationService
        assert hasattr(NotificationService, "send_whatsapp_message")


__all__ = ["TestCeleryApp", "TestNotificationService"]