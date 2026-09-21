# Spxcorp Pack Conversion

Odoo 19 Community · version 19.0.1.0.0 · Spxcorp Limited

Keep sealed cases, boxes, strips and loose items as separate Odoo products. Give each its own selling price, barcode and stock balance. Open packs only when you physically need the contents.

## Installation

1. Extract the ZIP. Copy the single `spx_pack_conversion` folder into your Odoo custom addons directory, or commit that folder to the addons repository used by your host.
2. Restart/rebuild Odoo so Python files are loaded.
3. Enable developer mode, open Apps and run **Update Apps List**.
4. Search for **Spxcorp Pack Conversion**, then install it.
5. Open **Pack Conversion** from the app launcher. It is also available at **Inventory → Operations → Pack Conversions**.

This is a Python server module. Upload it to the server/addons repository; the normal data-import screen does not install it. It is not a SiteGround website package. No external Python or JavaScript dependencies are required.

Odoo will install its standard Manufacturing, inventory valuation and product-expiry dependencies if missing. Purchase and Point of Sale are optional: this module does not require either to convert stock. When those apps are installed, pack products use their ordinary product, receipt and sales flows.

## Start with two existing products

Open **Pack Conversion → Pack Configurations → New**.

Example:

| Field | Value |
|---|---|
| Name | Blue Water 500ml — Case of 24 |
| Pack Product | Blue Water 500ml — Case of 24 |
| Quantity Inside One Pack | 24 |
| Contained Product | Blue Water 500ml — Single |
| Pack Selling Price | 25.00 |
| Contained Item Selling Price | 5.00 |
| Allow Repacking | Off |

Use two separate products, each with **Goods → Track Inventory** enabled. Use one variant per product to keep selling prices independent. Both can use Odoo's normal **Units** inventory unit: one unit of the case product means one whole case. The contained quantity is defined by this configuration.

The price fields edit the native product selling prices. They follow your company currency and Odoo's normal tax/pricelist settings. Set the company currency to TTD for Trinidad-dollar pricing. Supplier purchase prices remain in the native Purchase tab. Selling price and inventory cost are different fields.

One pack product has one breakdown in each company. Different sizes must be different products. For a box containing ten strips of ten tablets, create Box → Strip (10), then Strip → Tablet (10). Convert at the level you physically open; this release does not automatically cascade through several levels in one click.

## Create a new pack from an existing item

Open **Pack Conversion → Create Pack Product**, or open the item and use its **Pack Conversion** tab.

Select the contained item, quantity inside the pack, pack name, selling price, initial cost and optional barcode. This creates a separate product and links it to the item. It creates no stock. The new pack inherits the contained item's category, tracking, expiry settings and matching company taxes. If POS is installed, the new pack is marked Available in POS; enable the contained item separately if needed.

The suggested initial pack cost is the current contained-item cost multiplied by the quantity. Enter the actual cost if different. With Standard Cost, both forms must have consistent costs before conversion; AVCO/FIFO follow the actual consumed value through Odoo's manufacturing valuation.

## Stock with or without a purchase order

**With a PO:** buy the case product, for example quantity 10 at the supplier's price per case. Receive those ten cases normally. Do not add 240 singles to stock as well.

**Without a PO:** use normal opening stock/Physical Inventory to count ten cases, or receive/transfer existing stock through your usual Odoo process. Conversion only requires available stock at the selected location. It does not require a supplier, PO or vendor bill.

If stock already exists entirely as singles, do not add cases on top of it. Count the actual sealed and loose stock and reconcile the opening quantities through your normal inventory adjustment process before going live.

## Convert

1. Select the configuration and click **Convert**.
2. Choose **Open Packs** and enter a whole number of packs.
3. Select the exact source and destination stock locations. They may be the same.
4. If tracked by batch, select the source lot.
5. Check the quantities and click **Confirm Conversion**.

With ten cases in stock, opening two produces eight cases and 48 singles. A later sale of a case removes one case; a sale of a single removes one single. Selecting 24 singles does not automatically select the case price. Existing native pricelist rules still apply if configured, so remove obsolete quantity-discount rules if they conflict with this pricing policy.

The **Available to Convert** field excludes reservations and applies to the exact location and selected batch. This first release consumes company-owned stock outside Odoo transport packages. A transport package is a logistics container, separate from the case product: use native Inventory to unpack that container first. Serial-number-tracked items and consignment stock are not supported in this release.

## Batches and expiration dates

Both products must use the same tracking method: no tracking, or batches/lots. If expiration is enabled, enable it on both forms.

A conversion consumes one selected source batch and creates a separate batch for the resulting product. The produced batch records its source batch and carries its expiration, best-before, removal and alert dates. Odoo's native manufacturing move-line links also connect the consumed and produced stock. Expired source batches are blocked. Run separate conversions for separate source batches; batches are never silently mixed.

The module preserves existing dates; it does not calculate medicine-specific shorter after-opening dates. Any applicable shortened shelf life remains an operational decision recorded through the normal batch process.

## Inventory value

Each conversion creates a native Odoo manufacturing order that consumes the source product and produces the destination product. There are no direct quantity edits or paired inventory adjustments, and no generated reusable bills of materials or automatic manufacturing routes.

- **AVCO/FIFO:** the native manufacturing valuation transfers the consumed stock value to the resulting product.
- **Standard Cost:** product costs must agree with the conversion ratio. For example, a case costing TT$12 and 24 singles costing TT$0.50 each agree. A selling price of TT$5 for the single is independent of its TT$0.50 cost.
- If the posted source and output values differ by more than the company's currency precision, confirmation rolls back the entire operation and explains the mismatch. No partial stock change is retained.

Extra manufacturing costs, work orders and by-products are not added. The module uses Odoo 19's native valuation and accounting behavior; it does not replace your accounting configuration.

## Repacking and correcting mistakes

**Allow Repacking** enables conversion from contained items back into whole packs. Keep it off for products that must not be presented as resealed packs, such as most opened medicine packages.

A manager can create a **full reversal** of a completed conversion, including when normal repacking is disabled. Enter a reason and confirm only when the goods have physically been restored. The required output stock must still be available. A reversal creates a new native stock operation at current native costs and retains the original record; it is not a backdated accounting cancellation. For batch-tracked stock, it creates another linked batch rather than merging into the old batch. Partial reversals are not included in this first version.

If a reversal draft was cancelled by mistake, a manager can delete that unposted reversal and create a new one. Completed conversions cannot be deleted or edited.

## Access and audit

In Settings → Users, assign **Pack Conversion: Operator** or **Manager**. Inventory administrators receive Manager access when the module is installed.

- Operators can create and confirm conversions and read pack configurations.
- Managers can configure products, set prices, create pack products and perform reversals.
- The roles include native Manufacturing user access because the underlying stock operations are manufacturing orders. Managers also receive Odoo product-management access.
- Company record rules apply. The conversion, its products, locations and batches must belong to compatible companies.
- History records the quantities, stock operation, operator, completion time and notes. The stock-movement button opens native Inventory records.

POS checkout, receipts, refunds, product publication and customer pricing remain native. This release does not automatically open a case during checkout or modify offline POS synchronization. Convert loose stock before selling it. Refund the product form that was actually returned; a loose return should not recreate a sealed case.

## Verification and first test

See `docs/VALIDATION.md` for the checks performed for this build and their limits.

On a test database, create the two water products with costs 12.00 and 0.50. Enter ten cases as opening stock, convert two, and confirm that stock is 8 cases and 48 singles. Sell one of each in your normal POS flow, then verify the remaining stock and receipt prices. Repeat with a PO receipt and a batch-tracked product before using real transactions.

The automated integration suite is included under `tests/`. For a normal Odoo 19 test environment:

```bash
odoo-bin -d pack_conversion_test -i spx_pack_conversion,purchase_stock --test-enable --test-tags /spx_pack_conversion --stop-after-init --without-demo
```

Use a dedicated test database; the above command installs modules and executes stock operations inside test transactions.
