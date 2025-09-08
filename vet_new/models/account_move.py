from odoo import models, fields, api, _
import logging

_logger = logging.getLogger(__name__)

class AccountMove(models.Model):
    _inherit = 'account.move'

    visit_id = fields.Many2one('vet.animal.visit', string="Animal Visit")
    extract_error_message = fields.Char(string="Extract Error Message")
    animal_display_name = fields.Char(
        string="Animal Name",
        compute="_compute_animal_display_name",
        store=True
    )
    extract_document_uuid = fields.Char()
    extract_state = fields.Char()
    extract_attachment_id = fields.Many2one('ir.attachment')
    extract_can_show_send_button = fields.Boolean()
    extract_can_show_banners = fields.Boolean()
    @api.depends("visit_id", "visit_id.animal_id", "visit_id.animal_id.name")
    def _compute_animal_display_name(self):
        for move in self:
            move.animal_display_name = move.visit_id.animal_id.name if move.visit_id and move.visit_id.animal_id else ""

    def action_manual_send_for_digitization(self):
        pass  # Implement digitization logic here

    def action_reload_ai_data(self):
        pass  # Implement reload logic here

class AccountPayment(models.Model):
    _inherit = 'account.payment'

    def action_post(self):
        res = super(AccountPayment, self).action_post()

        for payment in self:
            invoices = payment.invoice_ids
            if invoices and payment.move_id:
                lines_to_reconcile = payment.move_id.line_ids | invoices.mapped('line_ids')
                if lines_to_reconcile:
                    try:
                        lines_to_reconcile.reconcile()
                    except Exception as e:
                        _logger.warning("Reconciliation failed: %s", e)
        return res
