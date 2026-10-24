from copy import deepcopy
from html.parser import HTMLParser
import json
from pathlib import Path
from unittest.mock import patch
import tempfile
import unittest
from urllib.parse import unquote, urlsplit

from scripts.build_sites import ROOT, MERCHANTS, PRODUCT_COUNTS, build, load_catalog, load_photos, render_pages


class PageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[str] = []
        self.images: list[dict[str, str | None]] = []
        self.data = ""
        self.in_data = False
        self.text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if tag == "a":
            self.links.append(values["href"] or "")
        if tag == "img":
            self.images.append(values)
        if tag == "script" and values.get("id") == "product-data":
            self.in_data = True

    def handle_endtag(self, tag: str) -> None:
        if tag == "script":
            self.in_data = False

    def handle_data(self, data: str) -> None:
        if self.in_data:
            self.data += data
        else:
            self.text.append(data)


class SiteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.catalog = load_catalog(ROOT / "data" / "catalogs.json")
        cls.pages = render_pages(cls.catalog)

    def test_counts_and_merchant_isolation(self) -> None:
        self.assertEqual(len(self.pages), 56)  # 55 HTML pages and .nojekyll
        for merchant in MERCHANTS:
            paths = [p for p in self.pages if p.startswith(f"{merchant}/products/")]
            self.assertEqual(len(paths), PRODUCT_COUNTS[merchant])
            parser = PageParser()
            parser.feed(self.pages[f"{merchant}/index.html"])
            products = {f"products/{p.rsplit('/', 1)[1]}" for p in paths}
            self.assertEqual({link for link in parser.links if "products/" in link}, products)
            self.assertNotIn(f"{merchant}/products/009999.html", self.pages)

    def test_all_product_evidence_matches_seed(self) -> None:
        for product in self.catalog["products"]:
            with self.subTest(product=product["name"]):
                parser = PageParser()
                parser.feed(self.pages[f'{product["merchantId"]}/products/{product["itemCode"]}.html'])
                data = json.loads(parser.data)
                for key in ("merchantId", "itemCode", "upc", "name", "receiptName",
                            "description", "category", "packSize"):
                    self.assertEqual(data[key], product[key])
                self.assertEqual(data["merchantName"], MERCHANTS[product["merchantId"]])
                self.assertTrue(data["synthetic"])
                self.assertEqual(data["schemaVersion"], 1)
                self.assertEqual(data["currency"], "USD")
                self.assertEqual(data["catalogPrice"], product["currentPrice"])
                text = " ".join(parser.text)
                self.assertIn(product["itemCode"], text)
                self.assertIn(product["description"], text)
                self.assertIn(product["upc"] or "Not provided", text)
                self.assertIn("not historical receipt prices", text)

    def test_shared_code_is_merchant_scoped(self) -> None:
        names = set()
        for merchant in MERCHANTS:
            parser = PageParser()
            parser.feed(self.pages[f"{merchant}/products/001001.html"])
            data = json.loads(parser.data)
            self.assertEqual(data["merchantId"], merchant)
            self.assertEqual(data["itemCode"], "001001")
            names.add(data["name"])
        self.assertEqual(len(names), 3)

    def test_every_product_has_licensed_local_photo(self) -> None:
        photos = load_photos(self.catalog)
        self.assertEqual(
            {p["file"] for p in photos.values()},
            {p.name for p in (ROOT / "data" / "photos").iterdir() if p.is_file()},
        )
        self.assertTrue(all(p["license"] in ("Public domain", "CC0") for p in photos.values()))
        for merchant in MERCHANTS:
            catalog_html = self.pages[f"{merchant}/index.html"]
            self.assertEqual(catalog_html.count('<figure class="product-photo">'), PRODUCT_COUNTS[merchant])
            parser = PageParser()
            parser.feed(catalog_html)
            self.assertEqual(len(parser.images), PRODUCT_COUNTS[merchant])
        for product in self.catalog["products"]:
            html = self.pages[f'{product["merchantId"]}/products/{product["itemCode"]}.html']
            parser = PageParser()
            parser.feed(html)
            self.assertEqual(len(parser.images), 1)
            image = parser.images[0]
            photo = photos[f'{product["merchantId"]}/{product["itemCode"]}']
            self.assertEqual(image["src"], f'../../assets/photos/{photo["file"]}')
            self.assertIn(product["name"], image["alt"])
            self.assertNotIn(photo["source"], parser.links)
            self.assertNotIn(photo["licenseUrl"], parser.links)
            self.assertIn("../../photo-credits.html", parser.links)
            credits = PageParser()
            credits.feed(self.pages["photo-credits.html"])
            self.assertIn(photo["source"], credits.links)
            self.assertIn(photo["licenseUrl"], credits.links)
            self.assertIn(photo["author"], " ".join(credits.text))
            self.assertIn(
                '<figcaption>Representative product photo; not an exact brand or pack match.</figcaption>',
                html,
            )
            self.assertIn("Representative product photo", html)
            self.assertNotIn("<svg", html)

    def test_reject_attribution_required_photos(self) -> None:
        original = json.loads((ROOT / "data" / "photo-credits.json").read_text(encoding="utf-8"))
        for license_name in ("CC BY 4.0", "CC BY-SA 4.0", "Unknown"):
            manifest = deepcopy(original)
            manifest["warehouse-mart/001001"]["license"] = license_name
            with self.subTest(license=license_name), patch(
                "scripts.build_sites.json.loads", return_value=manifest
            ):
                with self.assertRaisesRegex(ValueError, "Only public-domain or CC0"):
                    load_photos(self.catalog)

    def test_links_resolve_under_github_project_prefix(self) -> None:
        base = Path("receipt-demo-merchants")
        known = {(base / name).as_posix() for name in self.pages}
        photos = load_photos(self.catalog)
        known.update(f'receipt-demo-merchants/assets/photos/{p["file"]}' for p in photos.values())
        import posixpath
        for name, html in self.pages.items():
            if not name.endswith(".html"):
                continue
            parser = PageParser()
            parser.feed(html)
            for link in parser.links + [image["src"] for image in parser.images]:
                parts = urlsplit(link)
                if parts.scheme:
                    self.assertEqual(parts.scheme, "https")
                    self.assertIn(parts.hostname, ("commons.wikimedia.org", "creativecommons.org"))
                    continue
                if not parts.path:
                    continue
                self.assertFalse(parts.scheme or parts.netloc or parts.path.startswith("/"))
                path = posixpath.normpath(
                    posixpath.join("receipt-demo-merchants", posixpath.dirname(name), unquote(parts.path))
                )
                if parts.path.endswith("/"):
                    path += "/index.html"
                self.assertIn(path, known, (name, link))

    def test_html_and_json_escape_catalog_text(self) -> None:
        catalog = deepcopy(self.catalog)
        malicious = '</script><script>alert("demo")</script>&'
        catalog["products"][0]["description"] = malicious
        html = render_pages(catalog)["warehouse-mart/products/001001.html"]
        self.assertNotIn(malicious, html)
        self.assertIn("&lt;/script&gt;", html)
        parser = PageParser()
        parser.feed(html)
        self.assertEqual(json.loads(parser.data)["description"], malicious)

    def test_deterministic_build_and_check(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "docs"
            self.assertEqual(build(ROOT / "data" / "catalogs.json", output), 55)
            self.assertEqual(build(ROOT / "data" / "catalogs.json", output, check=True), 55)
            (output / "index.html").write_text("stale", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "stale"):
                build(ROOT / "data" / "catalogs.json", output, check=True)
            build(ROOT / "data" / "catalogs.json", output)
            (output / "unrelated.txt").write_text("preserve", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Unexpected"):
                build(ROOT / "data" / "catalogs.json", output)
            self.assertEqual((output / "unrelated.txt").read_text(), "preserve")

    def test_reject_invalid_catalog_inputs(self) -> None:
        for field, value in (
            ("itemCode", 1001), ("itemCode", "../001001"),
            ("merchantId", "real-merchant"), ("upc", "123"),
            ("upc", "000000000018"), ("currentPrice", 16),
        ):
            with self.subTest(field=field, value=value), tempfile.TemporaryDirectory() as directory:
                catalog = deepcopy(self.catalog)
                catalog["products"][0][field] = value
                path = Path(directory) / "catalog.json"
                path.write_text(json.dumps(catalog), encoding="utf-8")
                with self.assertRaises(ValueError):
                    load_catalog(path)

    def test_checked_in_pages_are_current(self) -> None:
        self.assertEqual(build(ROOT / "data" / "catalogs.json", ROOT / "docs", check=True), 55)

    def test_electronics_are_warehouse_only_and_keep_existing_products(self) -> None:
        electronics = [p for p in self.catalog["products"] if p["category"] == "Electronics"]
        self.assertEqual(len(electronics), 5)
        self.assertEqual({p["merchantId"] for p in electronics}, {"warehouse-mart"})
        self.assertEqual({p["itemCode"] for p in electronics},
                         {"001016", "001017", "001018", "001019", "001020"})
        self.assertTrue(all(p["upc"] is None for p in electronics))
        self.assertEqual({p["name"] for p in electronics},
                         {"Wireless Headphones", "Bluetooth Speaker", "Laptop",
                          "Computer Monitor", "USB-C Charger"})
        self.assertEqual(len(self.catalog["products"]), 50)
        for merchant, count in PRODUCT_COUNTS.items():
            self.assertIn(f"{count} products", self.pages[f"{merchant}/index.html"])

    def test_photo_credits_link_on_every_page(self) -> None:
        import posixpath
        for name, html in self.pages.items():
            if not name.endswith(".html"):
                continue
            parser = PageParser()
            parser.feed(html)
            links = [
                link for link in parser.links
                if posixpath.normpath(posixpath.join(posixpath.dirname(name), link))
                == "photo-credits.html"
            ]
            self.assertEqual(len(links), 1, name)


if __name__ == "__main__":
    unittest.main()
