import math

from odoo import api, fields, models, _
from odoo.exceptions import UserError
from odoo.tools import SQL, float_compare


# Identity sentinel: an RPC-supplied context cannot impersonate an internal write.
_INTERNAL = object()
_DATES = ('expiration_date', 'use_date', 'removal_date', 'alert_date')


class PackConversion(models.Model):
    _name = 'spx.pack.conversion'
    _description = 'Pack Conversion'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _check_company_auto = True
    _order = 'id desc'

    name = fields.Char(default='New', readonly=True, copy=False)
    state = fields.Selection([('draft', 'Draft'), ('done', 'Done'), ('cancel', 'Cancelled')], default='draft', readonly=True, tracking=True, copy=False)
    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company)
    rule_id = fields.Many2one('spx.pack.rule', 'Pack Configuration', required=True, check_company=True, ondelete='restrict', tracking=True)
    direction = fields.Selection([('unpack', 'Open Packs'), ('repack', 'Repack Items')], default='unpack', required=True, tracking=True)
    pack_qty = fields.Integer('Number of Packs', default=1, required=True, tracking=True)
    source_product_id = fields.Many2one('product.product', compute='_compute_quantities', store=True)
    target_product_id = fields.Many2one('product.product', compute='_compute_quantities', store=True)
    source_qty = fields.Float('Quantity to Consume', compute='_compute_quantities', store=True, digits='Product Unit')
    target_qty = fields.Float('Quantity to Produce', compute='_compute_quantities', store=True, digits='Product Unit')
    source_uom_id = fields.Many2one('uom.uom', 'Source Unit', related='source_product_id.uom_id')
    target_uom_id = fields.Many2one('uom.uom', 'Produced Unit', related='target_product_id.uom_id')
    tracking = fields.Selection(related='source_product_id.tracking')
    location_id = fields.Many2one('stock.location', 'Source Location', required=True, check_company=True, domain="[('usage', '=', 'internal'), ('company_id', '=', company_id)]")
    location_dest_id = fields.Many2one('stock.location', 'Destination Location', required=True, check_company=True, domain="[('usage', '=', 'internal'), ('company_id', '=', company_id)]")
    source_lot_id = fields.Many2one('stock.lot', 'Source Batch / Lot', check_company=True, ondelete='restrict')
    target_lot_id = fields.Many2one('stock.lot', 'Produced Batch / Lot', check_company=True, ondelete='restrict', readonly=True, copy=False)
    available_qty = fields.Float('Available to Convert', compute='_compute_available', digits='Product Unit')
    production_id = fields.Many2one('mrp.production', 'Stock Operation', readonly=True, check_company=True, ondelete='restrict', copy=False)
    completed_by = fields.Many2one('res.users', readonly=True, copy=False)
    completed_at = fields.Datetime(readonly=True, copy=False)
    reverse_of_id = fields.Many2one('spx.pack.conversion', 'Reverses', readonly=True, copy=False, check_company=True, ondelete='restrict')
    reversal_ids = fields.One2many('spx.pack.conversion', 'reverse_of_id', readonly=True)
    reversal_count = fields.Integer(compute='_compute_reversal_count')
    reason = fields.Text('Notes / Reason', tracking=True)
    currency_id = fields.Many2one(related='company_id.currency_id')
    transferred_value = fields.Monetary('Inventory Value Transferred', readonly=True, copy=False)

    _positive_packs = models.Constraint('CHECK(pack_qty > 0)', 'Enter a positive whole number of packs.')
    _one_reversal = models.Constraint('UNIQUE(reverse_of_id)', 'A reversal already exists for this conversion.')

    @api.depends('rule_id', 'rule_id.units_per_pack', 'rule_id.pack_product_id', 'rule_id.unit_product_id', 'direction', 'pack_qty')
    def _compute_quantities(self):
        for rec in self:
            unpack = rec.direction == 'unpack'
            rec.source_product_id = rec.rule_id.pack_product_id if unpack else rec.rule_id.unit_product_id
            rec.target_product_id = rec.rule_id.unit_product_id if unpack else rec.rule_id.pack_product_id
            contents = rec.pack_qty * rec.rule_id.units_per_pack
            rec.source_qty = rec.pack_qty if unpack else contents
            rec.target_qty = contents if unpack else rec.pack_qty

    @api.depends('reversal_ids')
    def _compute_reversal_count(self):
        for rec in self:
            rec.reversal_count = len(rec.reversal_ids)

    @api.depends('source_product_id', 'location_id', 'source_lot_id', 'company_id')
    def _compute_available(self):
        for rec in self:
            rec.available_qty = 0
            if rec.source_product_id and rec.location_id:
                rec.available_qty = rec.env['stock.quant'].with_company(rec.company_id)._get_available_quantity(
                    rec.source_product_id, rec.location_id, lot_id=rec.source_lot_id, strict=True)

    @api.onchange('company_id')
    def _onchange_company(self):
        warehouse = self.env['stock.warehouse'].search([('company_id', '=', self.company_id.id)], limit=1)
        self.location_id = warehouse.lot_stock_id
        self.location_dest_id = warehouse.lot_stock_id
        self.source_lot_id = False

    @api.onchange('rule_id', 'direction')
    def _onchange_rule(self):
        self.source_lot_id = False
        if self.rule_id:
            self.company_id = self.rule_id.company_id
            if not self.location_id or self.location_id.company_id != self.company_id:
                self._onchange_company()

    @api.model_create_multi
    def create(self, vals_list):
        internal = self.env.context.get('_spx_pack_internal') is _INTERNAL
        protected = {'name', 'state', 'production_id', 'target_lot_id', 'completed_by', 'completed_at', 'reverse_of_id', 'transferred_value', 'source_product_id', 'target_product_id', 'source_qty', 'target_qty'}
        if not internal and any('default_' + field in self.env.context for field in protected):
            raise UserError(_('Operation results cannot be supplied as defaults.'))
        for vals in vals_list:
            if not internal and protected & vals.keys():
                raise UserError(_('Operation results can only be set by confirming a conversion.'))
            qty = vals.get('pack_qty', self.env.context.get('default_pack_qty', 1))
            if not isinstance(qty, (int, float)) or not math.isfinite(qty) or qty <= 0 or qty != int(qty):
                raise UserError(_('Enter a positive whole number of packs.'))
            company = self.env['res.company'].browse(vals.get('company_id', self.env.context.get('default_company_id', self.env.company.id)))
            vals['name'] = self.env['ir.sequence'].with_company(company).next_by_code('spx.pack.conversion') or 'New'
            if not vals.get('location_id') or not vals.get('location_dest_id'):
                warehouse = self.env['stock.warehouse'].search([('company_id', '=', company.id)], limit=1)
                vals.setdefault('location_id', warehouse.lot_stock_id.id)
                vals.setdefault('location_dest_id', warehouse.lot_stock_id.id)
        return super().create(vals_list)

    def write(self, vals):
        if self.env.context.get('_spx_pack_internal') is not _INTERNAL:
            self.check_access('write')
            self._lock_records()
            protected = {'name', 'state', 'production_id', 'target_lot_id', 'completed_by', 'completed_at', 'reverse_of_id', 'transferred_value', 'source_product_id', 'target_product_id', 'source_qty', 'target_qty'}
            if protected & vals.keys():
                raise UserError(_('Use the conversion actions to change its status or results.'))
            business = {'company_id', 'rule_id', 'direction', 'pack_qty', 'location_id', 'location_dest_id', 'source_lot_id', 'reason'}
            if business & vals.keys() and any(rec.state != 'draft' for rec in self):
                raise UserError(_('Completed and cancelled conversions are read-only. Use a reversal to correct completed stock movements.'))
            if business & vals.keys() and any(rec.reverse_of_id for rec in self):
                if set(vals) - {'reason'}:
                    raise UserError(_('A reversal must exactly mirror its original conversion.'))
            if 'pack_qty' in vals:
                qty = vals['pack_qty']
                if not isinstance(qty, (int, float)) or not math.isfinite(qty) or qty <= 0 or qty != int(qty):
                    raise UserError(_('Enter a positive whole number of packs.'))
        return super().write(vals)

    def _lock_records(self):
        if self.ids:
            self.flush_recordset()
            self.env.cr.execute(SQL('SELECT id FROM spx_pack_conversion WHERE id IN %s ORDER BY id FOR UPDATE', tuple(self.ids)))
            self.invalidate_recordset()

    @api.ondelete(at_uninstall=False)
    def _unlink_except_completed(self):
        if any(rec.state == 'done' or rec.production_id for rec in self):
            raise UserError(_('Completed conversions cannot be deleted.'))

    def _validate_conversion(self):
        self.ensure_one()
        self._check_company()
        rule = self.rule_id
        rule._check_configuration()
        if not rule.active or not (self.source_product_id.active and self.target_product_id.active):
            raise UserError(_('The pack configuration and both products must be active.'))
        if self.direction == 'repack' and not rule.allow_repack and not self.reverse_of_id:
            raise UserError(_('Repacking is disabled for this pack configuration.'))
        if self.reverse_of_id:
            if not self.env.user.has_group('spx_pack_conversion.group_pack_manager'):
                raise UserError(_('Only a Pack Conversion manager can confirm a reversal.'))
            if not (self.reason or '').strip():
                raise UserError(_('Enter the reason for reversing this conversion.'))
        for location in self.location_id | self.location_dest_id:
            if location.usage != 'internal' or location.company_id != self.company_id:
                raise UserError(_('Use internal stock locations belonging to this company.'))
        if self.source_product_id.tracking == 'lot':
            if not self.source_lot_id or self.source_lot_id.product_id != self.source_product_id:
                raise UserError(_('Select a source batch belonging to the product being consumed.'))
            if self.source_lot_id.expiration_date and self.source_lot_id.expiration_date <= fields.Datetime.now():
                raise UserError(_('This source batch has expired and cannot be converted.'))
        elif self.source_lot_id:
            raise UserError(_('Remove the batch selection for an untracked product.'))
        for product, qty in ((self.source_product_id, self.source_qty), (self.target_product_id, self.target_qty)):
            if float_compare(product.uom_id.round(qty), qty, precision_digits=8):
                raise UserError(_('The conversion quantity is incompatible with the product unit rounding.'))
        available = self.env['stock.quant']._get_available_quantity(self.source_product_id, self.location_id, lot_id=self.source_lot_id, strict=True)
        if float_compare(available, self.source_qty, precision_rounding=self.source_product_id.uom_id.rounding) < 0:
            raise UserError(_('Insufficient available stock: %(available)s available; %(needed)s needed. Check the exact location, batch and existing reservations. Stock in transport packages must first be unpacked through Inventory.', available=available, needed=self.source_qty))

    def action_confirm(self):
        self.ensure_one()
        self.check_access('write')
        if not self.env.user.has_group('spx_pack_conversion.group_pack_user'):
            raise UserError(_('You need Pack Conversion access to confirm this operation.'))
        # The savepoint also makes the operation atomic if a caller catches UserError.
        with self.env.cr.savepoint():
            self.flush_recordset()
            self.env.cr.execute(SQL('SELECT id FROM spx_pack_conversion WHERE id = %s FOR UPDATE', self.id))
            self.invalidate_recordset()
            if self.state == 'done':
                return self.action_open()
            if self.state != 'draft':
                raise UserError(_('Only a draft conversion can be confirmed.'))
            self.rule_id.flush_recordset()
            self.env.cr.execute(SQL('SELECT id FROM spx_pack_rule WHERE id = %s FOR UPDATE', self.rule_id.id))
            self.rule_id.invalidate_recordset()
            products = self.source_product_id | self.target_product_id
            products.flush_recordset()
            self.env.cr.execute(SQL('SELECT id FROM product_product WHERE id IN %s ORDER BY id FOR UPDATE', tuple(products.ids)))
            operation = self.with_company(self.company_id).with_context(_spx_pack_internal=_INTERNAL)
            operation._compute_quantities()
            operation._validate_conversion()
            operation._execute_conversion()
        return self.action_open()

    def _execute_conversion(self):
        self.ensure_one()
        warehouse = self.location_id.warehouse_id
        picking_type = warehouse.manu_type_id
        if not picking_type or picking_type.company_id != self.company_id:
            picking_type = self.env['stock.picking.type'].search([('code', '=', 'mrp_operation'), ('company_id', '=', self.company_id.id)], limit=1)
        if not picking_type:
            raise UserError(_('Configure a manufacturing operation type for this warehouse.'))
        target_lot = self.env['stock.lot']
        if self.target_product_id.tracking == 'lot':
            vals = {
                'name': '%s/%s' % (self.source_lot_id.name, self.name),
                'product_id': self.target_product_id.id, 'company_id': self.company_id.id,
                'spx_pack_source_lot_id': self.source_lot_id.id,
            }
            vals.update({date: self.source_lot_id[date] for date in _DATES})
            target_lot = self.env['stock.lot'].create(vals)
        mo = self.env['mrp.production'].create({
            'product_id': self.target_product_id.id,
            'product_qty': self.target_qty, 'product_uom_id': self.target_product_id.uom_id.id,
            'bom_id': False, 'company_id': self.company_id.id,
            'picking_type_id': picking_type.id,
            'location_src_id': self.location_id.id, 'location_dest_id': self.location_dest_id.id,
            'origin': self.name, 'spx_pack_conversion_id': self.id,
        })
        if mo.bom_id or mo.move_raw_ids:
            raise UserError(_('An unexpected bill of materials was applied. No stock was changed.'))
        raw_vals = mo._get_move_raw_values(self.source_product_id, self.source_qty, self.source_product_id.uom_id)
        raw_vals['manual_consumption'] = True
        raw = self.env['stock.move'].create(raw_vals)
        mo.action_confirm()
        raw._do_unreserve()
        reserved = raw._update_reserved_quantity(self.source_qty, self.location_id, lot_id=self.source_lot_id, strict=True)
        if float_compare(reserved, self.source_qty, precision_rounding=self.source_product_id.uom_id.rounding) < 0:
            raise UserError(_('The required stock could not be reserved. Refresh and try again.'))
        raw.picked = True
        mo.write({'qty_producing': self.target_qty, 'lot_producing_ids': [fields.Command.set(target_lot.ids)]})
        mo.with_context(skip_redirection=True).button_mark_done()
        if mo.state != 'done':
            raise UserError(_('Odoo requested an additional manufacturing step. Conversion was rolled back; check the operation type and product setup.'))
        consumed = sum(mo.move_raw_ids.mapped('value'))
        produced = sum(mo.move_finished_ids.mapped('value'))
        if not self.company_id.currency_id.is_zero(consumed - produced):
            raise UserError(_('Conversion would change inventory value from %(source).4f to %(target).4f. No stock was changed. For Standard Cost, align the pack and contained-item costs with the pack quantity. AVCO or FIFO carries consumed cost through the native operation.', source=consumed, target=produced))
        # Native expiration computations must never extend the source batch dates.
        if target_lot:
            target_lot.write({date: self.source_lot_id[date] for date in _DATES})
        self.write({
            'state': 'done', 'production_id': mo.id, 'target_lot_id': target_lot.id,
            'completed_by': self.env.uid, 'completed_at': fields.Datetime.now(),
            'transferred_value': consumed,
        })
        self.message_post(body=_('Converted %(source_qty)s × %(source)s into %(target_qty)s × %(target)s. Stock operation: %(operation)s.', source_qty=self.source_qty, source=self.source_product_id.display_name, target_qty=self.target_qty, target=self.target_product_id.display_name, operation=mo.name))

    def action_cancel(self):
        self.check_access('write')
        self._lock_records()
        if any(rec.state != 'draft' for rec in self):
            raise UserError(_('Only draft conversions can be cancelled.'))
        self.with_context(_spx_pack_internal=_INTERNAL).write({'state': 'cancel'})

    def action_reverse(self):
        self.ensure_one()
        self.check_access('write')
        self._lock_records()
        if not self.env.user.has_group('spx_pack_conversion.group_pack_manager'):
            raise UserError(_('Only a Pack Conversion manager can create a reversal.'))
        if self.state != 'done' or self.reverse_of_id:
            raise UserError(_('Only an original completed conversion can be reversed.'))
        if self.reversal_ids:
            return self.reversal_ids[:1].action_open()
        rec = self.with_context(_spx_pack_internal=_INTERNAL).create({
            'rule_id': self.rule_id.id, 'company_id': self.company_id.id,
            'direction': 'repack' if self.direction == 'unpack' else 'unpack',
            'pack_qty': self.pack_qty, 'location_id': self.location_dest_id.id,
            'location_dest_id': self.location_id.id, 'source_lot_id': self.target_lot_id.id,
            'reverse_of_id': self.id,
        })
        return rec.action_open()

    def action_open(self):
        self.ensure_one()
        return {'type': 'ir.actions.act_window', 'res_model': self._name, 'view_mode': 'form', 'res_id': self.id}

    def action_stock_moves(self):
        self.ensure_one()
        moves = self.production_id.move_raw_ids | self.production_id.move_finished_ids
        return {'type': 'ir.actions.act_window', 'name': _('Stock Movements'), 'res_model': 'stock.move', 'view_mode': 'list,form', 'domain': [('id', 'in', moves.ids)]}
