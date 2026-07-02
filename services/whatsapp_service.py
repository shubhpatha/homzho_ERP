"""
services/whatsapp_service.py - Native WhatsApp Link Generator
Generates wa.me links to send messages via the user's local WhatsApp/WhatsApp Web.
"""
import urllib.parse
from flask import current_app

def generate_wa_link(phone_number: str, message: str) -> str:
    """Generate a native wa.me link with prefilled text."""
    # Ensure phone number only contains digits
    clean_phone = ''.join(filter(str.isdigit, phone_number))
    
    # Optional: Add country code if missing (assumes India +91 if length is 10)
    if len(clean_phone) == 10:
        clean_phone = f"91{clean_phone}"
        
    encoded_message = urllib.parse.quote(message)
    return f"https://wa.me/{clean_phone}?text={encoded_message}"

def get_lead_followup_link(lead_name: str, phone: str) -> str:
    """Generate a WhatsApp link for following up with a new lead."""
    message = (
        f"Hi {lead_name},\n\n"
        "Thank you for showing interest in Homzho water purifiers! "
        "Our team will be happy to assist you in choosing the best plan for your needs.\n\n"
        "Please let us know if you have any questions or when would be a good time to call."
    )
    return generate_wa_link(phone, message)

def get_google_review_link(customer_name: str, phone: str) -> str:
    """Generate a WhatsApp link asking for a Google Review."""
    # Get review link from config or use a placeholder if not set
    review_url = current_app.config.get('GOOGLE_REVIEW_LINK', 'https://g.page/review')
    
    message = (
        f"Hi {customer_name},\n\n"
        "Thank you for choosing Homzho! We hope you're satisfied with your new installation/service.\n\n"
        f"Could you take a minute to leave us a quick review? It helps us a lot!\n{review_url}\n\n"
        "Best,\nHomzho Team"
    )
    return generate_wa_link(phone, message)

def get_referral_thank_you_link(referrer_name: str, phone: str, new_customer_name: str) -> str:
    """Generate a WhatsApp link thanking a customer for a referral."""
    message = (
        f"Hi {referrer_name},\n\n"
        f"Thank you so much for referring {new_customer_name} to Homzho! "
        "We truly appreciate your support and trust in our services.\n\n"
        "Best,\nHomzho Team"
    )
    return generate_wa_link(phone, message)
