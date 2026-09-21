from datetime import timedelta

from odoo import Command, fields
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import Form, TransactionCase, tagged, new_test_user


@tagged('post_install', '-at_install')
class TestPackConversion(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.location = cls.env['stock.warehouse'].search([('company_id', '=', cls.company.id)], limit=1).lot_stock_id
        cls.category = cls.env['product.category'].create({'name': 'Pack test standard', 'property_cost_method': 'standard'})
        cls.single = cls.env['product.product'].create({'name': 'Test Water Single', 'is_storable': True, 'type': 'consu', 'list_price': 5, 'standard_price': 0.5, 'categ_id': cls.category.id})
        cls.pack = cls.env['product.product'].create({'name': 'Test Water Case 24', 'is_storable': True, 'type': 'consu', 'list_price': 25, 'standard_price': 12, 'categ_id': cls.category.id})
        cls.rule = cls.env['spx.pack.rule'].create({'name': 'Water 24', 'pack_product_id': cls.pack.id, 'unit_product_id': cls.single.id, 'units_per_pack': 24})
        cls.operator = new_test_user(cls.env, login='pack_operator', groups='spx_pack_conversion.group_pack_user')

    def opening(self, product, qty, lot=None):
        quant = self.env['stock.quant'].with_context(inventory_mode=True).create({
            'product_id': product.id, 'location_id': self.location.id,
            'lot_id': lot.id if lot else False, 'inventory_quantity': qty,
        })
        quant.action_apply_inventory()
        return quant

    def conversion(self, **extra):
        vals = {'rule_id': self.rule.id, 'pack_qty': 2, 'location_id': self.location.id, 'location_dest_id': self.location.id}
        vals.update(extra)
        return self.env['spx.pack.conversion'].create(vals)

    def qty(self, product, lot=None):
        return self.env['stock.quant']._get_available_quantity(product, self.location, lot_id=lot, strict=True)

    def test_opening_stock_no_purchase_order(self):
        self.opening(self.pack, 10)
        rec = self.conversion()
        rec.action_confirm()
        self.assertEqual(rec.state, 'done')
        self.assertEqual((self.qty(self.pack), self.qty(self.single)), (8, 48))
        self.assertEqual((self.pack.lst_price, self.single.lst_price), (25, 5))
        self.assertEqual(rec.transferred_value, 24)
        self.assertFalse(rec.production_id.bom_id)
        self.assertEqual(rec.production_id.state, 'done')
        self.assertTrue(rec.production_id.move_finished_ids.move_line_ids.consume_line_ids)

    def test_double_confirmation_is_idempotent(self):
        self.opening(self.pack, 3)
        rec = self.conversion()
        rec.action_confirm()
        mo = rec.production_id
        rec.action_confirm()
        self.assertEqual(rec.production_id, mo)
        self.assertEqual((self.qty(self.pack), self.qty(self.single)), (1, 48))

    def test_insufficient_stock_is_atomic(self):
        self.opening(self.pack, 1)
        rec = self.conversion()
        with self.assertRaises(UserError):
            rec.action_confirm()
        self.assertEqual(rec.state, 'draft')
        self.assertFalse(rec.production_id)
        self.assertEqual((self.qty(self.pack), self.qty(self.single)), (1, 0))

    def test_existing_reservations_are_respected(self):
        self.opening(self.pack, 3)
        move = self.env['stock.move'].create({'product_id': self.pack.id, 'product_uom_qty': 2, 'product_uom': self.pack.uom_id.id, 'location_id': self.location.id, 'location_dest_id': self.env.ref('stock.stock_location_customers').id})
        move._action_confirm()
        move._action_assign()
        with self.assertRaises(UserError):
            self.conversion().action_confirm()
        self.assertEqual(move.quantity, 2)
        self.assertEqual(self.qty(self.pack), 1)

    def test_standard_cost_mismatch_rolls_back_stock_and_operation(self):
        self.opening(self.pack, 2)
        self.single.standard_price = 1
        rec = self.conversion()
        count = self.env['mrp.production'].search_count([])
        with self.assertRaises(UserError):
            rec.action_confirm()
        self.assertEqual(self.env['mrp.production'].search_count([]), count)
        self.assertEqual((self.qty(self.pack), self.qty(self.single)), (2, 0))

    def test_average_cost_transfer(self):
        self.category.property_cost_method = 'average'
        self.single.standard_price = 0.1
        self.opening(self.pack, 2)
        rec = self.conversion()
        rec.action_confirm()
        self.assertAlmostEqual(self.single.standard_price, 0.5, places=5)
        self.assertAlmostEqual(sum(rec.production_id.move_raw_ids.mapped('value')), sum(rec.production_id.move_finished_ids.mapped('value')), places=5)

    def test_fifo_cost_transfer(self):
        self.category.property_cost_method = 'fifo'
        self.single.standard_price = 0.1
        self.opening(self.pack, 2)
        rec = self.conversion()
        rec.action_confirm()
        self.assertAlmostEqual(rec.transferred_value, 24, places=5)
        self.assertAlmostEqual(sum(rec.production_id.move_finished_ids.mapped('value')), 24, places=5)

    def test_batch_and_all_expiry_dates_carry_over(self):
        (self.pack | self.single).write({'tracking': 'lot', 'use_expiration_date': True})
        expiry = fields.Datetime.now() + timedelta(days=180)
        dates = {'expiration_date': expiry, 'use_date': expiry - timedelta(days=10), 'removal_date': expiry - timedelta(days=20), 'alert_date': expiry - timedelta(days=30)}
        lot = self.env['stock.lot'].create({'name': 'WATER-LOT', 'product_id': self.pack.id, 'company_id': self.company.id, **dates})
        self.opening(self.pack, 5, lot)
        rec = self.conversion(source_lot_id=lot.id)
        rec.action_confirm()
        self.assertEqual(self.qty(self.pack, lot), 3)
        self.assertEqual(self.qty(self.single, rec.target_lot_id), 48)
        self.assertEqual(rec.target_lot_id.spx_pack_source_lot_id, lot)
        for name in dates:
            self.assertEqual(rec.target_lot_id[name], lot[name])

    def test_expired_and_wrong_batches_are_blocked(self):
        (self.pack | self.single).write({'tracking': 'lot', 'use_expiration_date': True})
        lot = self.env['stock.lot'].create({'name': 'EXPIRED', 'product_id': self.pack.id, 'company_id': self.company.id, 'expiration_date': fields.Datetime.now() - timedelta(days=1)})
        self.opening(self.pack, 5, lot)
        with self.assertRaises(UserError):
            self.conversion(source_lot_id=lot.id).action_confirm()
        with self.assertRaises(UserError):
            self.conversion().action_confirm()

    def test_repack_permission_and_stock(self):
        self.opening(self.single, 48)
        rec = self.conversion(direction='repack')
        with self.assertRaises(UserError):
            rec.action_confirm()
        self.rule.allow_repack = True
        rec.action_confirm()
        self.assertEqual((self.qty(self.pack), self.qty(self.single)), (2, 0))

    def test_reversal_keeps_original_and_restores_quantities(self):
        self.opening(self.pack, 5)
        rec = self.conversion()
        rec.action_confirm()
        action = rec.action_reverse()
        reversal = self.env['spx.pack.conversion'].browse(action['res_id'])
        with self.assertRaises(UserError):
            reversal.action_confirm()
        reversal.reason = 'Opened wrong product; physically restored.'
        reversal.action_confirm()
        self.assertEqual((self.qty(self.pack), self.qty(self.single)), (5, 0))
        self.assertEqual(rec.state, 'done')
        self.assertEqual(reversal.reverse_of_id, rec)
        self.assertEqual(rec.action_reverse()['res_id'], reversal.id)

    def test_operator_can_convert_but_not_configure_or_reverse(self):
        self.opening(self.pack, 4)
        rec = self.conversion().with_user(self.operator)
        rec.action_confirm()
        self.assertEqual(rec.completed_by, self.operator)
        with self.assertRaises(AccessError):
            self.rule.with_user(self.operator).write({'units_per_pack': 12})
        with self.assertRaises(UserError):
            rec.action_reverse()

    def test_done_record_cannot_be_forged_or_edited(self):
        with self.assertRaises(UserError):
            self.conversion(state='done')
        rec = self.conversion()
        with self.assertRaises(UserError):
            rec.write({'state': 'done'})
        self.opening(self.pack, 3)
        rec.action_confirm()
        with self.assertRaises(UserError):
            rec.write({'pack_qty': 1})
        with self.assertRaises(UserError):
            rec.unlink()
        with self.assertRaises(UserError):
            rec.production_id.write({'qty_producing': 1})

    def test_fractional_and_zero_packs_rejected(self):
        for qty in (0, -1, 1.5):
            with self.assertRaises(UserError):
                self.conversion(pack_qty=qty)

    def test_context_cannot_forge_completed_results(self):
        with self.assertRaises(UserError):
            self.env['spx.pack.conversion'].with_context(default_state='done').create({'rule_id': self.rule.id})

    def test_conversion_form_defaults_and_preview(self):
        with Form(self.env['spx.pack.conversion']) as form:
            form.rule_id = self.rule
            form.pack_qty = 3
        rec = form.record
        self.assertEqual(rec.source_qty, 3)
        self.assertEqual(rec.target_qty, 72)
        self.assertEqual(rec.location_id, self.location)

    def test_existing_manufacturing_bom_is_not_used(self):
        self.env['mrp.bom'].create({'product_tmpl_id': self.single.product_tmpl_id.id, 'product_qty': 1, 'type': 'normal', 'bom_line_ids': [Command.create({'product_id': self.pack.id, 'product_qty': 3})]})
        self.opening(self.pack, 2)
        rec = self.conversion()
        rec.action_confirm()
        self.assertFalse(rec.production_id.bom_id)
        self.assertEqual((self.qty(self.pack), self.qty(self.single)), (0, 48))

    def test_kit_products_are_not_silently_exploded(self):
        self.env['mrp.bom'].create({'product_tmpl_id': self.pack.product_tmpl_id.id, 'product_qty': 1, 'type': 'phantom', 'bom_line_ids': [Command.create({'product_id': self.single.id, 'product_qty': 24})]})
        with self.assertRaises(ValidationError):
            self.conversion().action_confirm()
        self.assertEqual(self.qty(self.pack), 0)

    def test_setup_creates_independent_prices_without_stock(self):
        wiz = self.env['spx.pack.setup'].create({'unit_product_id': self.single.id, 'name': 'Water Six Pack', 'units_per_pack': 6, 'selling_price': 15, 'cost': 3, 'barcode': 'TEST-PACK-6'})
        action = wiz.action_create_pack()
        rule = self.env['spx.pack.rule'].browse(action['res_id'])
        self.assertEqual(rule.pack_product_id.lst_price, 15)
        self.assertEqual(rule.pack_product_id.barcode, 'TEST-PACK-6')
        self.assertEqual(rule.pack_product_id.qty_available, 0)
        rule.pack_price = 17
        self.assertEqual(rule.pack_product_id.lst_price, 17)
        self.assertEqual(self.single.lst_price, 5)

    def test_nested_packs(self):
        box = self.env['product.product'].create({'name': 'Water Carton', 'type': 'consu', 'is_storable': True, 'standard_price': 120, 'categ_id': self.category.id})
        rule = self.env['spx.pack.rule'].create({'name': 'Carton of 10 cases', 'pack_product_id': box.id, 'unit_product_id': self.pack.id, 'units_per_pack': 10})
        self.opening(box, 1)
        self.conversion(rule_id=rule.id, pack_qty=1).action_confirm()
        self.conversion(pack_qty=1).action_confirm()
        self.assertEqual((self.qty(box), self.qty(self.pack), self.qty(self.single)), (0, 9, 24))

    def test_cycles_rejected(self):
        with self.assertRaises(ValidationError), self.env.cr.savepoint():
            self.env['spx.pack.rule'].create({'name': 'Bad cycle', 'pack_product_id': self.single.id, 'unit_product_id': self.pack.id, 'units_per_pack': 1})

    def test_company_mismatch_rejected(self):
        other = self.env['res.company'].create({'name': 'Other Pack Test Company'})
        other_location = self.env['stock.location'].create({'name': 'Other Stock', 'usage': 'internal', 'company_id': other.id})
        with self.assertRaises(UserError), self.env.cr.savepoint():
            self.conversion(location_id=other_location.id)

    def test_po_receipt_can_supply_conversion(self):
        if 'purchase.order' not in self.env:
            self.skipTest('Optional purchase_stock module not installed')
        vendor = self.env['res.partner'].create({'name': 'Pack Test Supplier'})
        order = self.env['purchase.order'].create({'partner_id': vendor.id, 'order_line': [Command.create({'product_id': self.pack.id, 'product_qty': 10, 'price_unit': 12})]})
        order.button_confirm()
        picking = order.picking_ids
        picking.move_ids.write({'quantity': 10, 'picked': True})
        picking.button_validate()
        rec = self.conversion()
        rec.action_confirm()
        self.assertEqual((self.qty(self.pack), self.qty(self.single)), (8, 48))
