import base64
import binascii
import secrets
from datetime import timedelta

from werkzeug.security import check_password_hash, generate_password_hash

from odoo import _, api, fields, models
from odoo.exceptions import UserError

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
_PORTAL_DUMMY_PASSWORD_HASH = generate_password_hash('odutech-portal-placeholder')
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
        return self.env['odutech.portal.company'].sudo().search([
            ('company_id', '=', self.company_id.id),
        ], limit=1)

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
        self.sudo().write({
            'password': generate_password_hash(password),
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

    def action_send_portal_credentials(self):
        self.ensure_one()
        if not self.portal_user:
            raise UserError(_("Turn on Portal User before sending portal credentials."))

        email = self._portal_send_password_setup_email()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Portal credentials'),
                'message': _('A password setup link was sent to %s.', email),
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
        return self.sudo().search([
            ('password_reset_token', '=', token),
            ('active', '=', True),
        ], limit=1)

    @api.model
    def _portal_authenticate(self, email, password):
        """Return the portal employee for this email and password, or an empty recordset."""
        email = (email or '').strip()
        password = password or ''
        if not email or not password:
            check_password_hash(_PORTAL_DUMMY_PASSWORD_HASH, password)
            return self.browse()

        candidates = self.sudo().search([
            ('portal_user', '=', True),
            ('active', '=', True),
            '|',
            ('work_email', '=ilike', email),
            ('private_email', '=ilike', email),
        ])
        if not candidates:
            check_password_hash(_PORTAL_DUMMY_PASSWORD_HASH, password)
            return self.browse()

        matched = self.browse()
        for employee in candidates:
            if employee._portal_check_password(password):
                if matched:
                    return self.browse()
                matched = employee
        return matched

    def _portal_issue_access_token(self):
        self.ensure_one()
        expires = fields.Datetime.now() + timedelta(hours=PORTAL_ACCESS_TOKEN_HOURS)
        token = secrets.token_urlsafe(32)
        self.sudo().write({
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
        if not token:
            return self.browse(), 'missing'
        employee = self.sudo().search([
            ('portal_access_token', '=', token),
            ('portal_user', '=', True),
            ('active', '=', True),
        ], limit=1)
        if not employee:
            return self.browse(), 'invalid'
        if (
            not employee.portal_access_token_expiration
            or employee.portal_access_token_expiration < fields.Datetime.now()
        ):
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
        return {
            'id': self.id,
            'name': self.name or '',
            'work_email': self.work_email or '',
            'work_phone': self.work_phone or '',
            'mobile_phone': self.mobile_phone or '',
            'job_title': self.job_title or '',
            'department': self.department_id.name or '',
            'company': self.company_id.name or '',
            'private_email': self.private_email or '',
            'private_phone': self.private_phone or '',
            'emergency_contact': self.emergency_contact or '',
            'emergency_phone': self.emergency_phone or '',
            'image_icon': self._portal_image_icon(),
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


def _portal_image_bytes(raw):
    if raw.startswith((b'\x89PNG', b'\xff\xd8\xff', b'GIF87a', b'GIF89a')):
        return True
    return raw.startswith(b'RIFF') and raw[8:12] == b'WEBP'
