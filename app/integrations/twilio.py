"""
Twilio WhatsApp Integration for InmuebleBot.

This module provides:
- Sending text messages
- Sending images
- Sending interactive buttons
- Verifying webhook signatures
- Parsing incoming WhatsApp messages
"""

import logging
from typing import Optional, List, Dict, Any
from dataclasses import dataclass

from twilio.rest import Client
from twilio.base.exceptions import TwilioRestException

from config.settings import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


@dataclass
class WhatsAppMessage:
    """Parsed incoming WhatsApp message."""
    phone: str           # User's phone number (with country code)
    message_id: str     # Twilio message SID
    body: str           # Message text
    media_url: Optional[str] = None  # Media URL if present
    message_type: str = "text"      # text, image, audio, video, button


class TwilioWhatsAppClient:
    """Client for sending WhatsApp messages via Twilio."""
    
    def __init__(self):
        self.account_sid = settings.TWILIO_ACCOUNT_SID
        self.auth_token = settings.TWILIO_AUTH_TOKEN
        self.whatsapp_number = settings.TWILIO_WHATSAPP_NUMBER
        self.verify_token = settings.TWILIO_WEBHOOK_VERIFY_TOKEN
        
        self._client = None
        self._is_configured = False
        
        if self.account_sid and self.auth_token and self.whatsapp_number:
            try:
                self._client = Client(self.account_sid, self.auth_token)
                self._is_configured = True
                logger.info(f"Twilio client initialized for {self.whatsapp_number}")
            except Exception as e:
                logger.error(f"Failed to initialize Twilio client: {e}")
    
    @property
    def is_configured(self) -> bool:
        return self._is_configured
    
    async def send_message(self, to: str, message: str) -> Dict[str, Any]:
        """
        Send a text message via WhatsApp.
        
        Args:
            to: Destination phone number (e.g., 'whatsapp:+5491155555555')
            message: Message text to send
            
        Returns:
            Dict with 'success' bool and 'message_id' or 'error'
        """
        if not self.is_configured:
            return {"success": False, "error": "Twilio not configured"}
        
        try:
            # Format 'to' number with whatsapp: prefix
            if not to.startswith("whatsapp:"):
                to = f"whatsapp:{to}"
            
            result = self._client.messages.create(
                body=message,
                from_=self.whatsapp_number,
                to=to
            )
            
            logger.info(f"Sent WhatsApp message to {to}: {result.sid}")
            return {"success": True, "message_id": result.sid}
            
        except TwilioRestException as e:
            logger.error(f"Twilio error sending message: {e}")
            return {"success": False, "error": str(e)}
        except Exception as e:
            logger.error(f"Unexpected error sending message: {e}")
            return {"success": False, "error": str(e)}
    
    async def send_image(self, to: str, image_url: str, caption: str = "") -> Dict[str, Any]:
        """
        Send an image via WhatsApp.
        
        Args:
            to: Destination phone number
            image_url: URL to the image
            caption: Optional image caption
            
        Returns:
            Dict with 'success' bool and 'message_id' or 'error'
        """
        if not self.is_configured:
            return {"success": False, "error": "Twilio not configured"}
        
        try:
            if not to.startswith("whatsapp:"):
                to = f"whatsapp:{to}"
            
            result = self._client.messages.create(
                body=caption or "Imagen",
                media_url=image_url,
                from_=self.whatsapp_number,
                to=to
            )
            
            logger.info(f"Sent WhatsApp image to {to}: {result.sid}")
            return {"success": True, "message_id": result.sid}
            
        except Exception as e:
            logger.error(f"Error sending image: {e}")
            return {"success": False, "error": str(e)}
    
    async def send_buttons(
        self, 
        to: str, 
        body: str, 
        buttons: List[Dict[str, str]]
    ) -> Dict[str, Any]:
        """
        Send interactive buttons via WhatsApp.
        
        Args:
            to: Destination phone number
            body: Text message above buttons
            buttons: List of {'id': '...', 'title': '...'}
            
        Returns:
            Dict with 'success' bool and 'message_id' or 'error'
        """
        if not self.is_configured:
            return {"success": False, "error": "Twilio not configured"}
        
        try:
            if not to.startswith("whatsapp:"):
                to = f"whatsapp:{to}"
            
            # Build Quick Replies action
            from twilio.twiml import TwimlMessageBuilder
            
            # Twilio WhatsApp interactive uses quick reply buttons
            action = {"buttons": buttons}
            
            # Note: TwiML requires special formatting for interactive
            # For now, we'll send as text with button labels
            button_text = "\n\n".join([b.get("title", "") for b in buttons])
            full_message = f"{body}\n\n{button_text}"
            
            result = self._client.messages.create(
                body=full_message,
                from_=self.whatsapp_number,
                to=to
            )
            
            logger.info(f"Sent interactive buttons to {to}: {result.sid}")
            return {"success": True, "message_id": result.sid}
            
        except Exception as e:
            logger.error(f"Error sending buttons: {e}")
            return {"success": False, "error": str(e)}
    
    def verify_webhook(self, signature: str, url: str, params: dict) -> bool:
        """
        Verify that the request came from Twilio.
        
        Args:
            signature: X-Twilio-Signature header
            url: Full URL of the request
            params: POST params
            
        Returns:
            True if signature is valid
        """
        if not self.verify_token:
            logger.warning("No verify token configured - skipping verification")
            return True
        
        try:
            from twilio.util import RequestValidator
            validator = RequestValidator(self.auth_token)
            return validator.validate(request_url, params, signature)
        except Exception as e:
            logger.error(f"Webhook verification error: {e}")
            return False


# Global client instance
twilio_client = TwilioWhatsAppClient()


# Convenience functions
async def send_whatsapp_message(phone: str, message: str) -> bool:
    """Send a text message. Returns True if successful."""
    result = await twilio_client.send_message(to=phone, message=message)
    return result.get("success", False)


async def send_whatsapp_image(phone: str, image_url: str, caption: str = "") -> bool:
    """Send an image. Returns True if successful."""
    result = await twilio_client.send_image(to=phone, image_url=image_url, caption=caption)
    return result.get("success", False)


async def send_whatsapp_buttons(phone: str, body: str, buttons: List[Dict[str, str]]) -> bool:
    """Send interactive buttons. Returns True if successful."""
    result = await twilio_client.send_buttons(to=phone, body=body, buttons=buttons)
    return result.get("success", False)


def parse_incoming_message(form_data: dict) -> Optional[WhatsAppMessage]:
    """
    Parse incoming WhatsApp message from Twilio webhook.
    
    Args:
        form_data: POST form data from Twilio
        
    Returns:
        WhatsAppMessage object or None if invalid
    """
    # Required fields
    message_sid = form_data.get("MessageSid")
    from_phone = form_data.get("From")
    body = form_data.get("Body", "").strip()
    
    if not message_sid or not from_phone:
        logger.warning("Missing required fields in incoming message")
        return None
    
    # Remove 'whatsapp:' prefix if present
    if from_phone.startswith("whatsapp:"):
        from_phone = from_phone[9:]
    
    # Check for media
    media_url = form_data.get("MediaUrl0")
    msg_type = form_data.get("MediaContentType0", "text")
    
    # Determine message type
    message_type = "text"
    if media_url:
        if "image" in msg_type:
            message_type = "image"
        elif "audio" in msg_type:
            message_type = "audio"
        elif "video" in msg_type:
            message_type = "video"
    
    return WhatsAppMessage(
        phone=from_phone,
        message_id=message_sid,
        body=body,
        media_url=media_url if media_url else None,
        message_type=message_type
    )