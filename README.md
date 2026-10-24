# receipt-demo-merchants
Fictional merchant storefronts for receipt enrichment demos

## What this repository contains

Three independent static storefronts: 20 Warehouse Mart products and 15 each
at Everyday Market and Fresh Basket. The original 45 products come from the
fictional starter catalog; five electronics products extend Warehouse Mart's
storefront only. There are 55 HTML pages: a directory, three
merchant catalogs, 50 product pages, and a photo credits page. No customer information, receipt
documents, application code, secrets, or evaluation ground truth belongs here.

| Merchant | Catalog path | Example product path |
| --- | --- | --- |
| Warehouse Mart | `warehouse-mart/` | `warehouse-mart/products/001001.html` |
| Everyday Market | `everyday-market/` | `everyday-market/products/001001.html` |
| Fresh Basket | `fresh-basket/` | `fresh-basket/products/001001.html` |

The same item code means different products at different merchants. Always
match **merchant ID + exact item code**, preserving leading zeros. Item `009999`
is deliberately absent. Only three products have synthetic UPCs; the other
47 retain null, not an invented value. UPCs are not GS1 assignments and must
not identify real products. Catalog prices are illustrative current prices,
not historical prices paid on receipts.

Warehouse Mart electronics use codes `001016` through `001020`: Wireless
Headphones, Bluetooth Speaker, Laptop, Computer Monitor, and USB-C Charger.
These five products have fictional specifications and prices, nullable UPCs,
and representative photos (not a promise of pictured brand or specifications).
They do not add or modify starter receipt PDFs, purchase seeds, evaluation
ground truth, or the private application's starter catalog.

## Generate and test locally

Python 3.10+; standard library only. Run in PowerShell from this repository:

```powershell
python scripts\build_sites.py
python scripts\build_sites.py --check
python -m unittest discover -s tests -v
python -m http.server 8088 --bind 127.0.0.1 --directory docs
```

Open `http://127.0.0.1:8088/`. Stop the preview with Ctrl+C.
Product content is readable without JavaScript; photographs use local site assets.
JavaScript only selects the light/dark theme. Append `?clawpilotTheme=dark`
or `?clawpilotTheme=light` to preview either theme.

Every catalog card and product detail includes a real, representative
product-type photograph, stored locally with the site. These are not exact
fictional-brand, flavor, organic-certification, frozen-state or pack-size matches.
They are labeled accordingly and are not evidence of product attributes.
No SVG illustrations or remote image dependencies remain.

Photos come from Wikimedia Commons and are recorded by the source as public
domain or CC0 public-domain dedications only. CC BY and CC BY-SA photos are
not accepted by either acquisition or build validation. Captions show only
"Representative product photo; not an exact
brand or pack match." Creator, source, license and cropping details appear on
the [Photo credits page](./docs/photo-credits.html), linked from every page's
footer, voluntarily retained for provenance rather than attribution obligations.
CC0 is a public-domain dedication to the extent legally possible, with a
fallback license; it is not the same as a guarantee of legal clearance.
Source metadata is not legal advice and does not clear trademarks, privacy,
publicity, or other non-copyright rights. No endorsement by pictured brands
is implied. Full source metadata,
license links and SHA-256 hashes are preserved in
[data/photo-credits.json](./data/photo-credits.json) and published as
[docs/photo-credits.json](./docs/photo-credits.json).

Normal builds use checked-in assets, not live image searches. The optional
`python scripts\source_photos.py` acquisition script accesses public Wikimedia
APIs, permits only public-domain or CC0 photos and resumes verified downloads
only after rechecking the source license and restriction metadata.
New or changed photo candidates must be reviewed before publication.

[data/catalogs.json](./data/catalogs.json) is the sole product source.
Edit it, rerun the generator, and review changes to [docs/](./docs/) before
committing. Do not edit generated pages directly. The build rejects unexpected
output files instead of deleting them.

## Manual GitHub Pages publishing (not enabled by this code)

After reviewing and merging the storefront branch into `main`:

1. Open this repository's **Settings > Pages**.
2. Under **Build and deployment**, choose **Deploy from a branch**.
3. Choose **main**, folder **/docs**, then **Save**.
4. Wait for GitHub's Pages deployment to finish and use **Visit site**.

Expected site base: `https://mavya3008.github.io/receipt-demo-merchants/`.
For example, the first product URL will be
`https://mavya3008.github.io/receipt-demo-merchants/warehouse-mart/products/001001.html`.
These are planned URLs until Pages is enabled and the deployment verified.
Relative links support the project prefix; [docs/.nojekyll](./docs/.nojekyll)
keeps the site plain static HTML. No custom Actions workflow, backend, analytics,
third-party fonts, or externally hosted images are required. Attribution links
lead to the original sources. GitHub still uses its own
Pages deployment machinery for branch publishing.

## Product evidence contract for future MCP tools

Fetch the published product HTML page, not the seed catalog file. Every page
has a `<script type="application/json" id="product-data">` block, separate from
the theme script, with:

- `schemaVersion: 1`, `synthetic: true`
- `merchantId`, `merchantName`, `itemCode` (string)
- `name`, `receiptName`, `description`, `category`, `packSize`
- `upc` (12-digit synthetic string or null)
- `catalogPrice` (decimal string), `currency: "USD"`

Validate these identifiers against the requested merchant/code and check that
visible content agrees. Store the fetched source URL, UTC retrieval time,
content SHA-256, and skill version with enrichment. A page does not contain
receipt IDs, purchase dates, quantities, or purchase prices.

Unknown item paths return HTTP 404 under GitHub Pages and a standard local HTTP
server. Tools must treat 404, network failures, invalid data, cross-merchant
redirects and ambiguous matches as explicit outcomes, never fabricate a match.
There is no catalog API, MCP server, agent runner, or database update code in
this repository. Merchant skills and application integration are maintained
separately in the private receipt application.
