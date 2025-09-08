from odoo import models, fields, api
from odoo.exceptions import UserError

# -------------------------
# Vet Service Model
# -------------------------
class VetService(models.Model):
    _name = "vet.service"
    _description = "Vet Service / Test / Vaccine"
    _order = "name"

    name = fields.Char("Name", required=True)
    service_type = fields.Selection([
        ('service', 'Service'),
        ('vaccine', 'Vaccine'),
        ('test', 'Test')
    ], string="Type", required=True, default='service')
    price = fields.Float("Price", required=True)
    product_id = fields.Many2one(
        "product.product",
        string="Linked Product",
        ondelete="set null"
    )
    description = fields.Text("Description")

    # Auto-create product if missing
    @api.model
    def create(self, vals):
        if not vals.get('product_id'):
            product_vals = {
                'name': vals.get('name'),
                'list_price': vals.get('price', 0),
                'type': 'consu',
            }
            product = self.env['product.product'].create(product_vals)
            vals['product_id'] = product.id
        return super().create(vals)

    # Keep product in sync
    def write(self, vals):
        res = super().write(vals)
        for service in self:
            if service.product_id:
                if 'price' in vals:
                    service.product_id.list_price = service.price
                if 'name' in vals:
                    service.product_id.name = service.name
        return res

    @api.onchange('product_id')
    def _onchange_product_id(self):
        if self.product_id:
            self.price = self.product_id.list_price or 0
            if not self.name:
                self.name = self.product_id.name

    def action_create_delivery(self):
        self.ensure_one()
        if not self.product_id:
            raise UserError("Please link a product to this service before creating a delivery.")

        StockPicking = self.env['stock.picking']
        StockMove = self.env['stock.move']

        picking_type = self.env.ref('stock.picking_type_out')  # standard delivery
        partner = self.env.user.partner_id

        picking = StockPicking.create({
            'partner_id': partner.id,
            'picking_type_id': picking_type.id,
            'location_id': picking_type.default_location_src_id.id,
            'location_dest_id': partner.property_stock_customer.id,
            'origin': f"Vet Service: {self.name}",
        })

        StockMove.create({
            'name': self.name,
            'product_id': self.product_id.id,
            'product_uom_qty': 1,
            'product_uom': self.product_id.uom_id.id,
            'picking_id': picking.id,
            'location_id': picking.location_id.id,
            'location_dest_id': picking.location_dest_id.id,
        })

        picking.action_confirm()
        picking.action_assign()

        return {
            "type": "ir.actions.act_window",
            "res_model": "stock.picking",
            "view_mode": "form",
            "res_id": picking.id,
        }