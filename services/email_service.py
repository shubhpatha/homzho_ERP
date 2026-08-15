"""
services/email_service.py - Manual email sending helpers.
"""
import smtplib
from threading import Thread
from email.message import EmailMessage
from html import escape

from flask import current_app, url_for


def _mail_ready():
    required = ['MAIL_SERVER', 'MAIL_PORT', 'MAIL_USERNAME', 'MAIL_PASSWORD', 'MAIL_DEFAULT_SENDER']
    missing = [key for key in required if not current_app.config.get(key)]
    if missing:
        return False, f"Email is not configured. Missing: {', '.join(missing)}"
    return True, ''


def _send_email(to_email, subject, text_body, html_body=None):
    if not to_email:
        return False, 'No recipient email address is available.'

    ready, message = _mail_ready()
    if not ready:
        current_app.logger.warning(message)
        return False, message

    msg = EmailMessage()
    msg['Subject'] = subject
    msg['From'] = 'Homzho Support <contact@homzho.in>'
    msg['To'] = to_email
    msg.set_content(text_body)
    if html_body:
        msg.add_alternative(html_body, subtype='html')

    try:
        with smtplib.SMTP(current_app.config['MAIL_SERVER'], current_app.config['MAIL_PORT'], timeout=15) as smtp:
            if current_app.config.get('MAIL_USE_TLS', True):
                smtp.starttls()
            smtp.login(current_app.config['MAIL_USERNAME'], current_app.config['MAIL_PASSWORD'])
            smtp.send_message(msg)
        return True, 'Email sent successfully.'
    except Exception as exc:
        current_app.logger.error(f'Email send failed: {exc}', exc_info=True)
        return False, f'Email could not be sent: {exc}'


def _send_prepared_email(app, msg):
    with app.app_context():
        try:
            with smtplib.SMTP(current_app.config['MAIL_SERVER'], current_app.config['MAIL_PORT'], timeout=15) as smtp:
                if current_app.config.get('MAIL_USE_TLS', True):
                    smtp.starttls()
                smtp.login(current_app.config['MAIL_USERNAME'], current_app.config['MAIL_PASSWORD'])
                smtp.send_message(msg)
            current_app.logger.info(f"Background email sent to {msg['To']} with subject {msg['Subject']}")
        except Exception as exc:
            current_app.logger.error(f'Background email send failed: {exc}', exc_info=True)


def _queue_email(to_email, subject, text_body, html_body=None):
    if not to_email:
        return False, 'No recipient email address is available.'

    ready, message = _mail_ready()
    if not ready:
        current_app.logger.warning(message)
        return False, message

    msg = EmailMessage()
    msg['Subject'] = subject
    msg['From'] = 'Homzho Support <contact@homzho.in>'
    msg['To'] = to_email
    msg.set_content(text_body)
    if html_body:
        msg.add_alternative(html_body, subtype='html')

    app = current_app._get_current_object()
    thread = Thread(target=_send_prepared_email, args=(app, msg), daemon=True)
    thread.start()
    return True, 'Email is being sent in the background.'


def _html_shell(title, body):
    return f"""
    <div style="font-family:Arial,sans-serif;color:#101828;line-height:1.55">
      <h2 style="color:#0f4c81">{escape(title)}</h2>
      {body}
      <p style="margin-top:24px">Regards,<br>Homzho Team</p>
    </div>
    """


def send_invoice_email(payment):
    customer = payment.customer
    if not customer:
        return False, 'This payment is not linked to a customer.'

    invoice_url = url_for('payments.view', payment_id=payment.payment_id, _external=True)
    subject = f'Homzho Invoice {payment.invoice_no}'
    text_body = (
        f"Hi {customer.cust_name},\n\n"
        f"Your Homzho invoice {payment.invoice_no} dated {payment.payment_date:%d %b %Y} is ready.\n"
        f"Amount paid: Rs. {payment.amount_paid:,.2f}\n"
        f"Invoice link: {invoice_url}\n\n"
        "Regards,\nHomzho Team"
    )
    html_body = _html_shell(
        f'Invoice {payment.invoice_no}',
        (
            f"<p>Hi {escape(customer.cust_name)},</p>"
            f"<p>Your Homzho invoice <strong>{escape(payment.invoice_no)}</strong> dated "
            f"<strong>{payment.payment_date:%d %b %Y}</strong> is ready.</p>"
            f"<p><strong>Amount paid:</strong> Rs. {payment.amount_paid:,.2f}</p>"
            f'<p><a href="{invoice_url}">View invoice</a></p>'
        ),
    )
    return _queue_email(customer.email_id, subject, text_body, html_body)


def send_billing_reminder_email(customer):
    subject = 'Homzho billing reminder'
    due_date = customer.next_billing_date.strftime('%d %b %Y') if customer.next_billing_date else 'your upcoming due date'
    text_body = (
        f"Hi {customer.cust_name},\n\n"
        f"This is a reminder that your Homzho plan payment is due on {due_date}.\n"
        f"Plan: {customer.plan_name}\n"
        f"Amount: Rs. {customer.monthly_rent:,.2f}\n"
        f"Payment UPI ID: HRIBHAVSERVICES@SRCB\n\n"
        "Regards,\nHomzho Team"
    )
    html_body = _html_shell(
        'Billing Reminder',
        (
            f"<p>Hi {escape(customer.cust_name)},</p>"
            f"<p>This is a reminder that your Homzho plan payment is due on "
            f"<strong>{escape(due_date)}</strong>.</p>"
            f"<p><strong>Plan:</strong> {escape(customer.plan_name)}<br>"
            f"<strong>Amount:</strong> Rs. {customer.monthly_rent:,.2f}</p>"
            f"<strong>Payment UPI ID:</strong> HRIBHAVSERVICES@SRCB</p>"
        ),
    )
    return _queue_email(customer.email_id, subject, text_body, html_body)


def send_maintenance_reminder_email(machine):
    customer = next((c for c in machine.customers if c.customer_status == 'Active'), None)
    if not customer:
        return False, 'No active customer is linked to this machine.'

    service_date = machine.next_service_date.strftime('%d %b %Y') if machine.next_service_date else 'the scheduled date'
    subject = 'Homzho maintenance reminder'
    text_body = (
        f"Hi {customer.cust_name},\n\n"
        f"Your Homzho water purifier service is due on {service_date}.\n"
        f"Machine serial number: {machine.machine_serial_no}\n\n"
        "Regards,\nHomzho Team"
    )
    html_body = _html_shell(
        'Maintenance Reminder',
        (
            f"<p>Hi {escape(customer.cust_name)},</p>"
            f"<p>Your Homzho water purifier service is due on "
            f"<strong>{escape(service_date)}</strong>.</p>"
            f"<p><strong>Machine serial number:</strong> {escape(machine.machine_serial_no)}</p>"
        ),
    )
    return _queue_email(customer.email_id, subject, text_body, html_body)


def send_lead_followup_email(lead):
    subject = 'Thanks for your interest in Homzho'
    text_body = (
        f"Hi {lead.name},\n\n"
        "Thank you for showing interest in Homzho water purifiers. "
        "Our team will be happy to help you choose a suitable plan.\n\n"
        "Regards,\nHomzho Team"
    )
    html_body = _html_shell(
        'Thanks for your interest in Homzho',
        (
            f"<p>Hi {escape(lead.name)},</p>"
            "<p>Thank you for showing interest in Homzho water purifiers. "
            "Our team will be happy to help you choose a suitable plan.</p>"
        ),
    )
    return _queue_email(lead.email_id, subject, text_body, html_body)


def send_customer_welcome_email(customer):
    subject = 'Welcome to Homzho'
    next_billing = customer.next_billing_date.strftime('%d %b %Y') if customer.next_billing_date else 'Not set'
    text_body = (
        f"Hi {customer.cust_name},\n\n"
        "Welcome to Homzho. Your customer profile has been created.\n"
        f"Plan: {customer.plan_name}\n"
        f"Payment frequency: {customer.payment_freq}\n"
        f"Next billing date: {next_billing}\n\n"
        "Regards,\nHomzho Team"
    )
    html_body = _html_shell(
        'Welcome to Homzho',
        (
            f"<p>Hi {escape(customer.cust_name)},</p>"
            "<p>Welcome to Homzho. Your customer profile has been created.</p>"
            f"<p><strong>Plan:</strong> {escape(customer.plan_name)}<br>"
            f"<strong>Payment frequency:</strong> {escape(customer.payment_freq)}<br>"
            f"<strong>Next billing date:</strong> {escape(next_billing)}</p>"
        ),
    )
    return _queue_email(customer.email_id, subject, text_body, html_body)
