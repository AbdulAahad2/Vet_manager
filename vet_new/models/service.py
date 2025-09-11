from odoo import models, fields, api
from odoo.exceptions import UserError


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
            service_type = vals.get('service_type', 'service')
            if service_type == 'service':
                prod_type = 'service'
            elif service_type == 'vaccine':
                prod_type = 'product'
            elif service_type == 'test':
                prod_type = 'consu'
            else:
                prod_type = 'service'

            product_vals = {
                'name': vals.get('name'),
                'list_price': vals.get('price', 0),
                'type': prod_type,
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
                if 'service_type' in vals:
                    if service.service_type == 'service':
                        service.product_id.type = 'service'
                    elif service.service_type == 'vaccine':
                        service.product_id.type = 'product'
                    elif service.service_type == 'test':
                        service.product_id.type = 'consu'
        return res

    @api.onchange('product_id')
    def _onchange_product_id(self):
        if self.product_id:
            self.price = self.product_id.list_price or 0
            if not self.name:
                self.name = self.product_id.name

    def action_add_product(self):
        """Ensure product exists, do not open product screen"""
        self.ensure_one()
        if not self.product_id:
            # Force product creation if missing
            service_type = self.service_type or 'service'
            if service_type == 'service':
                prod_type = 'service'
            elif service_type == 'vaccine':
                prod_type = 'product'
            elif service_type == 'test':
                prod_type = 'consu'
            else:
                prod_type = 'service'

            product_vals = {
                'name': self.name,
                'list_price': self.price,
                'type': prod_type,
            }
            product = self.env['product.product'].create(product_vals)
            self.product_id = product.id
        return True

