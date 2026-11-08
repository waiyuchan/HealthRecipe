"""Fetch one explicitly selected Xiachufang recipe with bounded network I/O."""

import json
import re
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup


def str_cleaner(string):
    return " ".join(string.split())


def recipe_id_from_input(value):
    value = str(value).strip()
    if re.fullmatch(r"\d{1,20}", value):
        return value
    url = urlparse(value)
    matched = re.fullmatch(r"/recipe/(\d{1,20})/?", url.path)
    if url.scheme == "https" and url.netloc in {"www.xiachufang.com", "xiachufang.com"} and matched:
        return matched[1]
    raise ValueError("请输入下厨房菜谱数字 ID 或 https://www.xiachufang.com/recipe/数字/ 链接")


def parse_recipe(html, recipe_id):
    soup = BeautifulSoup(html, "html.parser")
    structured = None

    def find_recipe(value):
        if isinstance(value, list):
            return next((found for v in value if (found := find_recipe(v))), None)
        if isinstance(value, dict):
            types = value.get("@type", [])
            if types == "Recipe" or isinstance(types, list) and "Recipe" in types:
                return value
            return find_recipe(value.get("@graph", []))
        return None

    for script in soup.select('script[type="application/ld+json"]'):
        try:
            structured = find_recipe(json.loads(script.string or script.get_text()))
        except (ValueError, TypeError):
            continue
        if structured:
            break
    title = soup.select_one("h1.page-title, h1")
    ingredients = []
    for row in soup.select(".ings tr"):
        name, amount = row.select_one(".name"), row.select_one(".unit")
        if name:
            ingredients.append(
                {
                    "name": str_cleaner(name.get_text()),
                    "unit": str_cleaner(amount.get_text()) if amount else "适量",
                }
            )
    methods = [str_cleaner(step.get_text()) for step in soup.select(".steps li p.text, .steps li p")]
    if structured:
        name = structured.get("name") or (title.get_text() if title else "")
        if not ingredients:
            ingredients = [
                {"name": str_cleaner(str(v)), "unit": "按原方"}
                for v in structured.get("recipeIngredient", [])
            ]

        def instruction_text(value):
            if isinstance(value, str):
                return [str_cleaner(BeautifulSoup(value, "html.parser").get_text())]
            if isinstance(value, dict):
                return instruction_text(value.get("itemListElement", value.get("text", "")))
            if isinstance(value, list):
                return [text for step in value for text in instruction_text(step)]
            return []

        if not methods:
            methods = instruction_text(structured.get("recipeInstructions", []))
    else:
        name = title.get_text() if title else ""
    methods = [m for m in methods if m]
    author = structured.get("author", "") if structured else ""
    if isinstance(author, list):
        author = "、".join(str(a.get("name", "")) if isinstance(a, dict) else str(a) for a in author)
    elif isinstance(author, dict):
        author = author.get("name", "")
    if not author:
        author_node = soup.select_one(".author .name, .author a")
        author = str_cleaner(author_node.get_text()) if author_node else ""
    if not name.strip() or not ingredients or not methods:
        raise ValueError("页面未包含完整菜谱，可能需要登录、触发访问限制或页面结构已变；可以手动录入")
    return {
        "xcf_id": str(recipe_id),
        "name": str_cleaner(name),
        "materials": ingredients,
        "methods": methods,
        "author": str(author),
        "source_url": f"https://www.xiachufang.com/recipe/{recipe_id}/",
    }


def recipe_extractor(recipe_id):
    recipe_id = recipe_id_from_input(recipe_id)
    try:
        with requests.get(
            f"https://www.xiachufang.com/recipe/{recipe_id}/",
            headers={"User-Agent": "HealthRecipe/1.0 (personal recipe importer)"},
            timeout=(5, 15),
            allow_redirects=False,
            stream=True,
        ) as response:
            if response.status_code != 200:
                raise ValueError(f"菜谱网站返回 {response.status_code}，可稍后重试或手动录入")
            chunks, total = [], 0
            for chunk in response.iter_content(65536):
                total += len(chunk)
                if total > 3_000_000:
                    raise ValueError("菜谱页面过大，请手动录入")
                chunks.append(chunk)
            html = b"".join(chunks).decode("utf-8", errors="replace")
    except requests.RequestException as exc:
        raise ValueError("无法连接菜谱网站，请检查网络或手动录入") from exc
    return parse_recipe(html, recipe_id)


def recipe_printer(recipe):
    print(json.dumps(recipe, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("recipe_id")
    recipe_printer(recipe_extractor(parser.parse_args().recipe_id))
