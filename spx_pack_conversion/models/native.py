from odoo import api, fields, models, _
from odoo.exceptions import UserError

from .conversion import _INTERNAL


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    spx_pack_rule_count = fields.Integer(compute='_compute_spx_pack_rule_count', groups='spx_pack_conversion.group_pack_user')

    def _compute_spx_pack_rule_count(self):
        for product in self:
            product.spx_pack_rule_count = self.env['spx.pack.rule'].search_count(['|', ('pack_product_id', 'in', product.product_variant_ids.ids), ('unit_product_id', 'in', product.product_variant_ids.ids)])

    def action_spx_pack_rules(self):
        self.ensure_one()
        return {'type': 'ir.actions.act_window', 'name': _('Pack Configurations'), 'res_model': 'spx.pack.rule', 'view_mode': 'list,form', 'domain': ['|', ('pack_product_id', 'in', self.product_variant_ids.ids), ('unit_product_id', 'in', self.product_variant_ids.ids)]}

    def action_spx_create_pack(self):
        self.ensure_one()
        if self.product_variant_count != 1:
            raise UserError(_('Select a product with a single variant.'))
        return {'type': 'ir.actions.act_window', 'name': _('Create Pack Product'), 'res_model': 'spx.pack.setup', 'view_mode': 'form', 'target': 'new', 'context': {'default_unit_product_id': self.product_variant_id.id}}


class StockLot(models.Model):
    _inherit = 'stock.lot'

    spx_pack_source_lot_id = fields.Many2one('stock.lot', 'Source Pack Batch', readonly=True, copy=False, ondelete='restrict', check_company=True)


class MrpProduction(models.Model):
    _inherit = 'mrp.production'

    spx_pack_conversion_id = fields.Many2one('spx.pack.conversion', 'Pack Conversion', readonly=True, copy=False, ondelete='restrict', check_company=True)

    @api.model_create_multi
    def create(self, vals_list):
        if self.env.context.get('_spx_pack_internal') is not _INTERNAL and any(v.get('spx_pack_conversion_id') for v in vals_list):
            raise UserError(_('Create pack stock operations through Pack Conversion.'))
        return super().create(vals_list)

    def write(self, vals):
        if self.env.context.get('_spx_pack_internal') is not _INTERNAL:
            if 'spx_pack_conversion_id' in vals:
                raise UserError(_('The conversion link cannot be changed manually.'))
            protected = {'product_id', 'product_qty', 'qty_producing', 'product_uom_id', 'bom_id', 'location_src_id', 'location_dest_id', 'move_raw_ids', 'move_finished_ids', 'lot_producing_ids', 'company_id', 'state'}
            if protected & vals.keys() and any(mo.spx_pack_conversion_id for mo in self):
                raise UserError(_('Correct this operation through its Pack Conversion reversal.'))
        return super().write(vals)

    def action_cancel(self):
        if any(mo.spx_pack_conversion_id for mo in self):
            raise UserError(_('Use a Pack Conversion reversal to correct this operation.'))
        return super().action_cancel()


class StockMove(models.Model):
    _inherit = 'stock.move'

    def _adjust_procure_method(self, picking_type_code=False):
        conversions = self.filtered(lambda m: m.raw_material_production_id.spx_pack_conversion_id)
        conversions.procure_method = 'make_to_stock'
        return super(StockMove, self - conversions)._adjust_procure_method(picking_type_code)
