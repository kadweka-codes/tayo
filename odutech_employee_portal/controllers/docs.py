import html
import json

from odoo import http
from odoo.http import request, Response

from ..models.hr_employee import (
    PORTAL_ACCESS_TOKEN_HOURS,
    PORTAL_PROFILE_PICTURE_MAX_BYTES,
    PORTAL_SELF_EDITABLE_FIELDS,
    PORTAL_TOKEN_HOURS,
)

EDITABLE_FIELDS = ', '.join((*PORTAL_SELF_EDITABLE_FIELDS, 'profile_picture'))
PICTURE_MAX_MB = PORTAL_PROFILE_PICTURE_MAX_BYTES // (1024 * 1024)


def api_documentation():
    """Single source for the HTML page and the JSON document."""
    return {
        'name': 'EP.Portal',
        'baseUrl': '/odutech/portal/api',
        'authentication': (
            'POST /auth/login returns an access token. Send it as '
            'Authorization: Bearer <token> on every employee call. '
            'The token lasts %s hours. Logout revokes it.'
        ) % PORTAL_ACCESS_TOKEN_HOURS,
        'errors': {
            'status': 'failed',
            'message': 'Human-readable reason.',
        },
        'endpoints': [
            {
                'method': 'GET',
                'path': '/odutech/portal/api',
                'auth': 'none',
                'summary': 'This documentation. Browsers receive HTML. Other clients receive JSON.',
                'request': 'GET /odutech/portal/api\nAccept: application/json',
                'response': 'This document. Add ?format=html to force the page, or ?format=json to force JSON.',
            },
            {
                'method': 'POST',
                'path': '/odutech/portal/api/auth/login',
                'auth': 'none',
                'summary': (
                    'Sign in with the work email or private email of an active portal user. '
                    'When the company has no custom domain, also send the login code as customer_code.'
                ),
                'request': """{
  "email": "person@company.com",
  "password": "their-password",
  "customer_code": "required when Has Custom Domain is off"
}""",
                'response': """{
  "status": "success",
  "data": {
    "access_token": "…",
    "token_type": "Bearer",
    "expires_at": "2026-11-15 03:46:00",
    "employee": { "id": 1, "name": "Amina Hassan", "work_email": "person@company.com" }
  }
}""",
                'notes': (
                    'Unknown email or password returns 401 and "Invalid email or password." '
                    'A past subscription expiry returns "Subscription has expired." '
                    'More active employees than Employee Count returns "License employee limit is reached."'
                ),
            },
            {
                'method': 'POST',
                'path': '/odutech/portal/api/auth/logout',
                'auth': 'bearer token',
                'summary': 'Revoke the current access token.',
                'request': 'Authorization: Bearer <token>',
                'response': """{
  "status": "success",
  "message": "Logged out."
}""",
            },
            {
                'method': 'POST',
                'path': '/odutech/portal/api/auth/reset-password',
                'auth': 'none',
                'summary': (
                    'Email a password setup link to one active portal user. '
                    'The link lasts %s hours.'
                ) % PORTAL_TOKEN_HOURS,
                'request': """{
  "email": "person@company.com"
}""",
                'response': """{
  "status": "success",
  "message": "A password reset link was sent."
}""",
                'notes': (
                    'The link is {portal base}/odutech/portal/set-password/<token>. '
                    'Use that token with set-password. An unknown email still returns success '
                    'and does not send mail.'
                ),
            },
            {
                'method': 'POST',
                'path': '/odutech/portal/api/auth/set-password',
                'auth': 'reset token',
                'summary': 'Save a new password from the token in the reset link. The password is stored as a hash.',
                'request': """{
  "token": "token-from-the-link",
  "password": "new-password",
  "password_confirm": "new-password"
}""",
                'response': """{
  "status": "success",
  "message": "Password saved."
}""",
                'notes': 'Password must be at least 8 characters and match password_confirm. The token is cleared after a successful save.',
            },
            {
                'method': 'GET',
                'path': '/odutech/portal/api/employees',
                'auth': 'bearer token',
                'summary': 'Active employees in the signed-in employee’s company.',
                'request': 'Authorization: Bearer <token>',
                'response': """{
  "status": "success",
  "data": [
    {
      "id": 1,
      "name": "Amina Hassan",
      "work_email": "amina@company.com",
      "work_phone": "",
      "mobile_phone": "",
      "job_title": "Accountant",
      "department": "Finance",
      "company": "Odutech Solutions",
      "private_email": "amina@example.com",
      "private_phone": "",
      "emergency_contact": "",
      "emergency_phone": ""
    }
  ]
}""",
                'notes': 'private_email, private_phone, emergency_contact, and emergency_phone are returned only on the signed-in employee’s own row.',
            },
            {
                'method': 'GET',
                'path': '/odutech/portal/api/employees/listing',
                'auth': 'bearer token',
                'summary': 'Company directory with department, manager, and image icons.',
                'request': 'Authorization: Bearer <token>',
                'response': """{
  "status": "success",
  "data": [
    {
      "id": 1,
      "name": "Amina Hassan",
      "work_email": "amina@company.com",
      "job_title": "Accountant",
      "image_icon": "…base64…",
      "department": { "id": 4, "name": "Finance" },
      "manager": { "id": 2, "name": "James Otieno", "image_icon": "…base64…" }
    }
  ]
}""",
                'notes': 'department and manager are null when missing. image_icon is the 128px avatar as base64, or null. Prefix it with data:image/png;base64, to display it.',
            },
            {
                'method': 'PUT, PATCH',
                'path': '/odutech/portal/api/employees',
                'auth': 'bearer token',
                'summary': 'Update only the signed-in employee. Send JSON, or multipart when uploading a picture.',
                'request': """{
  "name": "Amina Hassan",
  "mobile_phone": "254700000000",
  "work_phone": "",
  "private_email": "amina@example.com",
  "private_phone": "",
  "emergency_contact": "Omar Hassan",
  "emergency_phone": "254711000000",
  "profile_picture": null
}""",
                'response': """{
  "status": "success",
  "data": { "id": 1, "name": "Amina Hassan", "image_icon": "…base64…" }
}""",
                'notes': (
                    'Allowed fields: %s. '
                    'profile_picture accepts a base64 string, a data:image URL, or a multipart file of the same name. '
                    'PNG, JPEG, GIF, or WebP, up to %s MB. null or an empty string clears the picture.'
                ) % (EDITABLE_FIELDS, PICTURE_MAX_MB),
            },
        ],
    }


def _wants_json():
    requested = (request.params.get('format') or '').lower()
    if requested == 'json':
        return True
    if requested == 'html':
        return False
    accept = request.httprequest.headers.get('Accept') or ''
    return 'application/json' in accept and 'text/html' not in accept


def _try_form(endpoint):
    """A form that calls this endpoint from the documentation page."""
    methods = [method.strip() for method in endpoint['method'].split(',') if method.strip()]
    request_example = (endpoint.get('request') or '').strip()
    body = request_example if request_example.startswith('{') else ''
    options = ''.join(
        '<option value="%s">%s</option>' % (html.escape(method), html.escape(method))
        for method in methods
    )
    body_field = ''
    if body:
        body_field = (
            '<label>JSON body<textarea name="body" spellcheck="false">%s</textarea></label>'
            % html.escape(body)
        )
    return """
    <form class="try" data-path="%s" data-auth="%s">
      <div class="try-row">
        <label>Method<select name="method">%s</select></label>
        <button type="submit">Send</button>
      </div>
      %s
      <pre class="result">The response will appear here.</pre>
    </form>
    """ % (
        html.escape(endpoint['path'], quote=True),
        html.escape(endpoint.get('auth') or '', quote=True),
        options,
        body_field,
    )


def _render_html(document):
    sections = []
    for index, endpoint in enumerate(document['endpoints'], start=1):
        notes = endpoint.get('notes') or ''
        sections.append(
            """
            <section>
              <h2>%s. %s <span>%s</span></h2>
              <p>%s</p>
              <p class="meta"><strong>%s</strong> %s</p>
              <pre>%s</pre>
              <pre>%s</pre>
              %s
              %s
            </section>
            """ % (
                index,
                html.escape(endpoint['method']),
                html.escape(endpoint['path']),
                html.escape(endpoint['summary']),
                html.escape(endpoint['auth']),
                html.escape(endpoint['path']),
                html.escape(endpoint.get('request') or ''),
                html.escape(endpoint.get('response') or ''),
                '<p>%s</p>' % html.escape(notes) if notes else '',
                _try_form(endpoint),
            )
        )
    body = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
      <meta charset="utf-8"/>
      <meta name="viewport" content="width=device-width, initial-scale=1"/>
      <title>%(title)s API</title>
      <style>
        body { margin: 0; background: #f6f4ee; color: #1c1915; font: 16px/1.5 Georgia, serif; }
        main { max-width: 880px; margin: 0 auto; padding: 32px 20px 64px; }
        h1 { font-size: 2rem; margin-bottom: 0.25rem; }
        h2 { font-size: 1.25rem; border-bottom: 3px solid #1f7a4d; padding-bottom: 0.35rem; }
        h2 span { font-family: ui-monospace, monospace; font-size: 0.95rem; font-weight: normal; }
        .meta, .token, form.try { font-family: ui-monospace, monospace; font-size: 0.92rem; }
        pre { background: #16181d; color: #f4f1ea; padding: 16px; overflow: auto; border-radius: 6px; }
        a, button { color: #1f7a4d; }
        .token, form.try { background: #fff; border: 1px solid #d9d3c7; border-radius: 8px; padding: 12px 14px 14px; }
        .token { margin: 20px 0 8px; }
        label { display: block; margin: 8px 0; }
        input, select, textarea { width: 100%%; box-sizing: border-box; font: inherit; margin-top: 4px; }
        textarea { min-height: 140px; }
        .try-row { display: flex; gap: 12px; align-items: end; }
        .try-row label { flex: 1; }
        button { background: #1f7a4d; color: #fff; border: 0; border-radius: 6px; padding: 8px 16px; cursor: pointer; }
        .result { min-height: 3rem; white-space: pre-wrap; }
      </style>
    </head>
    <body>
      <main>
        <h1>%(title)s</h1>
        <p>%(auth)s</p>
        <p>Errors use <code>{"status": "failed", "message": "…"}</code>.
        Send <code>Accept: application/json</code> on this URL for the JSON form.
        <code>?format=html</code> forces this page.</p>
        <p>Use <strong>Send</strong> on an endpoint to call this server directly. A successful login stores the access token for the calls that need it.</p>
        <div class="token">
          <label>Access token
            <input id="access-token" type="text" autocomplete="off" placeholder="Filled automatically after login"/>
          </label>
        </div>
        %(sections)s
      </main>
      <script>
        const tokenInput = document.querySelector('#access-token');
        const storedToken = localStorage.getItem('epPortalToken') || '';
        tokenInput.value = storedToken;
        tokenInput.addEventListener('input', function () {
          localStorage.setItem('epPortalToken', tokenInput.value.trim());
        });

        document.querySelectorAll('form.try').forEach(function (form) {
          form.addEventListener('submit', async function (event) {
            event.preventDefault();
            const result = form.querySelector('.result');
            const method = form.querySelector('[name=method]').value;
            const bodyField = form.querySelector('[name=body]');
            const headers = { 'Accept': 'application/json' };
            if (form.dataset.auth === 'bearer token') {
              const token = tokenInput.value.trim();
              if (!token) {
                result.textContent = 'Sign in first, or paste an access token above.';
                return;
              }
              headers.Authorization = 'Bearer ' + token;
            }
            const options = { method: method, headers: headers };
            if (bodyField && method !== 'GET' && bodyField.value.trim()) {
              try {
                JSON.parse(bodyField.value);
              } catch (error) {
                result.textContent = 'The body is not valid JSON.';
                return;
              }
              headers['Content-Type'] = 'application/json';
              options.body = bodyField.value;
            }
            result.textContent = 'Sending…';
            try {
              const response = await fetch(form.dataset.path, options);
              const text = await response.text();
              let pretty = text;
              let parsed = null;
              try {
                parsed = JSON.parse(text);
                pretty = JSON.stringify(parsed, null, 2);
              } catch (error) {}
              result.textContent = response.status + ' ' + response.statusText + '\\n\\n' + pretty;
              const token = parsed && parsed.data && parsed.data.access_token;
              if (token) {
                tokenInput.value = token;
                localStorage.setItem('epPortalToken', token);
              }
            } catch (error) {
              result.textContent = String(error);
            }
          });
        });
      </script>
    </body>
    </html>
    """ % {
        'title': html.escape(document['name']),
        'auth': html.escape(document['authentication']),
        'sections': '\n'.join(sections),
    }
    return body


class PortalApiDocsController(http.Controller):

    @http.route(
        '/odutech/portal/api',
        type='http',
        auth='public',
        methods=['GET'],
        csrf=False,
        sitemap=False,
    )
    def documentation(self, **kwargs):
        document = api_documentation()
        if _wants_json():
            return Response(
                json.dumps(document, indent=2),
                status=200,
                mimetype='application/json',
            )
        return Response(_render_html(document), status=200, mimetype='text/html')
