from odoo import api, fields, models, _
from odoo.exceptions import UserError
from odoo.exceptions import ValidationError
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
    animal_name = fields.Many2one(
        'vet.animal',
        string="Animal Name",
    )
    animal_display_name = fields.Char(
        string="Animal Name",
        compute="_compute_animal_display_name",
        store=True
    )
    animal_pic = fields.Image(
        string="Animal Picture",
        related='animal_id.image_1920',
        store=True,
        readonly=False,

    )
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

    # ------------------------
    # Visit Lines
    # ------------------------
    line_ids = fields.One2many('vet.animal.visit.line', 'visit_id', string="Visit Lines")
    medicine_line_ids = fields.One2many('vet.animal.visit.line', 'visit_id',
                                        domain=[('service_id.service_type', '=', 'vaccine')],
                                        string="Medicine Lines")
    service_line_ids = fields.One2many('vet.animal.visit.line', 'visit_id',
                                       domain=[('service_id.service_type', '=', 'service')],
                                       string="Service Lines")
    test_line_ids = fields.One2many('vet.animal.visit.line', 'visit_id',
                                    domain=[('service_id.service_type', '=', 'test')],
                                    string="Test Lines")
    receipt_lines = fields.One2many('vet.animal.visit.line','visit_id', compute='_compute_receipt_lines', string="Receipt Lines")

    # ------------------------
    # Invoicing & Payment
    # ------------------------
    invoice_ids = fields.One2many('account.move', 'visit_id', string="Invoices", ondelete='set null')
    payment_state = fields.Selection([('not_paid', 'Not Paid'),
                                      ('partial', 'Partially Paid'),
                                      ('paid', 'Paid')],
                                     string="Payment Status", compute="_compute_payment_state", store=True)
    has_unpaid_invoice = fields.Boolean(
        string="Has Unpaid Invoice",
        compute="_compute_has_unpaid_invoice",
        store=True
    )
    state = fields.Selection([('draft', 'Draft'),
                              ('confirmed', 'Confirmed'),
                              ('done', 'Done'),
                              ('cancel', 'Cancelled')],
                             default='draft')
    delivered = fields.Boolean(default=False, string="Vaccines Delivered")

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
    # ------------------------
    # Create / Write
    # ------------------------
    @api.model
    def create(self, vals):
        if vals.get("name", _("New")) == _("New"):
            vals["name"] = self.env["ir.sequence"].next_by_code("vet.animal.visit") or "VIS00000"
        return super().create(vals)

    def write(self, vals):
        return super().write(vals)

    # ------------------------
    # Auto-fill Owner / Animal
    # ------------------------

    @api.depends("animal_id")
    def _compute_animal_display_name(self):
        for record in self:
            record.animal_display_name = record.animal_id.name if record.animal_id else ""
    @api.depends('owner_id', 'contact_number')
    def _compute_animals_for_owner(self):
        for record in self:
            domain = []
            if record.owner_id:
                animals = self.env['vet.animal'].search([('owner_id', '=', record.owner_id.id)])
            elif record.contact_number:
                partners = self.env['res.partner'].search([('phone', '=', record.contact_number)])
                animals = self.env['vet.animal'].search([('owner_id', 'in', partners.ids)]) if partners else self.env[
                    'vet.animal'].browse()
            else:
                animals = self.env['vet.animal'].browse()
            record.animal_ids = animals

    @api.onchange('owner_id')
    def _onchange_owner_id(self):
        """
        When Owner is selected:
        - set contact_number
        - filter animal_id domain to owner’s animals
        - if only one animal, auto-select it
        """
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
        """
        Auto-fill owner based on contact number and filter animals.
        """
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
        """
        When animal is chosen:
        - Auto-fill owner_id, contact_number
        - Auto-populate animal_ids
        - Sync selected_animal_id and animal_name
        """
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
    # Totals & Receipt Lines
    # ------------------------
    @api.depends('service_line_ids.subtotal', 'test_line_ids.subtotal', 'medicine_line_ids.subtotal',
                 'treatment_charge', 'discount_percent', 'discount_fixed')
    def _compute_totals(self):
        for visit in self:
            all_lines = visit.service_line_ids + visit.test_line_ids + visit.medicine_line_ids
            subtotal = sum(line.subtotal for line in all_lines)
            visit.subtotal = subtotal

            total = subtotal + (visit.treatment_charge or 0)

            if visit.discount_percent > 0:
                total -= total * (visit.discount_percent / 100.0)
            elif visit.discount_fixed > 0:
                total -= visit.discount_fixed

            visit.total_amount = total

    @api.depends('service_line_ids.quantity', 'service_line_ids.price_unit',
                 'test_line_ids.quantity', 'test_line_ids.price_unit',
                 'medicine_line_ids.quantity', 'medicine_line_ids.price_unit')
    def _compute_receipt_lines(self):
        for visit in self:
            all_lines = visit.service_line_ids + visit.test_line_ids + visit.medicine_line_ids
            visit.receipt_lines = all_lines.filtered(lambda l: l.quantity > 0 and l.product_id)

    # ------------------------
    # Payment Status
    # ------------------------
    @api.depends('invoice_ids.payment_state')
    def _compute_payment_state(self):
        for visit in self:
            if not visit.invoice_ids:
                visit.payment_state = 'not_paid'
            elif all(inv.payment_state == 'paid' for inv in visit.invoice_ids):
                visit.payment_state = 'paid'
            elif any(inv.payment_state in ['paid', 'partial'] for inv in visit.invoice_ids):
                visit.payment_state = 'partial'
            else:
                visit.payment_state = 'not_paid'

    @api.depends('invoice_ids', 'invoice_ids.payment_state')
    def _compute_has_unpaid_invoice(self):
        for visit in self:
            visit.has_unpaid_invoice = any(
                inv.payment_state in ['not_paid', 'partial'] for inv in visit.invoice_ids
            )

    # ------------------------
    # Partner Helper
    # ------------------------
    def _get_or_create_partner_from_owner(self, owner):
        self.ensure_one()
        if owner.partner_id:
            return owner.partner_id
        partner = self.env['res.partner'].create({
            'name': owner.name,
            'phone': owner.contact_number,
            'email': owner.email,
        })
        owner.partner_id = partner.id
        return partner

    # ------------------------
    # Invoice Creation (non-payable initially, prevent multiple invoices)
    # ------------------------

    @api.constrains('discount_percent', 'discount_fixed')
    def _check_discount_conflict(self):
        for visit in self:
            if visit.discount_percent > 0 and visit.discount_fixed > 0:
                raise ValidationError(
                    _("You cannot use both Discount (%) and Discount (Fixed) at the same time. Please use only one."))

    def action_create_invoice(self):
        for visit in self:
            if not visit.owner_id:
                raise UserError("Please select an Owner before creating an invoice.")

            # Prevent multiple invoices
            if visit.invoice_ids:
                raise UserError("An invoice has already been created for this visit.")

            # Get or create partner
            partner = visit._get_or_create_partner_from_owner(visit.owner_id)
            invoice_lines = []

            # Include all service, test, medicine lines
            all_lines = visit.service_line_ids + visit.test_line_ids + visit.medicine_line_ids
            for line in all_lines.filtered(lambda l: l.service_id.product_id):
                invoice_lines.append((0, 0, {
                    'name': line.service_id.name,
                    'product_id': line.service_id.product_id.id,
                    'quantity': line.quantity,
                    'price_unit': line.price_unit,
                    'tax_ids': [(6, 0, line.service_id.product_id.taxes_id.ids)],
                }))
                line.invoiced = True

            # Treatment charge
            if visit.treatment_charge:
                product = self.env.ref('vet_new.treatment_charge_product_new').product_variant_id
                invoice_lines.append((0, 0, {
                    'name': 'Treatment Charge',
                    'product_id': product.id,
                    'quantity': 1,
                    'price_unit': visit.treatment_charge,
                }))

            # Discount
            discount_product = self.env.ref('vet_new.discount_product_new').product_variant_id
            if visit.discount_percent > 0:
                discount_value = (visit.subtotal + (visit.treatment_charge or 0)) * (visit.discount_percent / 100.0)
                invoice_lines.append((0, 0, {
                    'name': f"Discount ({visit.discount_percent}%)",
                    'product_id': discount_product.id,
                    'quantity': 1,
                    'price_unit': -abs(discount_value),
                }))
            elif visit.discount_fixed > 0:
                invoice_lines.append((0, 0, {
                    'name': "Discount (Fixed)",
                    'product_id': discount_product.id,
                    'quantity': 1,
                    'price_unit': -abs(visit.discount_fixed),
                }))

            # Create invoice and link to visit
            invoice = self.env['account.move'].create({
                'move_type': 'out_invoice',
                'partner_id': partner.id,
                'invoice_date': fields.Date.context_today(self),
                'visit_id': visit.id,  # Make sure account.move has this field
                'invoice_line_ids': invoice_lines,
            })

            # Post invoice
            invoice.action_post()

            # Link invoice to visit
            visit.invoice_ids = [(4, invoice.id)]
            _logger.info("Invoice %s created for visit %s", invoice.name, visit.name)

        # ------------------------
        # Payment Button & Print Invoice
        # ------------------------

    def action_pay_invoice(self):
        """Pay invoices and open the standard invoice Print Preview."""
        self.ensure_one()

        if not self.invoice_ids:
            raise UserError(_("No invoice found for this visit."))

        for invoice in self.invoice_ids:
            # Post draft invoices if needed
            if invoice.state == 'draft':
                invoice.with_context(mail_auto_subscribe_no_notify=True).action_post()

            # Pay residual amount if any
            if invoice.amount_residual > 0:
                journal = self.env['account.journal'].search([('type', '=', 'bank')], limit=1)
                if not journal:
                    raise UserError(_("No bank journal found for payment."))

                payment = self.env['account.payment'].create({
                    'payment_type': 'inbound',
                    'partner_type': 'customer',
                    'partner_id': invoice.partner_id.id,
                    'amount': invoice.amount_residual,
                    'payment_method_id': self.env.ref('account.account_payment_method_manual_in').id,
                    'journal_id': journal.id,
                    'date': fields.Date.context_today(self),
                })
                payment.with_context(mail_auto_subscribe_no_notify=True).action_post()

                # Reconcile invoice with payment
                (invoice.line_ids + payment.move_id.line_ids).filtered(
                    lambda l: l.account_id.reconcile and l.partner_id == invoice.partner_id
                ).reconcile()

        # Mark visit as done and deliver vaccines
        self.state = 'done'
        self.action_deliver_vaccines()

        # Open standard Odoo invoice print preview
        return self.env.ref('vet_new.action_report_receipt').report_action(self.invoice_ids[0])

    # ------------------------
    # Deliver Vaccines
    # ------------------------
    def action_deliver_vaccines(self):
        StockPicking = self.env['stock.picking']
        StockMove = self.env['stock.move']
        StockMoveLine = self.env['stock.move.line']
        PickingType = self.env['stock.picking.type']

        for visit in self:
            if visit.delivered:
                continue

            origin = f"Visit {visit.name}"
            picking_type = PickingType.search([('code', '=', 'outgoing')], limit=1)
            if not picking_type:
                raise UserError(_("Please configure an outgoing picking type."))

            picking = StockPicking.create({
                'picking_type_id': picking_type.id,
                'location_id': picking_type.default_location_src_id.id,
                'location_dest_id': picking_type.default_location_dest_id.id or self.env.ref('stock.stock_location_customers').id,
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
        """Open a smart button to see invoices for this visit"""
        return {
            'name': _("Invoices"),
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'view_mode': 'list,form',
            'domain': [('id', 'in', self.invoice_ids.ids)],
            'context': {'default_visit_id': self.id},
        }
    @api.onchange('owner_id')
    def _onchange_owner_selected_animals(self):
        """Limit Select Animal field to Owner’s Animals"""
        if self.owner_id:
            return {
                'domain': {
                    'selected_animal_id': [('owner_id', '=', self.owner_id.id)]
                }
            }
        return {'domain': {'selected_animal_id': []}}

    @api.onchange('selected_animal_id')
    def _onchange_selected_animal_id(self):
        """
        When user selects an animal:
        - Set main animal_id and animal_name
        - Auto-fill owner and their animals
        """
        if self.selected_animal_id:
            self.animal_id = self.selected_animal_id
            self.animal_name = self.selected_animal_id
            self.owner_id = self.selected_animal_id.owner_id
            self.contact_number = self.selected_animal_id.owner_id.contact_number or ''
            # Populate all animals of this owner
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


# ------------------------
# Extend vet.animal display
# ------------------------
class VetAnimal(models.Model):
    _inherit = "vet.animal"

    def name_get(self):
        result = []
        for animal in self:
            parts = []
            if animal.microchip_no:  # Use microchip number instead of ID
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
    @api.model
    def name_search(self, name='', args=None, operator='ilike', limit=100):
        """
        Search animals by:
        - Animal name (default)
        - Microchip number (microchip_no, usually starts with HT)
        - "#HT123" → exact match on microchip_no
        """
        args = args or []
        name = (name or '').strip()
        if not name:
            return self.search(args, limit=limit).name_get()

        domain = []
        if name.startswith('#'):
            # Exact match on microchip_no (strip #)
            chip = name[1:].strip()
            domain = [('microchip_no', '=', chip)]
        else:
            # Search both microchip_no and name with operator
            domain = ['|', ('microchip_no', operator, name), ('name', operator, name)]

        try:
            records = self.search(domain + args, limit=limit)
            return records.name_get()
        except Exception as exc:
            _logger.exception("vet.animal.name_search failed: %s", exc)
            return []