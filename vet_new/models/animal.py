from odoo import fields, models, api
from odoo.exceptions import ValidationError
import logging
from dateutil.relativedelta import relativedelta

_logger = logging.getLogger(__name__)

class VetAnimal(models.Model):
    _name = "vet.animal"
    _description = "Animal"
    _rec_name = "microchip_no"
    _inherit = ['mail.thread', 'mail.activity.mixin']

    _sql_constraints = [
        ('microchip_unique', 'unique(microchip_no)', 'Microchip number must be unique!')
    ]

    microchip_no = fields.Char(
        string="Microchip No",
        required=True,
        copy=False,
        readonly=True,
        index=True,
        default=lambda self: self.env['ir.sequence'].next_by_code('vet.animal.microchip') or 'HT000000',
        tracking=True
    )
    name = fields.Char(string="Name", required=True, tracking=True)
    dob = fields.Date(string="Date of Birth", tracking=True)
    age = fields.Char(string="Age", compute="_compute_age", store=True)
    gender = fields.Selection([('male', 'Male'), ('female', 'Female')], string="Gender", tracking=True)
    species = fields.Selection([('dog', 'Dog'), ('cat', 'Cat'), ('other', 'Other')], string="Species", tracking=True)
    breed = fields.Char(string="Breed", tracking=True)
    owner_id = fields.Many2one('vet.animal.owner', string="Owner", tracking=True)
    contact_number = fields.Char(related='owner_id.contact_number', string="Owner Contact", store=True, readonly=True)

    # Use attachment_ids specifically for images
    image_1920 = fields.Image(string="Animal Image", max_width=1920, max_height=1920)

    active = fields.Boolean(string="Active", default=True)
    notes = fields.Text(string="Additional Notes")
    partner_id = fields.Many2one(
        'res.partner',
        string='Contact',
        related='owner_id.partner_id',
        store=True,
        index=True
    )
    @api.depends('dob')
    def _compute_age(self):
        for record in self:
            if record.dob:
                today = fields.Date.today()
                delta = relativedelta(today, record.dob)
                years = delta.years
                months = delta.months

                if years > 0:
                    if months > 0:
                        record.age = f"{years} year{'s' if years > 1 else ''} {months} month{'s' if months > 1 else ''}"
                    else:
                        record.age= f"{years} year{'s' if years > 1 else ''}"
                else:
                    record.age = f"{months} month{'s' if months != 1 else ''}"
            else:
                record.age = "0"

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('owner_id'):
                raise ValidationError("Add an owner.")
            if not vals.get('microchip_no'):
                vals['microchip_no'] = self.env['ir.sequence'].next_by_code('vet.animal.microchip') or 'HT000000'
        return super(VetAnimal, self).create(vals_list)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            # If partner_id is given but no owner_id, auto-assign
            if vals.get("partner_id") and not vals.get("owner_id"):
                owner = self.env["vet.animal.owner"].search(
                    [("partner_id", "=", vals["partner_id"])],
                    limit=1
                )
                if not owner:
                    raise ValidationError("This contact is not linked to a vet owner.")
                vals["owner_id"] = owner.id
        return super().create(vals_list)

    def name_get(self):
        result = []
        for rec in self:
            display = "[%s] %s" % (rec.microchip_no or "", rec.name or "")
            if rec.owner_id:
                display = "%s - Owner: %s" % (display, rec.owner_id.name)
            result.append((rec.id, display))
        return result

    @api.model
    def name_search(self, name='', args=None, operator='ilike', limit=100):
        args = args or []
        domain = []
        name = (name or '').strip()
        if name.startswith('#'):
            chip = name[1:].strip()
            domain = [('microchip_no', '=', chip)]
        elif name.upper().startswith('HT'):
            domain = [('microchip_no', operator, name)]
        else:
            domain = [('name', operator, name)]
        records = self.search(domain + args, limit=limit)
        return records.name_get()
