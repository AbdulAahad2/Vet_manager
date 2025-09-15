from odoo import models, fields, api


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

    # Helper: map vet.service.service_type → product.type
    def _map_service_type_to_product_config(self, service_type):
        """Return product type and tracking based on service_type"""
        mapping = {
            'service': {'type': 'service', 'tracking': 'none'},  # Service
            'vaccine': {'type': 'consu', 'tracking': 'lot'},  # Vaccine → Consumable + Tracking by Lots
            'test': {'type': 'consu', 'tracking': 'none'},  # Test → Consumable (no tracking)
        }
        return mapping.get(service_type, {'type': 'service', 'tracking': 'none'})

    # Auto-create product if missing
    @api.model
    def create(self, vals):
        if not vals.get('product_id'):
            config = self._map_service_type_to_product_config(
                vals.get('service_type', 'service')
            )
            product_vals = {
                'name': vals.get('name'),
                'list_price': vals.get('price', 0),
                'type': config['type'],
                'tracking': config['tracking'],
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
                    config = self._map_service_type_to_product_config(service.service_type)
                    service.product_id.type = config['type']
                    service.product_id.tracking = config['tracking']
        return res
    @api.onchange('product_id')
    def _onchange_product_id(self):
        if self.product_id:
            self.price = self.product_id.list_price or 0
            if not self.name:
                self.name = self.product_id.name

    def action_add_product(self):
        """Open product creation form with defaults instead of auto-creating"""
        self.ensure_one()
        config = self._map_service_type_to_product_config(self.service_type or 'service')

        return {
            'name': 'Add Product',
            'type': 'ir.actions.act_window',
            'res_model': 'product.product',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_name': self.name,
                'default_list_price': self.price,
                'default_type': config['type'],
                'default_tracking': config['tracking'],
            }
        }

