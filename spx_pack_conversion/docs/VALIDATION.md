# Build validation

Build: 19.0.1.0.0 — 21 September 2026

## Result

Installed successfully and upgraded successfully in an isolated Odoo 19 Community environment. Final automated run: **23 tests, 0 failures, 0 errors**, exit code 0. Python compilation, XML parsing and Odoo's own view validation also passed.

Odoo Community source revision: `026ffed6b9bced6558bbc4a19ce5e2ef6d31ffe1` (19.0 branch). Python 3.12. The test database used PGlite 0.5.8 with its PostgreSQL socket adapter, rather than a separate production PostgreSQL server. Tests executed actual Odoo models, native manufacturing completion, stock moves and valuation; no mocked stock engine was used.

## Scenarios exercised

1. Receive opening stock through an inventory adjustment, then open cases without a PO.
2. Confirm the same conversion twice without duplicating stock movements.
3. Reject insufficient stock with no partial operation.
4. Respect stock already reserved for another movement.
5. Roll back both stock and manufacturing records when Standard Costs disagree.
6. Transfer inventory value using Average Cost.
7. Transfer inventory value using FIFO.
8. Carry batch lineage and all four expiry-related dates to the produced batch.
9. Reject expired batches and missing batch selections.
10. Enforce the repacking option and produce the correct pack quantity.
11. Require a reversal reason, restore quantities and preserve the original record.
12. Allow operator conversions while blocking configuration edits and reversals.
13. Reject forged completion status and edits/deletion of completed conversions.
14. Reject fractional, zero and negative pack quantities.
15. Create a pack product with an independent price and barcode without creating stock.
16. Convert nested carton → case → individual stock.
17. Reject circular pack definitions.
18. Reject an incompatible company/location.
19. Receive ten cases against a native PO and convert two of them.
20. Reject attempts to supply a forged completed state through defaults.
21. Open/save the actual Odoo conversion form, checking default locations and quantity preview.
22. Keep unrelated existing manufacturing bills of materials out of pack conversion.
23. Reject kit products before attempting conversion.

The release test run and a source-file checksum inventory are included beside this file.

## Practical limits

This build has not been installed on the user's Cloudpepper instance. Browser-driven POS checkout, website checkout, production accounting/localization configurations and simultaneous multi-terminal stress tests were not executed. Row locking and native reservations are implemented, but the embedded database test is not a substitute for a production PostgreSQL concurrency test.

Before real stock use, install on a copy/test database and verify the water example, an actual PO receipt, a POS sale of each form, and one representative pharmacy batch using the company's installed accounting and POS extensions. The module does not alter POS JavaScript or the normal checkout flow.

No existing user database, repository, inventory, accounting entries or live site was changed while producing this package.
