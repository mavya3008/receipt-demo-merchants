"""Download reusable Wikimedia product-type photos and preserve license evidence."""

import hashlib
from html import unescape
import json
from pathlib import Path
import re
import time
from urllib.error import HTTPError
from urllib.parse import urlencode, urlsplit, unquote
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
PHOTO_OVERRIDES = {
    "Mint tea": "File:Peppermint Tea in a pot - Abyssinia.jpg",
    "Carbonated water": "File:Blue glass with carbonated water.jpg",
    "Apple": "File:Multicoloredapples001.jpg",
    "Pea": "File:USDA 2026 Peas frozen.png",
    "Strained yogurt": "File:Strained yogurt (20250302).jpg",
    "Brown rice": "File:Tricolor brown rice.jpg",
    "Blueberry": "File:Blueberries in a little bowl.jpg",
    "Spinach": "File:Spinach Plant Nourishment Meal Fresh Healthy Bio.jpg",
    "Quinoa": "File:Bolivian quinoa (1).jpg",
    "Avocado": "File:Avocado Fruit Harvested From Backyard.jpg",
    "USB-C": "File:Baseus CCCP20UE 20W USB charger-0.jpg",
    "Almond": "File:Almonds02.jpg",
    "Almond milk": "File:Almond effect plant protein drink.jpg",
    "Banana": "File:Banana caturra.JPG",
    "Black tea": "File:Nice Cup of Tea.jpg",
    "Black turtle bean": "File:BLACK TURTLE BEANS.jpg",
    "Bluetooth speaker": "File:JBL Boombox 2 1v2.jpg",
    "Butter": "File:Butter and Knive.jpg",
    "Cheddar cheese": "File:Cheese 46 bg 060106.jpg",
    "Cherry tomato": "File:Cherry-Tomatoes-in-Pack.jpg",
    "Computer monitor": "File:Computer monitor samsung.jpg",
    "Dishwashing liquid": "File:Diskmedel.JPG",
    "Egg as food": "File:6-Pack-Chicken-Eggs.jpg",
    "Flour": "File:Flour 01.jpg",
    "Granola": "File:Granola Honey and Vanilla Top.jpg",
    "Headphones": "File:Headphones on wood in black and white (Unsplash).jpg",
    "Hummus": "File:Houmous.jpg",
    "Laptop": "File:Samsung QX-511 (2).JPG",
    "Lentil": "File:Red lentils (1).jpg",
    "Milk": "File:Milk 2.jpg",
    "Oat milk": "File:Oatmilk 1.jpg",
    "Olive oil": "File:Olive Oil (Unsplash).jpg",
    "Paper towel": "File:Reczniki papierowe.jpg",
    "Peanut butter": "File:Six different types of peanut butter on a counter.jpg",
    "Soap": "File:Bars of pure Marseille and Aleppo soap, 2024.jpg",
    "Tofu": "File:Home-madeTofu.JPG",
    "White bread": "File:White sandwich bread.jpg",
    "White rice": "File:White rice on a brown table.jpg",
    "Whole wheat bread": "File:Two slices of Kingsmill bread.jpg",
}
TOPICS = {
    "Morning Roast Coffee": "Coffee bean", "Rolled Oats": "Rolled oats",
    "Olive Oil": "Olive oil", "Greek Yogurt": "Strained yogurt",
    "Paper Towels": "Paper towel", "Brown Rice": "Brown rice",
    "Almonds": "Almond", "Frozen Berries": "Blueberry",
    "Dish Soap": "Dishwashing liquid", "Whole Wheat Bread": "Whole wheat bread",
    "Cheddar Cheese": "Cheddar cheese", "Sparkling Water": "Carbonated water",
    "Laundry Detergent": "Laundry detergent", "Peanut Butter": "Peanut butter",
    "Eggs": "Egg as food", "Breakfast Tea": "Black tea", "White Rice": "White rice",
    "Tomato Sauce": "Tomato sauce", "Whole Milk": "Milk",
    "Sandwich Bread": "White bread", "Bananas": "Banana", "Penne Pasta": "Penne",
    "Potato Chips": "Potato chip", "Hand Soap": "Soap", "Orange Juice": "Orange juice",
    "Canned Beans": "Black turtle bean", "Flour": "Flour", "Butter": "Butter",
    "Frozen Peas": "Pea", "Apples": "Apple", "Herbal Mint Tea": "Mint tea",
    "Organic Spinach": "Spinach", "Sourdough Bread": "Sourdough",
    "Oat Milk": "Oat milk", "Hummus": "Hummus", "Avocados": "Avocado",
    "Quinoa": "Quinoa", "Dark Chocolate": "Dark chocolate",
    "Almond Beverage": "Almond milk", "Tofu": "Tofu",
    "Cherry Tomatoes": "Cherry tomato", "Granola": "Granola",
    "Lentils": "Lentil", "Blueberries": "Blueberry", "Carrots": "Carrot",
    "Wireless Headphones": "Headphones", "Bluetooth Speaker": "Bluetooth speaker",
    "Laptop": "Laptop", "Computer Monitor": "Computer monitor",
    "USB-C Charger": "USB-C",
}


def get(url: str) -> bytes:
    request = Request(url, headers={"User-Agent": "ReceiptDemo/1.0 (educational merchant catalog)"})
    for attempt in range(4):
        try:
            with urlopen(request, timeout=60) as response:
                content = response.read(20_000_001)
            break
        except HTTPError as error:
            if error.code not in (429, 503) or attempt == 3:
                raise
            delay = max(30 * (attempt + 1), int(error.headers.get("Retry-After", "0")))
            print(f"HTTP {error.code}; waiting {delay}s before retry: {url}", flush=True)
            time.sleep(delay)
    if len(content) > 20_000_000:
        raise ValueError(f"Photo response exceeds 20 MB: {url}")
    return content


def query(host: str, **parameters: str) -> dict:
    url = f"https://{host}/w/api.php?" + urlencode(
        {"action": "query", "format": "json", **parameters}
    )
    return json.loads(get(url))


def plain(value: str) -> str:
    return unescape(re.sub(r"<[^>]+>", "", value)).strip()


def main() -> None:
    catalog = json.loads((ROOT / "data" / "catalogs.json").read_text())
    topics = sorted(set(TOPICS.values()))
    response = query("en.wikipedia.org", prop="pageimages", piprop="original",
                     redirects="1", titles="|".join(topics))
    normalized = {p["from"]: p["to"] for p in response["query"].get("normalized", [])}
    redirects = {p["from"]: p["to"] for p in response["query"].get("redirects", [])}
    pages = {p["title"]: p for p in response["query"]["pages"].values()}
    files = {}
    for topic in topics:
        if topic in PHOTO_OVERRIDES:
            files[topic] = PHOTO_OVERRIDES[topic]
            continue
        title = normalized.get(topic, topic)
        title = redirects.get(title, title)
        original = pages[title].get("original", {}).get("source", "")
        if "/wikipedia/commons/" not in original:
            raise ValueError(f"No reusable Commons photo discovered for {topic}: {original}")
        files[topic] = "File:" + unquote(urlsplit(original).path.rsplit("/", 1)[1])
    metadata = query("commons.wikimedia.org", prop="imageinfo",
                     iiprop="url|extmetadata", iiurlwidth="640",
                     titles="|".join(sorted(set(files.values()))))
    images = {p["title"].replace("_", " "): p["imageinfo"][0]
              for p in metadata["query"]["pages"].values()}
    output = ROOT / "data" / "photos"
    output.mkdir(exist_ok=True)
    manifest_path = ROOT / "data" / "photo-credits.json"
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
    downloaded = {}
    for product in catalog["products"]:
        topic = TOPICS[product["name"]]
        key = f'{product["merchantId"]}/{product["itemCode"]}'
        info = images[files[topic].replace("_", " ")]
        meta = info["extmetadata"]
        license_name = meta["LicenseShortName"]["value"]
        if license_name not in ("Public domain", "CC0"):
            raise ValueError(f"Only public-domain or CC0 photos are allowed for {topic}: {license_name}")
        if meta.get("Restrictions", {}).get("value"):
            raise ValueError(f"Photo has additional restrictions: {topic}")
        if key in manifest:
            saved = output / manifest[key]["file"]
            if (manifest[key]["topic"] == topic and manifest[key]["source"] == info["descriptionurl"]
                    and manifest[key]["license"] == license_name and saved.is_file()
                    and hashlib.sha256(saved.read_bytes()).hexdigest() == manifest[key]["sha256"]):
                print(f"{key}: verified existing download", flush=True)
                continue
        source = info.get("thumburl", info["url"])
        if source not in downloaded:
            time.sleep(2)
            content = get(source)
            if content.startswith(b"\xff\xd8\xff"):
                suffix = ".jpg"
            elif content.startswith(b"\x89PNG\r\n"):
                suffix = ".png"
            elif content.startswith(b"RIFF") and content[8:12] == b"WEBP":
                suffix = ".webp"
            else:
                raise ValueError(f"Expected JPEG, PNG or WebP photograph for {topic}: {content[:40]!r}")
            filename = hashlib.sha256(content).hexdigest()[:20] + suffix
            (output / filename).write_bytes(content)
            downloaded[source] = (filename, hashlib.sha256(content).hexdigest())
        filename, digest = downloaded[source]
        key = f'{product["merchantId"]}/{product["itemCode"]}'
        manifest[key] = {
            "file": filename, "sha256": digest, "topic": topic,
            "source": info["descriptionurl"], "downloadUrl": source,
            "author": plain(meta.get("Artist", {}).get("value", "See source page")),
            "license": license_name,
            "licenseUrl": meta.get("LicenseUrl", {}).get(
                "value", "https://commons.wikimedia.org/wiki/Commons:Public_domain"),
            "description": plain(meta.get("ImageDescription", {}).get("value", topic)),
            "changes": "Displayed at a fixed aspect ratio with CSS cropping; no source edits.",
        }
        print(f'{key}: {topic} / {license_name}', flush=True)
        manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=True) + "\n",
                                 encoding="utf-8")
    (ROOT / "data" / "photo-credits.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
