"""Generate deterministic static storefronts from the fictional product catalog."""

import argparse
from collections import Counter
import hashlib
from html import escape
import json
from pathlib import Path
import re
from string import Template
from typing import TypedDict
from urllib.parse import urlsplit


ROOT = Path(__file__).resolve().parents[1]
MERCHANTS = {
    "warehouse-mart": "Warehouse Mart",
    "everyday-market": "Everyday Market",
    "fresh-basket": "Fresh Basket",
}
PRODUCT_COUNTS = {"warehouse-mart": 20, "everyday-market": 15, "fresh-basket": 15}


class Merchant(TypedDict):
    id: str
    name: str
    address: str
    layout: str


class Product(TypedDict):
    merchantId: str
    itemCode: str
    upc: str | None
    name: str
    receiptName: str
    description: str
    category: str
    packSize: str
    currentPrice: str


class Catalog(TypedDict):
    schemaVersion: int
    synthetic: bool
    currency: str
    notice: str
    merchants: list[Merchant]
    products: list[Product]


def load_catalog(path: Path) -> Catalog:
    catalog = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(catalog, dict) or (
        catalog.get("schemaVersion") != 1
        or catalog.get("synthetic") is not True
        or catalog.get("currency") != "USD"
    ):
        raise ValueError("Expected synthetic schemaVersion 1 catalog in USD.")
    merchants = catalog.get("merchants")
    products = catalog.get("products")
    if not isinstance(merchants, list) or len(merchants) != 3:
        raise ValueError("Expected exactly three merchants.")
    if any(not isinstance(m, dict) for m in merchants):
        raise ValueError("Merchant entries must be objects.")
    if Counter((m.get("id"), m.get("name")) for m in merchants) != Counter(MERCHANTS.items()):
        raise ValueError("Merchant identities must match the three fictional storefronts.")
    if not isinstance(products, list) or len(products) != sum(PRODUCT_COUNTS.values()):
        raise ValueError("Expected exactly 50 fictional products.")
    seen: set[tuple[str, str]] = set()
    counts: Counter[str] = Counter()
    for product in products:
        if not isinstance(product, dict):
            raise ValueError("Product entries must be objects.")
        for key in ("merchantId", "itemCode", "name", "receiptName", "description",
                    "category", "packSize", "currentPrice"):
            if not isinstance(product.get(key), str) or not product[key].strip():
                raise ValueError(f"Product {key} must be a nonempty string.")
        merchant_id, code = product["merchantId"], product["itemCode"]
        if merchant_id not in MERCHANTS or not re.fullmatch(r"[0-9]{6}", code):
            raise ValueError("Product requires an allowed merchant and six-digit string code.")
        if (merchant_id, code) in seen:
            raise ValueError("Duplicate merchant/item code.")
        seen.add((merchant_id, code))
        counts[merchant_id] += 1
        if not re.fullmatch(r"(0|[1-9][0-9]*)\.[0-9]{2}", product["currentPrice"]):
            raise ValueError("Catalog prices must be nonnegative decimal strings.")
        if "upc" not in product:
            raise ValueError("Product upc must be explicit, including null when absent.")
        upc = product["upc"]
        if upc is not None:
            if not isinstance(upc, str) or not re.fullmatch(r"[0-9]{12}", upc):
                raise ValueError("Synthetic UPC must be a 12-digit string or null.")
            if (sum(int(n) * (3 if i % 2 == 0 else 1) for i, n in enumerate(upc))) % 10:
                raise ValueError("Synthetic UPC checksum is invalid.")
    if counts != Counter(PRODUCT_COUNTS):
        raise ValueError("Expected 20 Warehouse Mart products and 15 per other merchant.")
    return catalog


def load_photos(catalog: Catalog) -> dict[str, dict[str, str]]:
    photos = json.loads((ROOT / "data" / "photo-credits.json").read_text(encoding="utf-8"))
    expected = {f'{p["merchantId"]}/{p["itemCode"]}' for p in catalog["products"]}
    if set(photos) != expected:
        raise ValueError("Photo manifest must cover exactly the catalog's merchant/product pairs.")
    for photo in photos.values():
        if photo["licenseUrl"].startswith("http://creativecommons.org/"):
            photo["licenseUrl"] = photo["licenseUrl"].replace("http://", "https://", 1)
        if not re.fullmatch(r"[0-9a-f]{20}\.(jpg|png|webp)", photo["file"]):
            raise ValueError("Invalid photo asset filename.")
        content = (ROOT / "data" / "photos" / photo["file"]).read_bytes()
        if hashlib.sha256(content).hexdigest() != photo["sha256"]:
            raise ValueError(f'Photo checksum mismatch: {photo["file"]}')
        if not photo["source"].startswith("https://commons.wikimedia.org/wiki/File:"):
            raise ValueError("Photo source must identify a Wikimedia Commons file.")
        if not photo["author"] or not photo["license"] or not photo["licenseUrl"].startswith("https://"):
            raise ValueError("Photo attribution and license link are required.")
        if photo["license"] not in ("Public domain", "CC0"):
            raise ValueError("Only public-domain or CC0 product photos are allowed.")
        if urlsplit(photo["licenseUrl"]).hostname not in ("creativecommons.org", "commons.wikimedia.org"):
            raise ValueError("Unexpected photo license host.")
    return photos


def product_photo(product: Product, photo: dict[str, str], prefix: str) -> str:
    return (
        f'<figure class="product-photo"><img src="{prefix}assets/photos/{photo["file"]}" '
        f'alt="{escape(photo["topic"])} - representative photo for {escape(product["name"])}" '
        'width="640" height="420" loading="lazy" decoding="async">'
        '<figcaption>Representative product photo; not an exact brand or pack match.'
        '</figcaption></figure>'
    )


def render_pages(catalog: Catalog) -> dict[str, str]:
    photos = load_photos(catalog)
    template = Template((ROOT / "scripts" / "page.html").read_text(encoding="utf-8"))
    pages: dict[str, str] = {".nojekyll": ""}

    def page(title: str, description: str, home: str, body: str,
             structured: dict[str, object] | None = None) -> str:
        data = ""
        if structured is not None:
            # JSON script text must not be able to terminate its enclosing HTML element.
            encoded = json.dumps(structured, indent=2, ensure_ascii=True)
            encoded = encoded.replace("&", "\\u0026").replace("<", "\\u003c").replace(">", "\\u003e")
            data = f'<script type="application/json" id="product-data">{encoded}</script>'
        return template.substitute(
            title=escape(title), description=escape(description), home=home,
            body=body, structured=data,
        )

    merchant_cards = "".join(
        f'<article class="card"><span class="tag">{PRODUCT_COUNTS[merchant]} products</span>'
        f'<h2><a href="{merchant}/">{escape(name)}</a></h2>'
        f'<p>A fictional storefront with its own merchant-scoped item codes.</p>'
        f'<a href="{merchant}/">Browse {escape(name)}</a></article>'
        for merchant, name in MERCHANTS.items()
    )
    pages["index.html"] = page(
        "Fictional merchant storefronts | Receipt Demo",
        "Three fictional merchant catalogs for receipt enrichment demos.", "./",
        '<p class="eyebrow">The enrichment learning lab</p>'
        '<h1>Small receipts.<br>Richer product stories.</h1>'
        '<p class="intro">Explore three independent demo storefronts. '
        'Every product has a stable page that an enrichment tool can fetch as evidence.</p>'
        '<div class="stats"><span><strong>3</strong> merchants</span>'
        f'<span><strong>{len(catalog["products"])}</strong> products</span>'
        '<span><strong>0</strong> real transactions</span></div>'
        f'<section class="grid" aria-label="Merchant storefronts">{merchant_cards}</section>',
    )
    credits = "".join(
        f'<article class="card"><h2>{escape(MERCHANTS[p["merchantId"]])} / {escape(p["name"])}</h2>'
        f'<p class="code">Item {p["itemCode"]}</p>'
        f'<p><a href="{escape(photos[p["merchantId"] + "/" + p["itemCode"]]["source"])}">'
        f'{escape(photos[p["merchantId"] + "/" + p["itemCode"]]["topic"])}</a>'
        f' by {escape(photos[p["merchantId"] + "/" + p["itemCode"]]["author"])} / '
        f'<a href="{escape(photos[p["merchantId"] + "/" + p["itemCode"]]["licenseUrl"])}">'
        f'{escape(photos[p["merchantId"] + "/" + p["itemCode"]]["license"])}</a>.</p>'
        '<p>Resized by the source provider; cropped for display. '
        'No endorsement by the photographer is implied.</p></article>'
        for p in catalog["products"]
    )
    pages["photo-credits.html"] = page(
        "Photo credits | Receipt Demo", "Creators, sources and licenses for product photographs.", "./",
        '<nav aria-label="Breadcrumb"><a href="./">All merchants</a></nav>'
        '<h1>Photo credits</h1><p class="intro">Representative photographs are recorded '
        'by their sources as public domain or CC0 public-domain dedications. '
        'Source and creator records are retained for provenance. '
        'This is not a guarantee about trademark, privacy or other non-copyright rights.</p>'
        f'<section class="grid" aria-label="Photo attribution">{credits}</section>',
    )
    for merchant_id, merchant_name in MERCHANTS.items():
        products = sorted(
            (p for p in catalog["products"] if p["merchantId"] == merchant_id),
            key=lambda p: p["itemCode"],
        )
        cards = "".join(
            f'<article class="card">{product_photo(p, photos[merchant_id + "/" + p["itemCode"]], "../")}'
            f'<span class="tag">{escape(p["category"])}</span>'
            f'<h2><a href="products/{p["itemCode"]}.html">{escape(p["name"])}</a></h2>'
            f'<p>{escape(p["description"])}</p>'
            f'<p class="code">Item {p["itemCode"]}</p>'
            f'<p>{escape(p["packSize"])} / <span class="price">USD {p["currentPrice"]}</span></p>'
            f'<a href="products/{p["itemCode"]}.html">View product evidence</a></article>'
            for p in products
        )
        pages[f"{merchant_id}/index.html"] = page(
            f"{merchant_name} | Fictional storefront",
            f"Browse {len(products)} fictional {merchant_name} products.", "../",
            '<nav aria-label="Breadcrumb"><a href="../">All merchants</a></nav>'
            f'<p class="eyebrow">Independent demo storefront / {merchant_id}</p>'
            f'<h1>{escape(merchant_name)}</h1>'
            '<p class="intro">Everyday essentials, clearly described. '
            'Use the exact item code to find the product behind a receipt abbreviation.</p>'
            f'<div class="stats"><span>{len(products)} products</span><span>USD catalog prices</span>'
            '<span>Static product evidence</span></div>'
            f'<section class="grid" aria-label="Products">{cards}</section>',
        )
        for product in products:
            code = product["itemCode"]
            upc = product["upc"]
            fields = (
                ("Merchant", merchant_name), ("Merchant ID", merchant_id),
                ("Item code", code), ("Receipt abbreviation", product["receiptName"]),
                ("Category", product["category"]), ("Pack size", product["packSize"]),
                ("Synthetic UPC", upc if upc is not None else "Not provided"),
                ("Illustrative catalog price", f'USD {product["currentPrice"]}'),
            )
            details = "".join(
                f'<dt>{escape(label)}</dt><dd>{escape(value)}</dd>'
                for label, value in fields
            )
            payload: dict[str, object] = {
                "schemaVersion": 1, "synthetic": True,
                "merchantId": merchant_id, "merchantName": merchant_name,
                "itemCode": code, "upc": upc, "name": product["name"],
                "receiptName": product["receiptName"],
                "description": product["description"], "category": product["category"],
                "packSize": product["packSize"],
                "catalogPrice": product["currentPrice"], "currency": "USD",
            }
            pages[f"{merchant_id}/products/{code}.html"] = page(
                f'{product["name"]} | {merchant_name}',
                product["description"], "../../",
                '<nav aria-label="Breadcrumb"><a href="../../">All merchants</a> / '
                f'<a href="../">{escape(merchant_name)}</a> / <span>{code}</span></nav>'
                f'<article class="card detail"><p class="eyebrow">{escape(merchant_name)}</p>'
                f'<span class="tag">{escape(product["category"])}</span>'
                f'<h1>{escape(product["name"])}</h1>'
                f'{product_photo(product, photos[merchant_id + "/" + code], "../../")}'
                f'<p class="intro">{escape(product["description"])}</p>'
                f'<dl>{details}</dl><p class="muted">'
                'This catalog price is not evidence of the price paid on a receipt. '
                'A missing UPC is intentionally unknown.</p></article>',
                payload,
            )
    return pages


def build(catalog_path: Path, output: Path, *, check: bool = False) -> int:
    catalog = load_catalog(catalog_path)
    pages = render_pages(catalog)
    photos = load_photos(catalog)
    files = {name: content.encode("utf-8") for name, content in pages.items()}
    for photo in photos.values():
        files[f'assets/photos/{photo["file"]}'] = (ROOT / "data" / "photos" / photo["file"]).read_bytes()
    files["photo-credits.json"] = (ROOT / "data" / "photo-credits.json").read_bytes()
    existing = {p.relative_to(output).as_posix() for p in output.rglob("*") if p.is_file()}
    extra = existing - files.keys()
    if extra:
        raise ValueError(f"Unexpected files in output; inspect manually: {sorted(extra)}")
    if check:
        if existing != files.keys() or any(
            (output / name).read_bytes() != content
            for name, content in files.items()
        ):
            raise ValueError("Generated site is missing or stale; run scripts\\build_sites.py.")
    else:
        for name, content in files.items():
            target = output / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
    return len(pages) - 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, default=ROOT / "data" / "catalogs.json")
    parser.add_argument("--output", type=Path, default=ROOT / "docs")
    parser.add_argument("--check", action="store_true", help="Verify outputs without writing.")
    args = parser.parse_args()
    try:
        count = build(args.catalog, args.output, check=args.check)
    except (ValueError, OSError) as error:
        parser.exit(1, f"Site build failed: {error}\n")
    print(f'{"Verified" if args.check else "Generated"} {count} HTML pages (3 merchants, 50 products).')
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
