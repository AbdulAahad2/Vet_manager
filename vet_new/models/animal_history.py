from odoo import api, fields, models

class VetAnimalHistoryWizard(models.TransientModel):
    _name = "vet.animal.history.wizard"
    _description = "Animal Visit History Search"

    animal_id = fields.Many2one("vet.animal", string="Animal")
    animal_name = fields.Char(string="Animal Name", readonly=False)
    partner_id = fields.Many2one("res.partner", string="Owner")
    contact_number = fields.Char(string="Owner Contact")
    history_line_ids = fields.One2many("vet.animal.history.line", "wizard_id", string="History Lines")
    total_visits = fields.Integer(string="Total Visits", readonly=True)

    @api.onchange('partner_id')
    def _onchange_partner(self):
        if self.partner_id:
            self.contact_number = self.partner_id.phone
    @api.onchange('animal_id')
    def _onchange_animal(self):
        if self.animal_id and self.animal_id.owner_id:
            self.partner_id = self.animal_id.owner_id.partner_id
            self.contact_number = self.partner_id.phone
            self.animal_name = self.animal_id.name
        return {'domain': {'animal_id': [('id', '=', self.animal_id.id)]}}

    @api.onchange('animal_name')
    def _onchange_animal_name(self):
        if self.animal_name:
            animals = self.env['vet.animal'].search([('name', 'ilike', self.animal_name)])
            return {'domain': {'animal_id': [('id', 'in', animals.ids)]}}
        return {'domain': {'animal_id': [('id', '=', False)]}}

    @api.onchange('contact_number')
    def _onchange_contact_number(self):
        if self.contact_number:
            owner = self.env['res.partner'].search([('phone', '=', self.contact_number)], limit=1)
            if owner:
                self.partner_id = owner
                animals = self.env['vet.animal'].search([('owner_id.partner_id', '=', owner.id)])
                self.animal_id = False
                return {'domain': {'animal_id': [('id', 'in', animals.ids)]}}
            else:
                self.partner_id = False
                self.animal_id = False
                return {'domain': {'animal_id': [('id', '=', False)]}}
        else:
            self.partner_id = False
            self.animal_id = False
            return {'domain': {'animal_id': [('id', '=', False)]}}

    def action_search_history(self):
        self.ensure_one()
        domain = []

        if self.animal_id:
            domain.append(('animal_id', '=', self.animal_id.id))
        elif self.animal_name:
            animals = self.env['vet.animal'].search([('name', 'ilike', self.animal_name)])
            domain.append(('animal_id', 'in', animals.ids)) if animals else domain.append(('id', '=', 0))
        elif self.contact_number:
            owner = self.env['res.partner'].search([('phone', '=', self.contact_number)], limit=1)
            if owner:
                animals = self.env['vet.animal'].search([('owner_id.partner_id', '=', owner.id)])
                domain.append(('animal_id', 'in', animals.ids)) if animals else domain.append(('id', '=', 0))
            else:
                domain.append(('id', '=', 0))

        visits = self.env['vet.animal.visit'].search(domain, order='date desc')

        lines = [(0, 0, {
            'visit_id': visit.id,
            'visit_date': visit.date,
            'doctor': visit.doctor_id.name,
            'notes': visit.notes or '-',
            'total_amount': visit.total_amount,
        }) for visit in visits]

        # reset before adding
        self.history_line_ids = [(5, 0, 0)] + lines
        self.total_visits = len(visits)

        return self._return_wizard_action()

    def _return_wizard_action(self):
        """Reopen wizard with updated results"""
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'vet.animal.history.wizard',
            'view_mode': 'form',
            'res_id': self.id,
            'target': 'new',
        }
class VetAnimalHistoryLine(models.TransientModel):
    _name = "vet.animal.history.line"
    _description = "Animal Visit History Line"

    wizard_id = fields.Many2one("vet.animal.history.wizard", string="Wizard", ondelete="cascade")
    visit_id = fields.Many2one("vet.animal.visit", string="Visit")
    visit_date = fields.Datetime(string="Visit Date")
    doctor = fields.Char(string="Doctor")
    notes = fields.Text(string="Notes")
    total_amount = fields.Monetary(string="Total Amount", currency_field="currency_id")

    currency_id = fields.Many2one("res.currency", default=lambda self: self.env.company.currency_id)
