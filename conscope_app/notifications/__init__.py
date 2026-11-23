"""Transactional email delivery building blocks; no automatic monitoring hook."""

from .models import AlertEmailContext, DeliveryFailure, DeliveryResult, EmailMessage, RenderedEmail
from .service import NotificationService
from .resend import ResendEmailProvider

__all__ = [
    "AlertEmailContext",
    "DeliveryFailure",
    "DeliveryResult",
    "EmailMessage",
    "NotificationService",
    "RenderedEmail",
    "ResendEmailProvider",
]
