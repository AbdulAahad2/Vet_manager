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

    # Convenience mirror fields (auto-sync from partner)
    name = fields.Char(related="partner_id.name", store=True, readonly=False, tracking=True,index =True,search= True )
    contact_number = fields.Char(related="partner_id.phone", store=True, readonly=False, tracking=True, index=True, search="_search_contact_number")
    email = fields.Char(related="partner_id.email", store=True, readonly=False, tracking=True)
    address = fields.Char(related="partner_id.street", store=True, readonly=False, tracking=True)

    # Relation to animals
    animal_ids = fields.One2many('vet.animal', 'owner_id', string="Animals")

    _sql_constraints = [
        ('unique_contact_number', 'unique(contact_number)', 'Contact number must be unique!')
    ]

    @api.constrains('partner_id')
    def _check_contact_number(self):
        for record in self:
            phone = record.partner_id.phone
            if not phone:
                raise ValidationError("Contact number must be set")
            if not re.fullmatch(r'\d{11}', phone):
                raise ValidationError("Phone number must be exactly 11 digits.")

    @api.constrains('contact_number')
    def _check_contact_number(self):
        for record in self:
            if not record.contact_number:
                raise ValidationError("Contact number must be set")
            if record.contact_number and not re.fullmatch(r'\d{11}', record.contact_number):
                raise ValidationError("Phone number must be exactly 11 digits.")

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            phone = None

            # Case 1: Provided contact_number directly (for auto-partner creation)
            if vals.get("contact_number"):
                phone = vals["contact_number"]

            # Case 2: Partner already exists → check partner’s phone
            elif vals.get("partner_id"):
                partner = self.env["res.partner"].browse(vals["partner_id"])
                phone = partner.phone

            # 🚨 Validate phone
            if not phone:
                raise ValidationError("Contact number must be set")

            if not isinstance(phone, str):  # prevent NoneType errors
                raise ValidationError("Invalid contact number format")

            if not re.fullmatch(r'\d{11}', phone):
                raise ValidationError("Phone number must be exactly 11 digits.")

            # Auto-create partner if missing
            if not vals.get("partner_id"):
                partner = self.env["res.partner"].create({
                    "name": vals.get("name", "Unknown Owner"),
                    "phone": phone,
                    "email": vals.get("email"),
                    "street": vals.get("address"),
                })
                vals["partner_id"] = partner.id

        return super().create(vals_list)

    def _search_contact_number(self, operator, value):
        return [('partner_id.phone', operator, value)]