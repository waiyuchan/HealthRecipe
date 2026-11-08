"""Parse the checked-in category snapshot without side effects on import."""

import json
import re
from pathlib import Path
from urllib.parse import urljoin

from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[2]


def extract_categories(html):
    soup = BeautifulSoup(html, "html.parser")
    result = {}
    for group in soup.select(".cates-list"):
        label, content = group.select_one(".cates-list-info"), group.select_one(".cates-list-all")
        if not label or not content:
            continue
        sections = {}
        for heading in content.select("h4"):
            link = heading.select_one("a")
            listing = heading.find_next_sibling("ul")
            items = []
            for item in listing.select("li a") if listing else []:
                items.append(
                    {
                        "name": re.sub(r"[\d.]+", "", item.get_text(strip=True)),
                        "url": urljoin("https://www.xiachufang.com", item.get("href", "")),
                    }
                )
            sections[heading.get_text(strip=True)] = {
                "url": link.get("href", "") if link else "",
                "items": items,
            }
        result[label.get_text(strip=True)] = sections
    return result


if __name__ == "__main__":
    result = extract_categories((ROOT / "data/category.html").read_text())
    (ROOT / "data/category.json").write_text(json.dumps(result, ensure_ascii=False, indent=2))
