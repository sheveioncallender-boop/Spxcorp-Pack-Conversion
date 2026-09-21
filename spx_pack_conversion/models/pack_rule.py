from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError
from odoo.tools import SQL


class PackRule(models.Model):
    _name = 'spx.pack.rule'
    _description = 'Pack Configuration'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _check_company_auto = True
    _order = 'name, id'

    name = fields.Char(required=True, tracking=True)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company)
    pack_product_id = fields.Many2one('product.product', 'Pack Product', required=True, ondelete='restrict', check_company=True, tracking=True)
    unit_product_id = fields.Many2one('product.product', 'Contained Product', required=True, ondelete='restrict', check_company=True, tracking=True)
    units_per_pack = fields.Integer('Quantity Inside One Pack', required=True, default=24, tracking=True)
    allow_repack = fields.Boolean('Allow Repacking', tracking=True, help='Permit contained items to be physically assembled back into this pack. Leave off for sealed packs and medicines that must not be repacked.')
    pack_price = fields.Float('Pack Selling Price', related='pack_product_id.lst_price', readonly=False, groups='spx_pack_conversion.group_pack_manager')
    unit_price = fields.Float('Contained Item Selling Price', related='unit_product_id.lst_price', readonly=False, groups='spx_pack_conversion.group_pack_manager')
    currency_id = fields.Many2one(related='company_id.currency_id')
    pack_barcode = fields.Char('Pack Barcode', related='pack_product_id.barcode', readonly=False, groups='spx_pack_conversion.group_pack_manager')
    unit_barcode = fields.Char('Contained Item Barcode', related='unit_product_id.barcode', readonly=True)
    pack_on_hand = fields.Float(related='pack_product_id.qty_available', string='Packs On Hand')
    unit_on_hand = fields.Float(related='unit_product_id.qty_available', string='Contained Items On Hand')
    conversion_ids = fields.One2many('spx.pack.conversion', 'rule_id')
    conversion_count = fields.Integer(compute='_compute_conversion_count')

    _source_company_unique = models.Constraint('UNIQUE(pack_product_id, company_id)', 'A pack product can have only one breakdown per company. Use separate products for different pack sizes.')
    _positive_ratio = models.Constraint('CHECK(units_per_pack > 0)', 'The contained quantity must be a positive whole number.')

    @api.depends('conversion_ids')
    def _compute_conversion_count(self):
        for rule in self:
            rule.conversion_count = len(rule.conversion_ids)

    @api.constrains('pack_product_id', 'unit_product_id', 'units_per_pack', 'company_id')
    def _check_configuration(self):
        for rule in self:
            if rule.pack_product_id == rule.unit_product_id:
                raise ValidationError(_('The pack and its contents must be different products.'))
            products = rule.pack_product_id | rule.unit_product_id
            kits = self.env['mrp.bom']._bom_find(products, company_id=rule.company_id.id, bom_type='phantom')
            if any(kits.values()):
                raise ValidationError(_('Use independently stocked products, not Kit bills of materials, for pack conversion. Archive the kit configuration or use separate pack products.'))
            for product in products:
                if not product.is_storable or product.type != 'consu':
                    raise ValidationError(_('Enable Track Inventory on both products.'))
                if product.tracking == 'serial':
                    raise ValidationError(_('Pack conversion supports untracked stock or batches/lots, not individual serial numbers.'))
                if product.product_tmpl_id.product_variant_count != 1:
                    raise ValidationError(_('Use separate single-variant products for each pack form so their selling prices stay independent.'))
            if rule.pack_product_id.tracking != rule.unit_product_id.tracking:
                raise ValidationError(_('Both products must use the same tracking method: no tracking or batches/lots.'))
            if rule.pack_product_id.use_expiration_date != rule.unit_product_id.use_expiration_date:
                raise ValidationError(_('Enable expiration dates on both products, or neither.'))
            visited = {rule.pack_product_id.id}
            current = rule.unit_product_id
            rules = self.with_context(active_test=False).search([('company_id', '=', rule.company_id.id)])
            next_product = {r.pack_product_id.id: r.unit_product_id for r in rules}
            while current:
                if current.id in visited:
                    raise ValidationError(_('Pack breakdowns cannot form a circular chain. Use Allow Repacking for the reverse operation.'))
                visited.add(current.id)
                current = next_product.get(current.id)

    def write(self, vals):
        self.check_access('write')
        self.flush_recordset()
        if self.ids:
            self.env.cr.execute(SQL('SELECT id FROM spx_pack_rule WHERE id IN %s ORDER BY id FOR UPDATE', tuple(self.ids)))
            self.invalidate_recordset()
        if {'pack_product_id', 'unit_product_id', 'units_per_pack', 'company_id'} & vals.keys():
            if self.env['spx.pack.conversion'].search_count([('rule_id', 'in', self.ids)]):
                raise UserError(_('This configuration has conversion records. Use a new pack product for a different pack size; existing history must retain its meaning.'))
        return super().write(vals)

    def action_convert(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window', 'name': _('Convert Pack'),
            'res_model': 'spx.pack.conversion', 'view_mode': 'form',
            'context': {'default_rule_id': self.id, 'default_company_id': self.company_id.id},
        }

    def action_history(self):
        self.ensure_one()
        return {'type': 'ir.actions.act_window', 'name': _('Conversion History'), 'res_model': 'spx.pack.conversion', 'view_mode': 'list,form', 'domain': [('rule_id', '=', self.id)]}
