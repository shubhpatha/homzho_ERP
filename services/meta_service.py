"""
services/meta_service.py - Meta Conversion API Integration
Sends server-side events to Meta when a Lead converts.
"""
import time
import hashlib
import requests
from flask import current_app

def hash_data(data: str) -> str:
    """Hash data using SHA256 as required by Meta CAPI."""
    if not data:
        return ""
    return hashlib.sha256(data.strip().lower().encode('utf-8')).hexdigest()

def send_conversion_event(lead_or_customer, event_name="Lead"):
    """
    Send an event to the Meta Conversion API.
    Fails silently if META_ACCESS_TOKEN or META_PIXEL_ID is missing.
    """
    pixel_id = current_app.config.get('META_PIXEL_ID')
    access_token = current_app.config.get('META_ACCESS_TOKEN')
    
    if not pixel_id or not access_token:
        current_app.logger.debug("Meta Conversion API skipped: missing credentials in config.")
        return False
        
    url = f"https://graph.facebook.com/v18.0/{pixel_id}/events"
    
    # We try to extract email and phone depending on if it's a Lead or Customer object
    email = getattr(lead_or_customer, 'email_id', '')
    phone = getattr(lead_or_customer, 'contact_number', '')
    
    user_data = {}
    if email:
        user_data['em'] = hash_data(email)
    if phone:
        user_data['ph'] = hash_data(''.join(filter(str.isdigit, phone)))

    if not user_data:
        current_app.logger.warning("Meta CAPI skipped: No email or phone to hash.")
        return False

    payload = {
        "data": [
            {
                "event_name": event_name,
                "event_time": int(time.time()),
                "action_source": "website",
                "user_data": user_data,
                "custom_data": {
                    "currency": "INR",
                    "value": getattr(lead_or_customer, 'monthly_rent', 0)
                }
            }
        ],
        "access_token": access_token
    }

    try:
        response = requests.post(url, json=payload, timeout=5)
        response.raise_for_status()
        current_app.logger.info(f"Meta CAPI {event_name} event sent successfully.")
        return True
    except Exception as e:
        current_app.logger.error(f"Meta CAPI Error: {e}")
        return False
