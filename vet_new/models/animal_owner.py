from odoo import models, fields, api
from odoo.exceptions import ValidationError
import re

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

    # Extra owner details (not in partner)
    notes = fields.Text("Additional Notes")
    active = fields.Boolean("Active", default=True)

    # Mirror fields (sync with partner)
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
    email = fields.Char(related="partner_id.email", store=True, readonly=False, tracking=True)
    address = fields.Char(related="partner_id.street", store=True, readonly=False, tracking=True)

    # Relation to animals
    animal_ids = fields.One2many('vet.animal', 'owner_id', string="Animals")

    # -------------------------
    # Validation Constraints
    # -------------------------
    @api.constrains('contact_number')
    def _check_owner_contact_number(self):
        for record in self:
            phone = record.contact_number
            if not phone:
                raise ValidationError("Contact number must be set.")
            phone = str(phone)
            if not re.fullmatch(r'\d{11}', phone):
                raise ValidationError("Phone number must be exactly 11 digits.")

            # Python uniqueness check
            dup = self.search([
                ('contact_number', '=', phone),
                ('id', '!=', record.id)
            ], limit=1)
            if dup:
                raise ValidationError("Contact number must be unique!")

    # -------------------------
    # Create override
    # -------------------------
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            phone = None

            # If contact_number is given → use it
            if vals.get("contact_number"):
                phone = vals["contact_number"]

            # If partner is provided → check its phone
            elif vals.get("partner_id"):
                partner = self.env["res.partner"].browse(vals["partner_id"])
                phone = partner.phone

            # Validate phone
            if not phone:
                raise ValidationError("Contact number must be set.")

            phone = str(phone)
            if not re.fullmatch(r'\d{11}', phone):
                raise ValidationError("Phone number must be exactly 11 digits.")

            # If no partner → create one automatically
            if not vals.get("partner_id"):
                partner = self.env["res.partner"].create({
                    "name": vals.get("name", "Unknown Owner"),
                    "phone": phone,
                    "email": vals.get("email"),
                    "street": vals.get("address"),
                })
                vals["partner_id"] = partner.id

        return super().create(vals_list)


# ------------------------------------------------------------
# Extend res.partner so Contacts always sync to Vet Management
# ------------------------------------------------------------
from odoo import models, api

class ResPartnerInherit(models.Model):
    _inherit = "res.partner"

    owner_id = fields.One2many("vet.animal.owner", "partner_id", string="Vet Owner")
    animal_ids = fields.One2many(
        "vet.animal",
        "partner_id",
        string="Animals"
    )

    def _compute_animal_ids(self):
        for partner in self:
            partner.animal_ids = self.env['vet.animal'].search([('owner_id.partner_id', '=', partner.id)])
    @api.model_create_multi
    def create(self, vals_list):
        partners = super().create(vals_list)
        for partner in partners:
            if self.env.context.get("create_user") or partner.user_ids:
                continue
            # Always ensure owner exists
            if not partner.owner_id:
                self.env['vet.animal.owner'].create({
                    "partner_id": partner.id,
                    "name": partner.name or "Unknown Owner",
                    "contact_number": partner.phone or "00000000000",  # fallback if blank
                    "email": partner.email,
                    "address": partner.street,
                })
        return partners

    def write(self, vals):
        res = super().write(vals)
        for partner in self:
            if partner.user_ids:
                continue
            if not partner.owner_id:
                self.env['vet.animal.owner'].create({
                    "partner_id": partner.id,
                    "name": partner.name or "Unknown Owner",
                    "contact_number": partner.phone or "00000000000",
                    "email": partner.email,
                    "address": partner.street,
                })
        return res
