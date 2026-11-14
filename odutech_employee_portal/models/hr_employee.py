import base64
import binascii
import re
import secrets
from datetime import datetime, timedelta, timezone

import requests
from werkzeug.security import check_password_hash, generate_password_hash

from odoo import _, api, fields, models
from odoo.exceptions import UserError

ODUTECH_EMPLOYEES_API = 'https://odoogrid.com/api/enterprise-suit/employees'
PORTAL_TOKEN_HOURS = 48
PORTAL_ACCESS_TOKEN_HOURS = 24
PORTAL_SELF_EDITABLE_FIELDS = (
    'name',
    'mobile_phone',
    'work_phone',
    'private_email',
    'private_phone',
    'emergency_contact',
    'emergency_phone',
)
# ~15ms on this server. The default scrypt hash is about 100ms per login.
_PORTAL_PASSWORD_METHOD = 'pbkdf2:sha256:100000'
_PORTAL_SQL_FIELDS = frozenset({
    'password',
    'password_reset_token',
    'token_expiration_time',
    'portal_user',
    'portal_access_token',
    'portal_access_token_expiration',
})


def _portal_hash_password(password):
    return generate_password_hash(password or '', method=_PORTAL_PASSWORD_METHOD)


_PORTAL_DUMMY_PASSWORD_HASH = _portal_hash_password('odutech-portal-placeholder')
PORTAL_PROFILE_PICTURE_FIELD = 'profile_picture'
PORTAL_PROFILE_PICTURE_MAX_BYTES = 5 * 1024 * 1024


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    portal_user = fields.Boolean(
        string='Portal User',
        default=False,
    )
    password = fields.Char(
        string='Password',
        copy=False,
        help="Portal password hash. The employee sets it from the link in the credentials email.",
    )
    password_reset_token = fields.Char(
        string='Password Reset Token',
        copy=False,
        index=True,
    )
    token_expiration_time = fields.Datetime(
        string='Token Expiration Time',
        copy=False,
    )
    portal_access_token = fields.Char(
        string='Portal Access Token',
        copy=False,
        index=True,
    )
    portal_access_token_expiration = fields.Datetime(
        string='Portal Access Token Expiration',
        copy=False,
    )

    def init(self):
        cr = self.env.cr
        cr.execute("""
            CREATE INDEX IF NOT EXISTS odutech_employee_portal_work_email_idx
            ON hr_employee (lower(work_email))
            WHERE portal_user IS TRUE AND active IS TRUE
        """)
        cr.execute("""
            CREATE INDEX IF NOT EXISTS odutech_employee_portal_private_email_idx
            ON hr_employee (lower(private_email))
            WHERE portal_user IS TRUE AND active IS TRUE
        """)

    def _portal_sql_write(self, values):
        """Update a few stored columns without the hr.employee write path."""
        self.ensure_one()
        unknown = set(values) - _PORTAL_SQL_FIELDS
        if unknown:
            raise ValueError("Unexpected portal columns: %s" % ', '.join(sorted(unknown)))
        assignments = []
        params = []
        for field_name, value in values.items():
            field = self._fields[field_name]
            if value is False and field.type in ('char', 'text', 'datetime', 'date'):
                value = None
            assignments.append('"%s" = %%s' % field_name)
            params.append(value)
        assignments.append('"write_date" = %s')
        params.append(fields.Datetime.now())
        assignments.append('"write_uid" = %s')
        params.append(self.env.uid)
        params.append(self.id)
        self.env.cr.execute(
            'UPDATE hr_employee SET ' + ', '.join(assignments) + ' WHERE id = %s',
            params,
        )
        self.invalidate_recordset(list(values) + ['write_date', 'write_uid'])

    @api.model_create_multi
    def create(self, vals_list):
        if not self.env.su:
            vals_list = [self._without_direct_password(vals) for vals in vals_list]
        return super().create(vals_list)

    def write(self, vals):
        if not self.env.su:
            vals = self._without_direct_password(vals)
        return super().write(vals)

    def _without_direct_password(self, vals):
        if 'password' not in vals:
            return vals
        vals = dict(vals)
        vals.pop('password')
        return vals

    def _portal_email(self):
        self.ensure_one()
        return self.work_email or self.sudo().private_email

    def _portal_token_is_valid(self):
        self.ensure_one()
        return bool(
            self.password_reset_token
            and self.token_expiration_time
            and self.token_expiration_time >= fields.Datetime.now()
        )

    def _portal_company_setup(self):
        self.ensure_one()
        company_id = self.company_id.id
        if not company_id:
            return self.env['odutech.portal.company']
        self.env.cr.execute(
            """
            SELECT id
              FROM odutech_portal_company
             WHERE company_id = %s
             ORDER BY id
             LIMIT 1
            """,
            [company_id],
        )
        row = self.env.cr.fetchone()
        return self.env['odutech.portal.company'].sudo().browse(row[0] if row else [])

    def _portal_license_message(self):
        self.ensure_one()
        setup = self._portal_company_setup()
        if not setup:
            return _("Set up the company under EP.Portal before signing in.")
        return setup.portal_license_message()

    def _get_portal_set_password_url(self):
        self.ensure_one()
        setup = self._portal_company_setup()
        base = setup.portal_base_url() if setup else ''
        token = self.password_reset_token or ''
        return f"{base}/odutech/portal/set-password/{token}" if base else ''

    def _set_portal_password(self, password, password_confirm):
        """Store a hashed portal password when the reset token is still valid.

        Returns an error message, or None when the password was saved.
        """
        self.ensure_one()
        password = password or ''
        password_confirm = password_confirm or ''
        if not self._portal_token_is_valid():
            return _("This link has expired. Ask your company to send a new one.")
        if len(password) < 8:
            return _("Use at least 8 characters.")
        if password != password_confirm:
            return _("The two passwords do not match.")
        self.sudo()._portal_sql_write({
            'password': _portal_hash_password(password),
            'password_reset_token': False,
            'token_expiration_time': False,
            'portal_user': True,
        })
        return None

    def _portal_send_password_setup_email(self):
        """Create a 48-hour reset token and email the set-password link."""
        self.ensure_one()
        email = self._portal_email()
        if not email:
            raise UserError(_("This employee has no work email or private email."))

        setup = self._portal_company_setup()
        if not setup:
            raise UserError(_(
                "Set up %(company)s under EP.Portal before sending credentials.",
                company=self.company_id.display_name,
            ))
        if not setup.allow_employee_portal:
            raise UserError(_(
                "Turn on Allow Employee Portal for %(company)s before sending credentials.",
                company=setup.company_name,
            ))
        portal_url = setup.portal_base_url()
        if not portal_url:
            raise UserError(_("Set the Odoo ERP link or the employee portal URL before sending credentials."))
        if not portal_url.startswith(('http://', 'https://')):
            raise UserError(_("The portal link must start with http:// or https://."))

        employee = self.sudo()
        previous = {
            'password_reset_token': employee.password_reset_token,
            'token_expiration_time': employee.token_expiration_time,
        }
        employee.write({
            'password_reset_token': secrets.token_urlsafe(32),
            'token_expiration_time': fields.Datetime.now() + timedelta(hours=PORTAL_TOKEN_HOURS),
        })

        template = self.env.ref(
            'odutech_employee_portal.mail_template_portal_credentials',
            raise_if_not_found=False,
        )
        if not template:
            employee.write(previous)
            raise UserError(_("The portal credentials email template is missing."))

        try:
            template.sudo().send_mail(self.id, force_send=True, email_values={'email_to': email})
        except Exception:
            employee.write(previous)
            raise
        return email

    def _portal_employee_api_payload(self):
        """Fields accepted by POST /api/enterprise-suit/employees."""
        self.ensure_one()
        payload = {
            'fullNames': (self.name or '').strip(),
            'workEmail': (self.work_email or '').strip(),
        }
        personal_email = (self.sudo().private_email or '').strip()
        if personal_email:
            payload['personalEmail'] = personal_email
        work_phone = (self.work_phone or '').strip()
        if len(re.sub(r'\D', '', work_phone)) >= 7:
            payload['workPhone'] = work_phone
        personal_phone = (self.sudo().private_phone or self.mobile_phone or '').strip()
        if len(re.sub(r'\D', '', personal_phone)) >= 7:
            payload['personalPhone'] = personal_phone
        picture = self._portal_profile_picture_payload()
        if picture:
            payload['profilePicture'] = picture
        return payload

    def _portal_profile_picture_payload(self):
        self.ensure_one()
        image = self.image_1920
        if not image:
            return ''
        if isinstance(image, bytes):
            image = image.decode()
        try:
            raw = base64.b64decode(image, validate=True)
        except binascii.Error:
            return ''
        if not raw or len(raw) > PORTAL_PROFILE_PICTURE_MAX_BYTES or not _portal_image_bytes(raw):
            return ''
        return image

    def _portal_register_remote_employee(self):
        """Create the employee on Enterprise Suite and store the returned token."""
        self.ensure_one()
        payload = self._portal_employee_api_payload()
        if not payload['fullNames']:
            raise UserError(_("This employee needs a name."))
        if not payload['workEmail']:
            raise UserError(_("This employee needs a work email. The set-password message is sent there."))

        setup = self._portal_company_setup()
        if not setup:
            raise UserError(_(
                "Set up %(company)s under EP.Portal before sending credentials.",
                company=self.company_id.display_name,
            ))
        license_token = (setup.authorization_token or '').strip()
        if not license_token:
            raise UserError(_("Connect the company under EP.Portal before sending portal credentials."))

        try:
            response = requests.post(
                ODUTECH_EMPLOYEES_API,
                json=payload,
                headers={
                    'Content-Type': 'application/json',
                    'Accept': 'application/json',
                    'Authorization': f'Bearer {license_token}',
                    'X-License-Token': license_token,
                },
                timeout=30,
            )
        except requests.exceptions.RequestException as error:
            raise UserError(_("Could not reach the employee portal: %s") % error) from error

        try:
            result = response.json()
        except ValueError:
            result = {}
        if not isinstance(result, dict):
            result = {}
        if response.status_code not in (200, 201):
            message = result.get('error') or result.get('message') or response.text
            raise UserError(message or _("The employee could not be recorded. (%s)") % response.status_code)

        reset_token = (result.get('token') or '').strip()
        expires = _portal_expiration_from_api(result.get('expiresAt'))
        if not reset_token or not expires:
            raise UserError(_("The portal did not return a token and an expiration."))
        self.sudo().write({
            'password_reset_token': reset_token,
            'portal_access_token_expiration': expires,
        })
        return (result.get('email') or payload['workEmail']).strip()

    def action_send_portal_credentials(self):
        self.ensure_one()
        if not self.portal_user:
            raise UserError(_("Turn on Portal User before sending portal credentials."))

        email = self._portal_register_remote_employee()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Portal credentials'),
                'message': _('A set-password message was sent to %s.', email),
                'type': 'success',
                'sticky': False,
                'next': {
                    'type': 'ir.actions.act_window',
                    'name': _('Employee'),
                    'res_model': 'hr.employee',
                    'res_id': self.id,
                    'view_mode': 'form',
                    'views': [(False, 'form')],
                    'target': 'current',
                },
            },
        }

    def _portal_check_password(self, password):
        self.ensure_one()
        if not self.password:
            check_password_hash(_PORTAL_DUMMY_PASSWORD_HASH, password or '')
            return False
        try:
            return check_password_hash(self.password, password or '')
        except (TypeError, ValueError):
            return False

    @api.model
    def _portal_find_by_email(self, email):
        """Return the single active portal employee for this email, or an empty recordset."""
        email = (email or '').strip()
        if not email:
            return self.browse()
        candidates = self.sudo().search([
            ('portal_user', '=', True),
            ('active', '=', True),
            '|',
            ('work_email', '=ilike', email),
            ('private_email', '=ilike', email),
        ])
        if len(candidates) != 1:
            return self.browse()
        return candidates

    @api.model
    def _portal_employee_from_reset_token(self, token):
        token = (token or '').strip()
        if not token:
            return self.browse()
        self.env.cr.execute(
            """
            SELECT id
              FROM hr_employee
             WHERE password_reset_token = %s
               AND active IS TRUE
             LIMIT 1
            """,
            [token],
        )
        row = self.env.cr.fetchone()
        return self.sudo().browse(row[0] if row else [])

    @api.model
    def _portal_authenticate(self, email, password):
        """Return the portal employee for this email and password, or an empty recordset."""
        email = (email or '').strip().lower()
        password = password or ''
        if not email or not password:
            check_password_hash(_PORTAL_DUMMY_PASSWORD_HASH, password)
            return self.browse()

        self.env.cr.execute(
            """
            SELECT id, password
              FROM hr_employee
             WHERE active IS TRUE
               AND portal_user IS TRUE
               AND lower(work_email) = %s
            UNION
            SELECT id, password
              FROM hr_employee
             WHERE active IS TRUE
               AND portal_user IS TRUE
               AND lower(private_email) = %s
            """,
            [email, email],
        )
        rows = self.env.cr.fetchall()
        if not rows:
            check_password_hash(_PORTAL_DUMMY_PASSWORD_HASH, password)
            return self.browse()

        matched_id = None
        matched_hash = None
        for employee_id, stored_hash in rows:
            if employee_id == matched_id:
                continue
            if stored_hash and check_password_hash(stored_hash, password):
                if matched_id:
                    return self.browse()
                matched_id = employee_id
                matched_hash = stored_hash
        if not matched_id:
            return self.browse()

        employee = self.sudo().browse(matched_id)
        fast_prefix = _PORTAL_PASSWORD_METHOD + '$'
        if not (matched_hash or '').startswith(fast_prefix):
            employee._portal_sql_write({'password': _portal_hash_password(password)})
        return employee

    def _portal_issue_access_token(self):
        self.ensure_one()
        expires = fields.Datetime.now() + timedelta(hours=PORTAL_ACCESS_TOKEN_HOURS)
        token = secrets.token_urlsafe(32)
        self.sudo()._portal_sql_write({
            'portal_access_token': token,
            'portal_access_token_expiration': expires,
        })
        return token, expires

    def _portal_revoke_access_token(self):
        self.ensure_one()
        self.sudo().write({
            'portal_access_token': False,
            'portal_access_token_expiration': False,
        })

    @api.model
    def _portal_from_access_token(self, token):
        """Return (employee, error_code). error_code is None when the token is valid."""
        token = (token or '').strip()
        if not token:
            return self.browse(), 'missing'
        self.env.cr.execute(
            """
            SELECT id, portal_access_token_expiration
              FROM hr_employee
             WHERE portal_access_token = %s
               AND portal_user IS TRUE
               AND active IS TRUE
             LIMIT 1
            """,
            [token],
        )
        row = self.env.cr.fetchone()
        if not row:
            return self.browse(), 'invalid'
        employee = self.sudo().browse(row[0])
        expires = row[1]
        if not expires or expires < fields.Datetime.now():
            employee._portal_revoke_access_token()
            return self.browse(), 'expired'
        return employee, None

    def _portal_authorize_record(self, employee_id):
        """Allow a portal employee to reach only their own record.

        Returns (employee, reason). reason is None, 'missing', or 'forbidden'.
        """
        self.ensure_one()
        target = self.sudo().browse(employee_id).exists()
        if not target:
            return self.browse(), 'missing'
        if target.id != self.id:
            return self.browse(), 'forbidden'
        return target, None

    def _portal_api_values(self):
        self.ensure_one()
        data = self.sudo().read([
            'name',
            'work_email',
            'work_phone',
            'mobile_phone',
            'job_title',
            'department_id',
            'company_id',
            'private_email',
            'private_phone',
            'emergency_contact',
            'emergency_phone',
            'avatar_128',
        ])[0]
        department = data['department_id']
        company = data['company_id']
        image = data['avatar_128']
        if isinstance(image, bytes):
            image = image.decode()
        return {
            'id': self.id,
            'name': data['name'] or '',
            'work_email': data['work_email'] or '',
            'work_phone': data['work_phone'] or '',
            'mobile_phone': data['mobile_phone'] or '',
            'job_title': data['job_title'] or '',
            'department': department[1] if department else '',
            'company': company[1] if company else '',
            'private_email': data['private_email'] or '',
            'private_phone': data['private_phone'] or '',
            'emergency_contact': data['emergency_contact'] or '',
            'emergency_phone': data['emergency_phone'] or '',
            'image_icon': image or None,
        }

    def _portal_list_values(self, viewer):
        """Company directory row. Private fields are included only for the caller."""
        self.ensure_one()
        values = {
            'id': self.id,
            'name': self.name or '',
            'work_email': self.work_email or '',
            'work_phone': self.work_phone or '',
            'mobile_phone': self.mobile_phone or '',
            'job_title': self.job_title or '',
            'department': self.department_id.name or '',
            'company': self.company_id.name or '',
        }
        if viewer and self.id == viewer.id:
            values.update({
                'private_email': self.private_email or '',
                'private_phone': self.private_phone or '',
                'emergency_contact': self.emergency_contact or '',
                'emergency_phone': self.emergency_phone or '',
            })
        return values

    def _portal_image_icon(self):
        """Small employee avatar, base64-encoded, or None when no image is stored."""
        self.ensure_one()
        image = self.avatar_128
        if not image:
            return None
        if isinstance(image, bytes):
            image = image.decode()
        return image

    def _portal_listing_values(self):
        """Directory row with department, manager, and image icons."""
        self.ensure_one()
        department = self.department_id
        manager = self.parent_id
        return {
            'id': self.id,
            'name': self.name or '',
            'work_email': self.work_email or '',
            'job_title': self.job_title or '',
            'image_icon': self._portal_image_icon(),
            'department': {
                'id': department.id,
                'name': department.name or '',
            } if department else None,
            'manager': {
                'id': manager.id,
                'name': manager.name or '',
                'image_icon': manager._portal_image_icon(),
            } if manager else None,
        }

    def _portal_company_employees(self):
        """Active employees in the same company as this portal employee."""
        self.ensure_one()
        return self.sudo().search([
            ('company_id', '=', self.company_id.id),
            ('active', '=', True),
        ], order='name, id')

    def _portal_prepare_profile_picture(self, value):
        """Return (base64 text or False, error message). False clears the picture."""
        if value in (None, False, ''):
            return False, None

        raw = None
        if isinstance(value, (bytes, bytearray)):
            raw = bytes(value)
            if not _portal_image_bytes(raw):
                try:
                    raw = base64.b64decode(raw, validate=True)
                except binascii.Error:
                    return None, _("Profile picture must be an image file.")
        elif isinstance(value, str):
            text = value.strip()
            if text.startswith('data:'):
                if ',' not in text or not text.lower().startswith('data:image/'):
                    return None, _("Profile picture must be an image file.")
                text = text.split(',', 1)[1]
            try:
                raw = base64.b64decode(text, validate=True)
            except binascii.Error:
                return None, _("Profile picture must be base64-encoded image data.")
        else:
            return None, _("Profile picture must be an image file.")

        if not raw:
            return None, _("Profile picture is empty.")
        if len(raw) > PORTAL_PROFILE_PICTURE_MAX_BYTES:
            return None, _("Profile picture must be smaller than 5 MB.")
        if not _portal_image_bytes(raw):
            return None, _("Profile picture must be a PNG, JPEG, GIF, or WebP image.")
        return base64.b64encode(raw).decode(), None

    def _portal_update_own_information(self, values):
        """Write only the caller's own profile fields. Returns an error message or None."""
        self.ensure_one()
        allowed = set(PORTAL_SELF_EDITABLE_FIELDS) | {PORTAL_PROFILE_PICTURE_FIELD}
        unknown = [key for key in values if key not in allowed]
        if unknown:
            names = ', '.join((*PORTAL_SELF_EDITABLE_FIELDS, PORTAL_PROFILE_PICTURE_FIELD))
            return _("You can only edit your own information. Allowed fields: %s.") % names

        cleaned = {}
        for key, value in values.items():
            if key == PORTAL_PROFILE_PICTURE_FIELD:
                picture, error = self._portal_prepare_profile_picture(value)
                if error:
                    return error
                cleaned['image_1920'] = picture
                continue
            if value is None:
                value = False
            if value is not False and not isinstance(value, str):
                return _("Field %s must be text.") % key
            if isinstance(value, str):
                value = value.strip()
            if key == 'name' and not value:
                return _("Name cannot be empty.")
            if key == 'private_email' and value and '@' not in value:
                return _("Private email is not valid.")
            cleaned[key] = value or False
        if not cleaned:
            return _("No values to update.")
        self.sudo().write(cleaned)
        if 'image_1920' in cleaned:
            self.invalidate_recordset(['image_1920', 'image_128', 'avatar_128'])
        return None


def _portal_expiration_from_api(value):
    text = str(value or '').strip()
    if not text:
        return False
    if text.endswith('Z'):
        text = text[:-1] + '+00:00'
    moment = datetime.fromisoformat(text)
    if moment.tzinfo is not None:
        moment = moment.astimezone(timezone.utc).replace(tzinfo=None)
    return fields.Datetime.to_string(moment)


def _portal_image_bytes(raw):
    if raw.startswith((b'\x89PNG', b'\xff\xd8\xff', b'GIF87a', b'GIF89a')):
        return True
    return raw.startswith(b'RIFF') and raw[8:12] == b'WEBP'
