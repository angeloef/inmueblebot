"""
Modelos de la base de datos.
Exporta todos los modelos ORM para uso convenient.
"""
from app.db.models.user import User
from app.db.models.property import Property
from app.db.models.conversation import Conversation
from app.db.models.message import Message
from app.db.models.appointment import Appointment

__all__ = [
    "User",
    "Property",
    "Conversation",
    "Message",
    "Appointment",
]