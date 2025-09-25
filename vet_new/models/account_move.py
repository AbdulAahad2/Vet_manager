# models/account_move_inherit.py
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
    amount_paid = fields.Monetary(
        string="Amount Paid",
        compute="_compute_amount_paid",
        currency_field="currency_id",
        store=True
    )
    extract_document_uuid = fields.Char()
    extract_state = fields.Char()
    extract_attachment_id = fields.Many2one('ir.attachment')
    extract_can_show_send_button = fields.Boolean()
    extract_can_show_banners = fields.Boolean()

    def action_print_visit_receipt_from_invoice(self):
        """
        Return the visit receipt report action for visits related to this/these invoice(s).
        Lookup order:
          1) invoice.visit_id (explicit link)
          2) invoice_origin matching vet.animal.visit.name
          3) try to find visit by visit_id on invoice lines (if you add that later)
        This method consolidates visits into a recordset and returns the visit report action.
        """
        self.ensure_one()
        invoices = self if len(self) == 1 else self

        # 1) explicit relation(s)
        visits = invoices.mapped('visit_id').filtered(lambda v: v.exists())

        # 2) if none, try invoice_origin -> visit.name match (safe)
        if not visits:
            origins = list(set(invoices.mapped('invoice_origin')))
            if origins:
                visits = self.env['vet.animal.visit'].search([('name', 'in', origins)])
                visits = visits.filtered(lambda v: v.exists())

        # 3) (optional) could add more heuristics here if needed

        if not visits:
            raise UserError(_("No related visit found for this invoice to print a visit receipt."))

        # Return the visit receipt action (report_action handles multiple visits)
        return self.env.ref('vet_new.action_report_visit_receipt').report_action(visits)

    @api.depends("visit_id", "visit_id.animal_id", "visit_id.animal_id.name")
    def _compute_animal_display_name(self):
        for move in self:
            move.animal_display_name = move.visit_id.animal_id.name if move.visit_id and move.visit_id.animal_id else ""

    def action_manual_send_for_digitization(self):
        pass

    def action_reload_ai_data(self):
        pass

    @api.depends("amount_total", "amount_residual")
    def _compute_amount_paid(self):
        for move in self:
            move.amount_paid = move.amount_total - move.amount_residual

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
