# Spxcorp Pack Conversion

**Odoo 19 Community · 19.0.1.0.0 · Spxcorp Limited**

Track sealed cases, boxes, packs and loose items as separate products with independent prices, barcodes and stock. Convert available packs into their contents when physically opened, with or without a purchase order.

## Module

The installable addon is in [`spx_pack_conversion/`](spx_pack_conversion/). Keep this folder intact when adding the repository to your Odoo addons path.

- Configurable pack quantities and nested box → strip → tablet definitions.
- Native purchasing, receiving, inventory, selling and POS product flows.
- Explicit pack conversion, optional repacking and manager-controlled reversals.
- Native manufacturing and stock movements, reservation checks and cost-value checks.
- Batch lineage, expiration-date carryover, permissions and conversion history.

## Install on Cloudpepper / Odoo

1. Connect this repository as a custom addons source and select **`main`**.
2. Rebuild/restart the instance to load the module files.
3. In Odoo, enable developer mode and run **Apps → Update Apps List**.
4. Search for **Spxcorp Pack Conversion** and install it.
5. Open **Pack Conversion → Create Pack Product**, or use **Pack Configurations** to link existing products.

The addon uses the standard Odoo `mrp_account` and `product_expiry` dependencies. Manufacturing and related native dependencies will be installed if missing. A purchase order is not required for conversion. No extra Python or JavaScript packages are needed.

Start on a test database. With ten cases of 24 in opening stock, opening two should leave eight cases and create 48 loose items. Set selling prices independently from inventory costs. Under Standard Cost, pack and contained-item costs must agree with the pack ratio.

## Documentation and validation

- [Full setup and user guide](spx_pack_conversion/README.md)
- [Validation and known limits](spx_pack_conversion/docs/VALIDATION.md)
- [Automated test results](spx_pack_conversion/docs/TEST-RESULTS.txt)
- [License](spx_pack_conversion/LICENSE)

Installation and upgrade were verified in an isolated Odoo 19 environment, with **23 integration tests passing**. The test database used embedded PostgreSQL (PGlite); live Cloudpepper deployment, production PostgreSQL concurrency and browser-driven POS checkout remain to be verified on the target instance.

This first release supports untracked or batch-tracked company-owned stock. Serial numbers, consignment stock, automatic conversion during checkout and partial reversals are outside its scope.
