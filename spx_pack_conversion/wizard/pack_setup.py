from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError


class PackSetup(models.TransientModel):
    _name = 'spx.pack.setup'
    _description = 'Create a Pack Product'
    _check_company_auto = True

    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company)
    unit_product_id = fields.Many2one('product.product', 'Contained Product', required=True, check_company=True, domain="[('is_storable', '=', True), ('tracking', '!=', 'serial')]")
    name = fields.Char('New Pack Product Name', required=True)
    units_per_pack = fields.Integer('Quantity Inside One Pack', default=24, required=True)
    selling_price = fields.Float('Pack Selling Price', required=True, digits='Product Price')
    cost = fields.Float('Initial Cost Per Pack', required=True, digits='Product Price', help='Inventory cost, separate from the selling price. Purchases follow normal Odoo costing.')
    barcode = fields.Char('Pack Barcode')
    allow_repack = fields.Boolean('Allow Repacking')
    currency_id = fields.Many2one(related='company_id.currency_id')

    @api.onchange('unit_product_id', 'units_per_pack')
    def _onchange_product(self):
        if self.unit_product_id:
            self.name = _('%(product)s — Pack of %(qty)s', product=self.unit_product_id.name, qty=self.units_per_pack)
            self.cost = self.unit_product_id.with_company(self.company_id).standard_price * self.units_per_pack

    def action_create_pack(self):
        self.ensure_one()
        if not self.env.user.has_group('spx_pack_conversion.group_pack_manager'):
            raise UserError(_('Only a Pack Conversion manager can create pack products.'))
        self._check_company()
        if self.units_per_pack <= 0 or self.selling_price < 0 or self.cost < 0:
            raise ValidationError(_('Enter a positive whole pack size and non-negative prices.'))
        unit = self.unit_product_id
        vals = {
            'name': self.name, 'type': 'consu', 'is_storable': True,
            'company_id': self.company_id.id, 'categ_id': unit.categ_id.id,
            'uom_id': self.env.ref('uom.product_uom_unit').id,
            'list_price': self.selling_price, 'standard_price': self.cost,
            'barcode': self.barcode or False, 'sale_ok': True, 'purchase_ok': True,
            'tracking': unit.tracking, 'use_expiration_date': unit.use_expiration_date,
            'taxes_id': [fields.Command.set(unit.taxes_id.filtered(lambda t: t.company_id == self.company_id).ids)],
            'supplier_taxes_id': [fields.Command.set(unit.supplier_taxes_id.filtered(lambda t: t.company_id == self.company_id).ids)],
        }
        for field in ('expiration_time', 'use_time', 'removal_time', 'alert_time'):
            vals[field] = unit[field]
        if 'available_in_pos' in self.env['product.product']._fields:
            vals['available_in_pos'] = True
        with self.env.cr.savepoint():
            pack = self.env['product.product'].with_company(self.company_id).create(vals)
            rule = self.env['spx.pack.rule'].create({
                'name': self.name, 'company_id': self.company_id.id,
                'pack_product_id': pack.id, 'unit_product_id': unit.id,
                'units_per_pack': self.units_per_pack, 'allow_repack': self.allow_repack,
            })
        return {'type': 'ir.actions.act_window', 'res_model': 'spx.pack.rule', 'view_mode': 'form', 'res_id': rule.id, 'target': 'current'}
