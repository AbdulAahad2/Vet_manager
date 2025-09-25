from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError
import logging

_logger = logging.getLogger(__name__)

class VetAnimalVisit(models.Model):
    _name = "vet.animal.visit"
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = "Animal Visit"
    _order = "date desc"
    _rec_name = "name"

    # ------------------------
    # Basic Info
    # ------------------------
    name = fields.Char(string="Visit Reference", readonly=True, copy=False, default=lambda self: _("New"))
    date = fields.Datetime(default=fields.Datetime.now)
    animal_id = fields.Many2one("vet.animal", string="Animal", required=True)
    selected_animal_id = fields.Many2one('vet.animal', string="Select Animal")
    animal_ids = fields.Many2many('vet.animal', compute='_compute_animals_for_owner', string="Owner's Animals")
    animal_name = fields.Many2one('vet.animal', string="Animal Name")
    animal_display_name = fields.Char(string="Animal Name", compute="_compute_animal_display_name", store=True)
    animal_pic = fields.Image(string="Animal Picture", related='animal_id.image_1920', store=True, readonly=False)
    debug_animal_pic = fields.Char(compute="_compute_debug_animal_pic")
    owner_id = fields.Many2one('vet.animal.owner', string="Owner")
    contact_number = fields.Char(string="Owner Contact")
    doctor_id = fields.Many2one("vet.animal.doctor", string="Doctor")
    notes = fields.Text("Notes")
    treatment_charge = fields.Float(default=0.0)
    discount_percent = fields.Float(string="Discount (%)", default=0.0)
    discount_fixed = fields.Float(string="Discount (Fixed)", default=0.0)
    subtotal = fields.Float(compute='_compute_totals', store=True)
    total_amount = fields.Float(compute='_compute_totals', store=True)

    is_fully_paid = fields.Boolean(
        string="Fully Paid",
        compute="_compute_is_fully_paid",
        store=False
    )

    # ------------------------
    # Visit Lines
    # ------------------------
    line_ids = fields.One2many('vet.animal.visit.line', 'visit_id', string="Visit Lines")
    medicine_line_ids = fields.One2many(
        'vet.animal.visit.line', 'visit_id',
        domain=[('service_id.service_type', '=', 'vaccine')],
        string="Medicine Lines"
    )
    service_line_ids = fields.One2many(
        'vet.animal.visit.line', 'visit_id',
        domain=[('service_id.service_type', '=', 'service')],
        string="Service Lines"
    )
    test_line_ids = fields.One2many(
        'vet.animal.visit.line', 'visit_id',
        domain=[('service_id.service_type', '=', 'test')],
        string="Test Lines"
    )
    receipt_lines = fields.One2many('vet.animal.visit.line', 'visit_id', compute='_compute_receipt_lines', string="Receipt Lines")

    # ------------------------
    # Invoicing & Payment
    # ------------------------
    invoice_ids = fields.One2many('account.move', 'visit_id', string="Invoices")
    payment_state = fields.Selection(
        [('not_paid', 'Not Paid'), ('partial', 'Partially Paid'), ('paid', 'Paid')],
        string="Payment Status", compute="_compute_payment_state", store=True
    )
    has_unpaid_invoice = fields.Boolean(string="Has Unpaid Invoice", compute="_compute_has_unpaid_invoice", store=True)
    state = fields.Selection([('draft', 'Draft'), ('confirmed', 'Confirmed'), ('done', 'Done'), ('cancel', 'Cancelled')], default='draft')
    delivered = fields.Boolean(default=False, string="Vaccines Delivered")
    amount_received = fields.Float(compute='_compute_amount_received')
    latest_payment_amount = fields.Float(
        string="Latest Payment Amount",
        default=0.0,
        help="Amount of the most recent payment made for this visit."
    )

    owner_unpaid_balance = fields.Float(
        string="Unpaid Balance",
        compute="_compute_owner_unpaid_balance",
        store=False,
        digits=(16, 2),
    )

    # ------------------------
    # COMPUTES
    # ------------------------
    @api.depends('latest_payment_amount', 'invoice_ids', 'invoice_ids.state', 'invoice_ids.amount_residual')
    def _compute_amount_received(self):
        for visit in self:
            # Use the latest payment amount if available
            visit.amount_received = visit.latest_payment_amount or 0.0
    @api.depends('owner_id.partner_id')
    def _compute_has_unpaid_invoice(self):
        AccountMove = self.env['account.move']
        for visit in self:
            has_unpaid = False
            partner = visit.owner_id.partner_id
            if partner:
                unpaid = AccountMove.search_count([
                    ('partner_id', '=', partner.id),
                    ('move_type', '=', 'out_invoice'),
                    ('payment_state', 'in', ['not_paid', 'partial']),
                ])
                has_unpaid = unpaid > 0
            visit.has_unpaid_invoice = has_unpaid

    @api.depends('payment_state')
    def _compute_is_fully_paid(self):
        for visit in self:
            old_state = visit.state
            visit.is_fully_paid = visit.payment_state == 'paid'
            if visit.state not in ['cancel']:
                new_state = 'done' if visit.payment_state == 'paid' else 'confirmed'
                if visit.state != new_state:
                    visit.state = new_state
                    _logger.info("Visit %s: State changed from %s to %s (payment_state=%s, is_fully_paid=%s)",
                                 visit.name, old_state, new_state, visit.payment_state, visit.is_fully_paid)
                else:
                    _logger.info(
                        "Visit %s: No state change needed, payment_state=%s, is_fully_paid=%s, current_state=%s",
                        visit.name, visit.payment_state, visit.is_fully_paid, visit.state)

    @api.depends('animal_id', 'animal_id.image_1920')
    def _compute_debug_animal_pic(self):
        for rec in self:
            if rec.animal_id:
                _logger.info(
                    "VetAnimalVisit[%s]: animal_id=%s, image_1920 exists=%s, animal_pic exists=%s",
                    rec.id,
                    rec.animal_id.name,
                    bool(rec.animal_id.image_1920),
                    bool(rec.animal_pic)
                )
                rec.debug_animal_pic = str(bool(rec.animal_pic))
            else:
                _logger.warning("VetAnimalVisit[%s]: No animal_id set", rec.id)
                rec.debug_animal_pic = "No animal_id"

    @api.depends('animal_id.image_1920')
    def _compute_animal_pic(self):
        for rec in self:
            rec.animal_pic = rec.animal_id.image_1920 or False

    @api.depends("animal_id")
    def _compute_animal_display_name(self):
        for record in self:
            record.animal_display_name = record.animal_id.name if record.animal_id else ""

    @api.depends('owner_id', 'contact_number')
    def _compute_animals_for_owner(self):
        for record in self:
            if record.owner_id:
                animals = self.env['vet.animal'].search([('owner_id', '=', record.owner_id.id)])
            elif record.contact_number:
                partners = self.env['res.partner'].search([('phone', '=', record.contact_number)])
                animals = self.env['vet.animal'].search([('owner_id', 'in', partners.ids)]) if partners else self.env['vet.animal'].browse()
            else:
                animals = self.env['vet.animal'].browse()
            record.animal_ids = animals

    @api.depends('service_line_ids.subtotal', 'test_line_ids.subtotal', 'medicine_line_ids.subtotal', 'treatment_charge', 'discount_percent', 'discount_fixed')
    def _compute_totals(self):
        for visit in self:
            all_lines = visit.service_line_ids + visit.test_line_ids + visit.medicine_line_ids
            subtotal = sum(line.subtotal for line in all_lines) if all_lines else 0.0
            visit.subtotal = subtotal
            total = subtotal + (visit.treatment_charge or 0.0)
            if visit.discount_percent > 0:
                total -= total * (visit.discount_percent / 100.0)
            elif visit.discount_fixed > 0:
                total -= visit.discount_fixed
            visit.total_amount = float(total or 0.0)

    @api.depends('service_line_ids.quantity', 'service_line_ids.price_unit', 'test_line_ids.quantity', 'test_line_ids.price_unit', 'medicine_line_ids.quantity', 'medicine_line_ids.price_unit')
    def _compute_receipt_lines(self):
        for visit in self:
            all_lines = visit.service_line_ids + visit.test_line_ids + visit.medicine_line_ids
            visit.receipt_lines = all_lines.filtered(lambda l: l.quantity > 0 and l.product_id)

    @api.depends('invoice_ids.payment_state')
    def _compute_payment_state(self):
        for visit in self:
            states = visit.invoice_ids.mapped('payment_state')
            if not states:
                visit.payment_state = 'not_paid'
            elif all(s == 'paid' for s in states):
                visit.payment_state = 'paid'
            elif any(s == 'partial' for s in states):
                visit.payment_state = 'partial'
            else:
                visit.payment_state = 'not_paid'

    @api.depends("owner_id")
    def _compute_owner_unpaid_balance(self):
        for visit in self:
            visit.owner_unpaid_balance = visit._get_owner_unpaid_balance()

    def action_confirm(self):
        for visit in self:
            if visit.state == 'draft':
                visit.state = 'confirmed'
                _logger.info("Visit %s: Confirmed, state set to 'confirmed'", visit.name)
                visit.message_post(body=_("Visit confirmed."))

    # ------------------------
    # Create / Write
    # ------------------------
    def _update_state_from_payment(self):
        for visit in self:
            if visit.state == 'cancel':
                continue
            if visit.payment_state == 'paid':
                visit.state = 'done'
            elif visit.invoice_ids:
                visit.state = 'confirmed'
            else:
                visit.state = 'draft'

    @api.model
    def create(self, vals):
        if vals.get("name", _("New")) == _("New"):
            vals["name"] = self.env["ir.sequence"].next_by_code("vet.animal.visit") or "VIS00000"
        return super().create(vals)

    def write(self, vals):
        # Skip validation for payment operations and state changes
        if self.env.context.get('skip_visit_validation') or self.env.context.get('from_payment_wizard'):
            return super().write(vals)

        for visit in self:
            if visit.state in ['confirmed', 'done']:
                # Allow state changes and payment-related updates
                if 'state' in vals or any(field in vals for field in ['latest_payment_amount']):
                    return super().write(vals)

                # Optionally allow specific fields to be editable
                allowed_fields = ['notes', 'latest_payment_amount']  # Adjust as needed
                # Only check for restricted fields that are actually being modified
                restricted_fields = [key for key in vals.keys() if key not in allowed_fields]
                if restricted_fields:
                    raise UserError(
                        _("Cannot modify visit %s in %s state. Only %s can be updated. "
                          "Fields attempted to modify: %s") % (
                            visit.name, visit.state, ', '.join(allowed_fields) or 'no fields',
                            ', '.join(restricted_fields)
                        )
                    )
        return super().write(vals)
    # ------------------------
    # Auto-fill Owner / Animal
    # ------------------------

    def print_visit_receipt(self):
        return self.env.ref('vet_new.action_report_visit_receipt').report_action(self)
    @api.onchange('owner_id')
    def _onchange_owner_id(self):
        domain = {'animal_id': []}
        if self.owner_id:
            self.contact_number = self.owner_id.contact_number or ''
            animals = self.env['vet.animal'].search([('owner_id', '=', self.owner_id.id)])
            if len(animals) == 1:
                self.animal_id = animals[0]
            domain = {'animal_id': [('owner_id', '=', self.owner_id.id)]}
        else:
            self.contact_number = ''
            self.animal_id = False
            domain = {'animal_id': [('id', '!=', False)]}
        return {'domain': domain}

    @api.onchange('contact_number')
    def _onchange_contact_number(self):
        self.owner_id = False
        self.animal_id = False
        if self.contact_number:
            owner = self.env['vet.animal.owner'].search([('contact_number', '=', self.contact_number.strip())], limit=1)
            if owner:
                self.owner_id = owner
                animals = self.env['vet.animal'].search([('owner_id', '=', owner.id)])
                if len(animals) == 1:
                    self.animal_id = animals[0]
                domain = {'animal_id': [('owner_id', '=', owner.id)]}
            else:
                domain = {'animal_id': [('id', '!=', False)]}
        else:
            domain = {'animal_id': [('id', '!=', False)]}
        return {'domain': domain, 'value': {'owner_id': self.owner_id, 'animal_id': self.animal_id}}

    @api.onchange('animal_id')
    def _onchange_animal_id(self):
        if not self.animal_id:
            self.owner_id = False
            self.contact_number = ''
            self.animal_ids = False
            self.selected_animal_id = False
            self.animal_name = False
            return
        self.owner_id = self.animal_id.owner_id
        self.contact_number = self.owner_id.contact_number or ''
        self.animal_ids = self.env['vet.animal'].search([('owner_id', '=', self.owner_id.id)])
        self.selected_animal_id = self.animal_id
        self.animal_name = self.animal_id

    # ------------------------
    # Invoice / Payment helpers
    # ------------------------

    def action_print_visit_receipt(self):
        self.ensure_one()
        if not self.exists():
            raise UserError(_("This visit record no longer exists."))
        _logger.info("Printing visit receipt - visit id=%s name=%s for user=%s", self.id, self.name, self.env.uid)
        return self.env.ref("vet_new.action_report_visit_receipt").report_action(self)

    @api.model
    def print_visit_receipt(self, docids):
        valid_visits = self.env['vet.animal.visit'].browse(docids).filtered(lambda r: r.exists())
        if not valid_visits:
            raise UserError(_("No valid visit records found to print."))
        return self.env.ref('vet_new.action_report_visit_receipt').report_action(valid_visits)

    def action_print_receipt(self):
        self.ensure_one()
        return self.env.ref("vet_new.report_visit_receipt").report_action(self)

    def _sync_state_with_payment(self):
        for visit in self:
            if visit.state == "cancel":
                continue
            if visit.payment_state == "paid":
                visit.state = "done"
            elif visit.payment_state in ["partial", "not_paid"] and visit.invoice_ids:
                visit.state = "confirmed"
            else:
                visit.state = "draft"

    @api.constrains('payment_state', 'state')
    def _constrain_payment_state(self):
        for visit in self:
            if visit.state not in ['draft', 'cancel']:
                expected_state = 'done' if visit.payment_state == 'paid' else 'confirmed'
                if visit.state != expected_state:
                    visit.state = expected_state
                    _logger.info("Visit %s: Constrained state to %s due to payment_state=%s",
                                 visit.name, expected_state, visit.payment_state)

    def _get_owner_unpaid_balance(self, exclude_visits=None):
        self.ensure_one()
        if not self.owner_id or not self.owner_id.partner_id:
            return 0.0

        domain = [
            ("partner_id", "=", self.owner_id.partner_id.id),
            ("move_type", "=", "out_invoice"),
            ("payment_state", "in", ["not_paid", "partial"]),
        ]
        if exclude_visits:
            domain.append(("visit_id", "not in", exclude_visits))

        result = self.env["account.move"].read_group(
            domain, ["amount_residual"], []
        )
        return result[0]["amount_residual"] if result else 0.0

    def _get_or_create_partner_from_owner(self, owner):
        if owner.partner_id:
            return owner.partner_id
        partner = self.env['res.partner'].create({
            'name': owner.name,
            'phone': owner.contact_number,
            'email': owner.email,
        })
        owner.partner_id = partner.id
        return partner

    @api.constrains('discount_percent', 'discount_fixed')
    def _check_discount_conflict(self):
        for visit in self:
            if visit.discount_percent > 0 and visit.discount_fixed > 0:
                raise ValidationError(_("You cannot use both Discount (%) and Discount (Fixed) at the same time. Please use only one."))

    def action_create_invoice(self):
        for visit in self:
            if visit.invoice_ids:
                raise UserError(_("An invoice already exists for this visit."))

            if not visit.owner_id or not visit.owner_id.partner_id:
                raise UserError(_("Please set an owner with a linked partner before creating an invoice."))

            partner = visit.owner_id.partner_id
            invoice_lines = []
            first_account_id = False

            Account = self.env['account.account']
            if 'account_type' in Account._fields:
                income_account = Account.search([('account_type', '=', 'income')], limit=1)
            else:
                income_account = Account.search([('user_type_id.type', '=', 'income')], limit=1)
            if income_account:
                first_account_id = income_account.id

            def _get_income_account_for_product(product):
                if not product:
                    return None
                tmpl = product.product_tmpl_id
                return (
                    product.property_account_income_id.id
                    or (tmpl.property_account_income_id.id if tmpl and tmpl.property_account_income_id else False)
                    or (
                        tmpl.categ_id.property_account_income_categ_id.id if tmpl and tmpl.categ_id and tmpl.categ_id.property_account_income_categ_id else False)
                )

            for service in visit.service_line_ids:
                prod, qty, price = service.product_id, service.quantity or 1.0, service.price_unit or 0.0
                account_id = _get_income_account_for_product(prod) or first_account_id
                if not account_id:
                    raise UserError(
                        _("Please configure an Income Account for product %s.") % (prod.display_name if prod else ""))
                if not first_account_id:
                    first_account_id = account_id
                invoice_lines.append((0, 0, {
                    'product_id': prod.id if prod else False,
                    'name': prod.display_name if prod else (
                        service.service_id.name if service.service_id else _("Service")),
                    'quantity': qty,
                    'price_unit': price,
                    'account_id': account_id,
                    'tax_ids': [(6, 0, prod.taxes_id.ids if prod else [])],
                }))

            for test in visit.test_line_ids:
                prod, qty, price = test.product_id, test.quantity or 1.0, test.price_unit or 0.0
                account_id = _get_income_account_for_product(prod) or first_account_id
                if not account_id:
                    raise UserError(
                        _("Please configure an Income Account for product %s.") % (prod.display_name if prod else ""))
                if not first_account_id:
                    first_account_id = account_id
                invoice_lines.append((0, 0, {
                    'product_id': prod.id if prod else False,
                    'name': prod.display_name if prod else (test.service_id.name if test.service_id else _("Test")),
                    'quantity': qty,
                    'price_unit': price,
                    'account_id': account_id,
                    'tax_ids': [(6, 0, prod.taxes_id.ids if prod else [])],
                }))

            for med in visit.medicine_line_ids:
                prod, qty, price = med.product_id, med.quantity or 1.0, med.price_unit or 0.0
                account_id = _get_income_account_for_product(prod) or first_account_id
                if not account_id:
                    raise UserError(
                        _("Please configure an Income Account for product %s.") % (prod.display_name if prod else ""))
                if not first_account_id:
                    first_account_id = account_id
                invoice_lines.append((0, 0, {
                    'product_id': prod.id if prod else False,
                    'name': prod.display_name if prod else (med.service_id.name if med.service_id else _("Medicine")),
                    'quantity': qty,
                    'price_unit': price,
                    'account_id': account_id,
                    'tax_ids': [(6, 0, prod.taxes_id.ids if prod else [])],
                }))

            if visit.treatment_charge and float(visit.treatment_charge) != 0.0:
                if not first_account_id:
                    raise UserError(_("Cannot determine an income account for Treatment Charge."))
                invoice_lines.append((0, 0, {
                    'product_id': False,
                    'name': _("Treatment Charge"),
                    'quantity': 1.0,
                    'price_unit': float(visit.treatment_charge),
                    'account_id': first_account_id,
                    'tax_ids': [(6, 0, [])],
                }))

            if visit.discount_percent > 0:
                for line in invoice_lines:
                    line[2]['discount'] = visit.discount_percent
            elif visit.discount_fixed > 0:
                if not first_account_id:
                    raise UserError(_("Please configure an Income Account for discounts."))
                invoice_lines.append((0, 0, {
                    'product_id': False,
                    'name': _("Discount"),
                    'quantity': 1.0,
                    'price_unit': -float(visit.discount_fixed),
                    'account_id': first_account_id,
                    'tax_ids': [(6, 0, [])],
                }))

            if not invoice_lines:
                raise UserError(_("No invoiceable lines found for this visit. To pay previous balances, use the Complete Payment action."))

            invoice_vals = {
                'partner_id': partner.id,
                'move_type': 'out_invoice',
                'invoice_line_ids': invoice_lines,
                'invoice_date': fields.Date.context_today(self),
                'invoice_origin': visit.name,
                'visit_id': visit.id,
            }
            invoice = self.env['account.move'].create(invoice_vals)

            missing_account_lines = invoice.invoice_line_ids.filtered(lambda l: not l.account_id)
            if missing_account_lines:
                fallback = invoice.invoice_line_ids[:1].account_id.id if invoice.invoice_line_ids[
                    :1].account_id else False
                if fallback:
                    missing_account_lines.write({'account_id': fallback})
                else:
                    raise UserError(_("Invoice created but some lines have no account. Configure income accounts."))

            invoice.action_post()
            visit.invoice_ids = [(4, invoice.id)]
            _logger.info("Invoice %s created and posted for visit %s", invoice.name, visit.name)
            visit._sync_state_with_payment()

            return True

    def action_pay_invoice(self):
        self.ensure_one()
        if not self.invoice_ids:
            raise UserError(_("No invoice found for this visit."))

        invoices = self.invoice_ids.filtered(lambda inv: inv.payment_state in ["not_paid", "partial"])
        if not invoices:
            raise UserError(_("All invoices are already paid."))

        return {
            "name": _("Register Payment"),
            "type": "ir.actions.act_window",
            "res_model": "vet.animal.visit.payment.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {"default_visit_id": self.id},
        }

    def action_deliver_vaccines(self):
        StockPicking = self.env['stock.picking']
        StockMove = self.env['stock.move']
        StockMoveLine = self.env['stock.move.line']

        for visit in self:
            if visit.delivered:
                continue
            origin = f"Visit {visit.name}"
            warehouse = self.env.user._get_default_warehouse_id()
            if not warehouse:
                raise UserError(_("Please set a default warehouse in your user preferences."))
            picking_type = warehouse.out_type_id
            try:
                dest_location = self.env.ref('stock.stock_location_customers').id
            except Exception:
                dest_location = False
                _logger.warning("stock.stock_location_customers not found; using default dest location.")

            picking = StockPicking.create({
                'picking_type_id': picking_type.id,
                'location_id': warehouse.lot_stock_id.id,
                'location_dest_id': dest_location,
                'origin': origin,
                'partner_id': visit.owner_id and visit._get_or_create_partner_from_owner(visit.owner_id).id or False,
            })

            moves_to_process = []
            for vline in visit.medicine_line_ids:
                product = vline.service_id.product_id
                if not product or product.type not in ('product', 'consu'):
                    continue
                move = StockMove.create({
                    'name': product.display_name,
                    'product_id': product.id,
                    'product_uom_qty': vline.quantity,
                    'product_uom': product.uom_id.id,
                    'picking_id': picking.id,
                    'location_id': picking.location_id.id,
                    'location_dest_id': picking.location_dest_id.id,
                })
                StockMoveLine.create({
                    'move_id': move.id,
                    'picking_id': picking.id,
                    'product_id': product.id,
                    'product_uom_id': product.uom_id.id,
                    'qty_done': vline.quantity,
                    'location_id': picking.location_id.id,
                    'location_dest_id': picking.location_dest_id.id,
                })
                moves_to_process.append(move)

            if moves_to_process:
                picking.action_confirm()
                picking.action_assign()
                picking.button_validate()
                visit.delivered = True
                for line in visit.medicine_line_ids:
                    line.delivered = True
            else:
                picking.unlink()

    def action_view_invoices(self):
        self.ensure_one()
        if not self.invoice_ids:
            return {'type': 'ir.actions.client', 'tag': 'display_notification',
                    'params': {'title': _("No Invoices"), 'message': _("No invoices exist for this visit."),
                               'sticky': False}}
        return {
            'name': _("Invoices"),
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'view_mode': 'list,form',
            'views': [
                (self.env.ref('vet_new.view_vet_animal_visit_invoice_list').id, 'list') if self.env.ref(
                    'vet_new.view_vet_animal_visit_invoice_list', False) else (False, 'list'),
                (self.env.ref('vet_new.view_vet_animal_visit_invoice_form').id, 'form') if self.env.ref(
                    'vet_new.view_vet_animal_visit_invoice_form', False) else (False, 'form')
            ],
            'domain': [('id', 'in', self.invoice_ids.ids)],
            'context': {'default_visit_id': self.id},
        }

    @api.onchange('owner_id')
    def _onchange_owner_selected_animals(self):
        if self.owner_id:
            return {'domain': {'selected_animal_id': [('owner_id', '=', self.owner_id.id)]}}
        return {'domain': {'selected_animal_id': []}}

    @api.onchange('selected_animal_id')
    def _onchange_selected_animal_id(self):
        if self.selected_animal_id:
            self.animal_id = self.selected_animal_id
            self.animal_name = self.selected_animal_id
            self.owner_id = self.selected_animal_id.owner_id
            self.contact_number = self.selected_animal_id.owner_id.contact_number or ''
            self.animal_ids = self.env['vet.animal'].search([('owner_id', '=', self.owner_id.id)])
        else:
            self.animal_id = False
            self.animal_name = ''
            self.owner_id = False
            self.contact_number = ''
            self.animal_ids = False

    @api.onchange('animal_name')
    def _onchange_animal_name(self):
        if self.animal_name:
            self.animal_id = self.animal_name
            self.selected_animal_id = self.animal_name
            self.owner_id = self.animal_name.owner_id
            self.contact_number = self.animal_name.owner_id.contact_number or ''
        else:
            self.animal_id = False
            self.selected_animal_id = False
            self.owner_id = False
            self.contact_number = ''

    def action_complete_payment(self):
        self.ensure_one()
        if not self.invoice_ids:
            raise UserError(_("No invoice found for this visit."))

        partner = self.owner_id.partner_id
        invoices = self.env['account.move'].search([
            ('partner_id', '=', partner.id),
            ('move_type', '=', 'out_invoice'),
            ('state', '=', 'posted'),
            ('payment_state', 'in', ['not_paid', 'partial']),
        ], order='invoice_date asc, id asc')

        if not invoices:
            raise UserError(_("No unpaid invoices found for this owner."))

        return {
            'name': _('Register Payment'),
            'type': 'ir.actions.act_window',
            'res_model': 'account.payment.register',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'active_model': 'account.move',
                'active_ids': invoices.ids,
                'default_partner_id': partner.id,
                'default_amount': sum(invoices.mapped('amount_residual')),
                'default_payment_type': 'inbound',
                'default_partner_type': 'customer',
            }
        }
class VetAnimal(models.Model):
    _inherit = "vet.animal"



    def name_get(self):
        result = []
        for animal in self:
            parts = []
            if animal.microchip_no:
                parts.append(f"#{animal.microchip_no}")
            if animal.name:
                parts.append(animal.name)
            if animal.owner_id:
                parts.append(f"Owner: {animal.owner_id.name}")
                if animal.owner_id.contact_number:
                    parts.append(f"Phone: {animal.owner_id.contact_number}")
            display = " | ".join(parts)
            result.append((animal.id, display))
        return result

    @api.model
    def name_search(self, name='', args=None, operator='ilike', limit=100):
        args = args or []
        name = (name or '').strip()
        if not name:
            return self.search(args, limit=limit).name_get()
        if name.startswith('#'):
            chip = name[1:].strip()
            domain = [('microchip_no', '=', chip)]
        else:
            domain = ['|', ('microchip_no', operator, name), ('name', operator, name)]
        try:
            records = self.search(domain + args, limit=limit)
            return records.name_get()
        except Exception as exc:
            _logger.exception("vet.animal.name_search failed: %s", exc)
            return []

    def action_view_invoices(self):
        self.ensure_one()
        return {
            'name': 'Invoices',
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'view_mode': 'list,form',
            'views': [
                (self.env.ref('vet_new.view_vet_animal_visit_invoice_list').id, 'list') if self.env.ref('vet_new.view_vet_animal_visit_invoice_list', False) else (False, 'list'),
                (self.env.ref('vet_new.view_vet_animal_visit_invoice_form').id, 'form') if self.env.ref('vet_new.view_vet_animal_visit_invoice_form', False) else (False, 'form')
            ],
            'domain': [('visit_id', 'in', self.env['vet.animal.visit'].search([('animal_id', '=', self.id)]).ids), ('payment_state', '!=', 'paid')],
            'context': {'create': False},
        }

class VetAnimalVisitPaymentWizard(models.TransientModel):
    _name = "vet.animal.visit.payment.wizard"
    _description = "Animal Visit Payment Wizard"

    visit_id = fields.Many2one("vet.animal.visit", string="Visit", required=True)
    payment_method = fields.Selection(
        [("cash", "Cash"), ("bank", "Bank")],
        string="Payment Method",
        required=True,
    )
    journal_id = fields.Many2one(
        "account.journal",
        string="Journal",
        domain="[('type', '=', payment_method)]",
        required=True,
        default=lambda self: self.env["account.journal"].search(
            [("type", "=", "cash")], limit=1
        ),
    )
    amount = fields.Float(string="Amount", required=True)

    def action_confirm_payment(self):
        """Register payment for the visit invoice(s) using Odoo 18 standard receipts,
        update latest payment amount, handle receipt generation, and update visit state."""
        self.ensure_one()

        # 1️⃣ Re-browse visit safely
        visit = self.env['vet.animal.visit'].browse(self.visit_id.id)
        if not visit.exists():
            raise UserError(_("The visit record does not exist or has been deleted."))

        invoices = visit.invoice_ids.filtered(lambda m: m.state == "posted")
        if not invoices:
            raise UserError(_("No posted invoice found for this visit."))

        partner = visit.owner_id.partner_id
        if not partner:
            raise UserError(_("Visit owner has no linked partner. Cannot process payment."))

        amount = self.amount
        total_residual = sum(invoices.mapped("amount_residual"))

        if amount <= 0:
            raise UserError(_("Payment amount must be greater than zero."))
        if amount > total_residual:
            raise UserError(
                _("You are trying to pay more (%.2f) than the remaining balance (%.2f).")
                % (amount, total_residual)
            )

        # 2️⃣ Update the latest payment amount on the visit
        visit.write({'latest_payment_amount': amount})
        _logger.info("Visit %s: Updated latest_payment_amount to %s", visit.name, amount)

        # 3️⃣ Try standard Odoo 18 payment register
        try:
            PaymentRegister = self.env['account.payment.register']
            ctx = {
                'active_model': 'account.move',
                'active_ids': invoices.ids,
                'default_amount': amount,
                'default_partner_id': partner.id,
                'default_payment_type': 'inbound',
                'default_partner_type': 'customer',
                'default_journal_id': self.journal_id.id,
            }
            payment_wizard = PaymentRegister.with_context(ctx).create({})
            payment_wizard._create_payments()
            _logger.info("Visit %s: Payment registered successfully via account.payment.register", visit.name)
        except Exception as e:
            _logger.warning("Standard payment register failed for visit %s, falling back to manual journal entry: %s",
                            visit.name, e)

            # 4️⃣ Fallback: Manual journal entry
            payment_move = self.env["account.move"].create({
                "move_type": "entry",
                "date": fields.Date.context_today(self),
                "line_ids": [
                    (0, 0, {
                        "name": "Payment",
                        "debit": 0.0,
                        "credit": amount,
                        "account_id": partner.property_account_receivable_id.id,
                        "partner_id": partner.id,
                    }),
                    (0, 0, {
                        "name": "Bank/Cash",
                        "debit": amount,
                        "credit": 0.0,
                        "account_id": self.journal_id.default_account_id.id,
                        "partner_id": partner.id,
                    }),
                ],
            })
            payment_move.action_post()

            # Partial reconciliation
            receivable_lines = invoices.mapped("line_ids").filtered(
                lambda l: l.account_id == partner.property_account_receivable_id and not l.reconciled
            )
            payment_lines = payment_move.line_ids.filtered(
                lambda l: l.account_id == partner.property_account_receivable_id
            )
            for payment_line in payment_lines:
                if not receivable_lines:
                    break
                line_to_reconcile = receivable_lines[0]
                (line_to_reconcile + payment_line).reconcile()
                receivable_lines -= line_to_reconcile
            _logger.info("Visit %s: Manual journal entry created and reconciled", visit.name)

        # 5️⃣ Recompute invoice states (no manual overrides!)
        invoices.invalidate_recordset(['payment_state', 'amount_residual'])

        # 6️⃣ Update visit payment state, amount received, and status
        if visit.exists():
            visit.invalidate_recordset(['payment_state', 'is_fully_paid', 'amount_received'])

            visit._sync_state_with_payment()


            _logger.info(
                "Visit %s: State=%s, payment_state=%s, is_fully_paid=%s, amount_received=%s",
                visit.name, visit.state, visit.payment_state, visit.is_fully_paid, visit.amount_received
            )

        # 7️⃣ Unified Return Receipt PDF
        try:
            return self.env.ref('account.account_payment_receipt_action').report_action(invoices)
        except Exception:
            _logger.warning("Invoice receipt action failed for visit %s; falling back to visit receipt.", visit.name,
                            exc_info=True)

        try:
            return invoices.action_print_visit_receipt_from_invoice()
        except UserError as ue:
            _logger.warning("No visit found for invoice(s) after payment for visit %s: %s", visit.name, ue)

        try:
            return {
                'type': 'ir.actions.report',
                'report_name': 'vet_new.report_visit_receipt',
                'report_type': 'qweb-pdf',
                'context': {'active_model': 'vet.animal.visit'},
                'docids': [visit.id],
            }
        except Exception as e:
            _logger.error("All receipt print attempts failed for visit %s: %s", visit.name, e)
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Receipt not available'),
                    'message': _('Payment posted, but no receipt could be generated.'),
                    'sticky': False,
                }
            }


# reports/report_visit_receipt.py
from odoo import api, models

class ReportVisitReceipt(models.AbstractModel):
    _name = 'report.vet_new.report_visit_receipt'
    _description = 'Visit Receipt Report'

    @api.model
    def _get_report_values(self, docids, data=None):
        docs = self.env['vet.animal.visit'].browse(docids)
        return {
            'doc_ids': docs.ids,
            'doc_model': 'vet.animal.visit',
            'docs': docs,
        }

