"""
Intents del chatbot.
Enumeración de todos los intents posibles que el bot puede reconocer.
"""
from enum import Enum


class Intent(str, Enum):
    """
    Enum de intents del chatbot de bienes raíces.
    """
    GREETING = "greeting"
    PROPERTY_SEARCH = "property_search"
    PROPERTY_DETAILS = "property_details"
    SCHEDULE_APPOINTMENT = "schedule_appointment"
    FAQ = "faq"
    HUMAN_HANDOFF = "human_handoff"
    UNKNOWN = "unknown"


# Descripciones de intents para el LLM
INTENT_DESCRIPTIONS = {
    Intent.GREETING: "El usuario envía un saludo inicial o pregunta de cortesía",
    Intent.PROPERTY_SEARCH: "El usuario busca propiedades con criterios específicos (ubicación, precio, tipo)",
    Intent.PROPERTY_DETAILS: "El usuario pide más información sobre una propiedad específica",
    Intent.SCHEDULE_APPOINTMENT: "El usuario quiere agendar una cita para visitar una propiedad",
    Intent.FAQ: "El usuario hace preguntas generales sobre el servicio, precios, proceso, etc.",
    Intent.HUMAN_HANDOFF: "El usuario pide hablar con un agente humano",
    Intent.UNKNOWN: "El mensaje no puede ser clasificado en ninguna categoría",
}