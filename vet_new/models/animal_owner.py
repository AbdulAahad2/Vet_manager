from odoo import models, fields, api
from odoo.exceptions import ValidationError
import re
from dateutil.relativedelta import relativedelta


class VetAnimalOwner(models.Model):
    _name = 'vet.animal.owner'
    _description = 'Animal Owner'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    # Link to Odoo Contact (res.partner)
    partner_id = fields.Many2one(
        'res.partner',
        string="Contact",
        required=True,
        ondelete="cascade"
    )

    # Extra owner details
    notes = fields.Text("Additional Notes")
    active = fields.Boolean("Active", default=True)

    # Mirror fields
    name = fields.Char(
        related="partner_id.name",
        store=True,
        readonly=False,
        tracking=True,
        index=True
    )
    contact_number = fields.Char(
        related="partner_id.phone",
        store=True,
        readonly=False,
        tracking=True,
        index=True,
        search=lambda self, operator, value: [('partner_id.phone', operator, value)]
    )
    email = fields.Char(
        related="partner_id.email",
        store=True,
        readonly=False,
        tracking=True
    )
    address = fields.Char(
        compute="_compute_address",
        string="Address",
        store=True,
        readonly=False,
        tracking=True
    )

    # Relation to animals
    animal_ids = fields.One2many('vet.animal', 'owner_id', string="Animals")

    @api.depends(
        'partner_id.street', 'partner_id.street2', 'partner_id.city',
        'partner_id.zip', 'partner_id.state_id', 'partner_id.country_id'
    )
    def _compute_address(self):
        for record in self:
            record.address = record.partner_id._display_address(without_company=True) if record.partner_id else False

    # -------------------------
    # Phone Validation
    # -------------------------
    @api.constrains('contact_number')
    def _check_owner_contact_number(self):
        for record in self:
            phone = record.contact_number
            if not phone:
                raise ValidationError("Contact number must be set.")
            if not re.fullmatch(r'\d{11}', str(phone)):
                raise ValidationError("Phone number must be exactly 11 digits.")

            # Check uniqueness at partner level
            dup = self.env['res.partner'].search([
                ('phone', '=', phone),
                ('id', '!=', record.partner_id.id)
            ], limit=1)
            if dup:
                raise ValidationError("Contact number must be unique!")

    # -------------------------
    # Create Override
    # -------------------------
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            partner_id = vals.get("partner_id")

            # Create partner if not provided
            if not partner_id and not self.env.context.get("skip_partner_create"):
                partner = self.env['res.partner'].with_context(skip_owner_create=True).create({
                    "name": vals.get("name", "Unknown Owner"),
                    "phone": vals.get("contact_number"),
                    "email": vals.get("email"),
                    "street": vals.get("address"),
                })
                vals["partner_id"] = partner.id

        return super().create(vals_list)


class ResPartnerInherit(models.Model):
    _inherit = "res.partner"

    owner_id = fields.One2many("vet.animal.owner", "partner_id", string="Vet Owner")
    animal_ids = fields.One2many("vet.animal", "partner_id", string="Animals")
    dob = fields.Date(string="Date of Birth", tracking=True)
    age = fields.Char(string="Age", compute="_compute_age", store=True)

    @api.depends('dob')
    def _compute_age(self):
        for record in self:
            if record.dob:
                delta = relativedelta(fields.Date.today(), record.dob)
                years, months = delta.years, delta.months
                if years > 0:
                    record.age = f"{years} year{'s' if years > 1 else ''} {months} month{'s' if months > 1 else ''}" if months else f"{years} year{'s' if years > 1 else ''}"
                else:
                    record.age = f"{months} month{'s' if months > 1 else ''}"
            else:
                record.age = "0"

    @api.model_create_multi
    def create(self, vals_list):
        partners = super().create(vals_list)
        for partner in partners:
            if self.env.context.get("skip_owner_create"):
                continue
            if not partner.owner_id:
                self.env['vet.animal.owner'].with_context(skip_partner_create=True).create({
                    "partner_id": partner.id,
                    "name": partner.name or "Unknown Owner",
                    "contact_number": partner.phone,
                    "email": partner.email,
                    "address": partner.street,
                })
        return partners

    def write(self, vals):
        res = super().write(vals)
        for partner in self:
            if self.env.context.get("skip_owner_create"):
                continue
            if not partner.owner_id:
                self.env['vet.animal.owner'].with_context(skip_partner_create=True).create({
                    "partner_id": partner.id,
                    "name": partner.name or "Unknown Owner",
                    "contact_number": partner.phone,
                    "email": partner.email,
                    "address": partner.street,
                })
        return res
