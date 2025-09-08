from odoo import models, fields

class VetAnimalDoctor(models.Model):
    _name = 'vet.animal.doctor'
    _description = 'Animal Doctor'
    _inherit = ['mail.thread', 'mail.activity.mixin']  # Added for tracking and activities

    name = fields.Char("Doctor Name", required=True, tracking=True)
    contact_number = fields.Char("Contact Number", tracking=True)
    email = fields.Char("Email", tracking=True)
    specialization = fields.Char("Specialization", tracking=True)
    appointments = fields.One2many('vet.animal.schedule', 'doctor_id', string="Appointments")
    active = fields.Boolean(default=True)
    visit_ids = fields.One2many('vet.animal.visit', 'doctor_id', string='Visits')
    notes = fields.Text("Notes")

    _sql_constraints = [
        ('unique_contact_number', 'unique(contact_number)', 'Contact number must be unique!')
    ]
