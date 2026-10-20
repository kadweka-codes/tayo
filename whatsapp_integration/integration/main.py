def send_whatsapp_message(env, phone, template_name=None, message=None):
    """Send through the active WhatsApp configuration. Credentials stay on that record."""
    config = env['whatsapp.config'].sudo()
    if template_name:
        return config.send_template(phone, template_name)
    return config.send_text(phone, message or '')
