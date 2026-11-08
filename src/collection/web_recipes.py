"""Public recipe discovery and extraction. No login, challenge bypass or invented steps."""

import html
import json
import re
import threading
import time
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import quote, unquote, urljoin, urlparse, urlunparse

import requests
from bs4 import BeautifulSoup

from src.food_entry import dish_key
from src.models import Recipe

SOURCES = {
    "xiachufang": {
        "name": "下厨房",
        "hosts": {"www.xiachufang.com", "m.xiachufang.com", "xiachufang.com"},
        "search": "https://www.xiachufang.com/search/?keyword={q}",
    },
    "meishichina": {
        "name": "美食天下",
        "hosts": {"home.meishichina.com", "m.meishichina.com", "www.meishichina.com"},
        "search": "https://home.meishichina.com/search/recipe/?q={q}",
    },
    "douguo": {
        "name": "豆果美食",
        "hosts": {"www.douguo.com", "m.douguo.com", "douguo.com"},
        "search": "https://www.douguo.com/search/recipe/{q}",
    },
    "xiaohongshu": {
        "name": "小红书",
        "hosts": {"www.xiaohongshu.com", "xiaohongshu.com", "xhslink.com", "www.xhslink.com"},
        "search": "https://www.xiaohongshu.com/search_result?keyword={q}&source=web_search_result_notes",
    },
    "woks": {
        "name": "The Woks of Life · 原文英文",
        "hosts": {"thewoksoflife.com", "www.thewoksoflife.com"},
        "search": "https://thewoksoflife.com/?s={q}",
    },
}
HOSTS = {host: source for source, info in SOURCES.items() for host in info["hosts"]}
SEARCH_TERMS = {
    "番茄炒蛋": "tomato egg",
    "红烧肉": "braised pork belly",
    "鱼香肉丝": "yu xiang pork",
    "宫保鸡丁": "kung pao chicken",
    "麻婆豆腐": "mapo tofu",
    "糖醋里脊": "sweet sour pork",
    "可乐鸡翅": "coca cola chicken wings",
    "酸菜鱼": "suan cai fish",
    "白切鸡": "poached chicken",
    "地三鲜": "di san xian",
    "酸辣土豆丝": "shredded potato",
    "蛋炒饭": "egg fried rice",
    "葱油拌面": "scallion oil noodles",
    "凉拌黄瓜": "smashed cucumber",
    "香菇蒸鸡": "steamed chicken mushroom",
    "蒜蓉西兰花": "broccoli garlic",
    "香煎豆腐": "pan fried tofu",
}

MAX_BYTES = 3_000_000


def source_identity(url):
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    path = unquote(parsed.path)
    if "xiachufang.com" in host and (m := re.search(r"/recipe/(\d+)", path)):
        return "xiachufang:" + m[1]
    if "douguo.com" in host and (m := re.search(r"/(?:cookbook|recipe(?:/amp|/imgs)?)/(\d+)", path)):
        return "douguo:" + m[1]
    if "meishichina.com" in host and (m := re.search(r"/(?:recipe-|recipe/)(\d+)", path)):
        return "meishichina:" + m[1]
    if "xiaohongshu.com" in host and (m := re.search(r"/(?:explore|discovery/item)/([a-zA-Z0-9]+)", path)):
        return "xiaohongshu:" + m[1]
    return host.removeprefix("www.") + path.rstrip("/")


def checked_url(value, expected=None):
    # Accept a copied share message, but never arbitrary URL schemes or hosts.
    found = re.search(r"https?://[^\s<>「」“”]+", value.strip())
    url = (found[0] if found else value.strip()).rstrip("。，,；;）)")
    if re.fullmatch(r"\d{1,20}", url):
        url = "https://www.xiachufang.com/recipe/" + url + "/"
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    try:
        port = parsed.port
    except ValueError as exc:
        raise ValueError("分享链接端口无效") from exc
    if (
        parsed.scheme not in {"http", "https"}
        or host not in HOSTS
        or parsed.username
        or parsed.password
        or port not in {None, 443}
    ):
        raise ValueError("目前支持下厨房、美食天下、豆果、小红书分享链接和 The Woks of Life 的公开页面")
    source = HOSTS[host]
    if expected and source != expected:
        raise ValueError("跳转超出了原菜谱站点，已停止提取")
    return urlunparse(("https", host, parsed.path or "/", parsed.params, parsed.query, "")), source


def clean_text(value):
    return " ".join(BeautifulSoup(str(value), "html.parser").get_text(" ", strip=True).split())


def parse_narration(name, narration, materials=None):
    text = narration.strip()
    if not text:
        raise ValueError("做法可以留空去网上找；直接保存口述时需要至少一句你知道的做法")
    steps = [
        re.sub(r"^\s*(?:第?[一二三四五六七八九十\d]+[步、.．:：)]\s*)", "", line).strip()
        for line in re.split(r"\n+|[。；;]+", text)
    ]
    steps = [s for s in steps if s]
    if not steps or any(len(s) > 2000 for s in steps) or len(steps) > 60:
        raise ValueError("请把口述分成清晰的步骤，每步不超过 2000 字，最多 60 步")
    return Recipe(
        name=name,
        materials=materials or [],
        methods=steps,
        original_text=text,
        description="按你的口述整理；食材与用量可稍后补充。",
    )


def _structured_recipe(soup):
    def visit(value, depth=0):
        if depth > 12:
            return None
        if isinstance(value, list):
            return next((r for v in value if (r := visit(v, depth + 1))), None)
        if isinstance(value, dict):
            kind = value.get("@type", [])
            if kind == "Recipe" or isinstance(kind, list) and "Recipe" in kind:
                return value
            return visit(value.get("@graph", []), depth + 1)
        return None

    for script in soup.select('script[type="application/ld+json"]'):
        raw = script.string or script.get_text()
        if len(raw) > 500000:
            continue
        try:
            result = visit(json.loads(raw))
            if result:
                return result
        except (ValueError, TypeError, RecursionError):
            pass
    return None


def instruction_lines(value):
    if isinstance(value, str):
        return [x.strip() for x in re.split(r"\n+", clean_text(value)) if x.strip()]
    if isinstance(value, list):
        return [line for v in value for line in instruction_lines(v)]
    if isinstance(value, dict):
        return instruction_lines(value.get("itemListElement", value.get("text", "")))
    return []


def xhs_note(soup):
    for script in soup.select("script"):
        text = script.string or ""
        if "__INITIAL_STATE__" not in text:
            continue
        raw = text.split("__INITIAL_STATE__", 1)[1].lstrip(" =").rstrip("; \n")
        # Replace JS undefined tokens outside strings; never eval a page's JavaScript.
        raw = re.sub(
            r'("(?:\\.|[^"\\])*"|\bundefined\b)', lambda m: "null" if m[0] == "undefined" else m[0], raw
        )
        try:
            state = json.loads(raw)
        except (ValueError, RecursionError):
            continue
        if not isinstance(state, dict) or not isinstance(state.get("note"), dict):
            continue
        detail = state["note"].get("noteDetailMap", {})
        if not isinstance(detail, dict):
            continue
        for item in detail.values():
            if isinstance(item, dict) and isinstance(item.get("note"), dict):
                return item["note"]
    title = soup.select_one('meta[property="og:title"],meta[name="og:title"]')
    desc = soup.select_one('meta[name="description"],meta[property="og:description"]')
    return {
        "title": title.get("content", "") if title else "",
        "desc": desc.get("content", "") if desc else "",
    }


def parse_public_recipe(body, url, fallback_name=""):
    url, source = checked_url(url)
    soup = BeautifulSoup(body, "html.parser")
    structured = _structured_recipe(soup)
    title = soup.select_one("h1")
    name = (
        clean_text(structured.get("name", ""))
        if structured
        else clean_text(title.get_text())
        if title
        else ""
    )
    author = ""
    materials = []
    methods = []
    original = ""
    if structured:
        for line in structured.get("recipeIngredient", []):
            if isinstance(line, str) and line.strip():
                materials.append({"name": clean_text(line)[:80], "unit": "按原文"})
        methods = instruction_lines(structured.get("recipeInstructions", []))
        who = structured.get("author", "")
        if isinstance(who, list):
            author = "、".join(
                clean_text(v.get("name", "")) if isinstance(v, dict) else clean_text(v) for v in who
            )
        elif isinstance(who, dict):
            author = clean_text(who.get("name", ""))
        elif isinstance(who, str):
            author = clean_text(who)
    if source == "woks":
        visible = []
        for row in soup.select(".wprm-recipe-ingredient"):
            n = row.select_one(".wprm-recipe-ingredient-name")
            amount = row.select_one(".wprm-recipe-ingredient-amount")
            unit = row.select_one(".wprm-recipe-ingredient-unit")
            if n and n.get_text(strip=True):
                visible.append(
                    {
                        "name": n.get_text(" ", strip=True),
                        "unit": " ".join(v.get_text(" ", strip=True) for v in [amount, unit] if v is not None)
                        or "按原文",
                    }
                )
        if visible:
            materials = visible
    if source == "xiachufang":
        for row in soup.select(".ings tr"):
            n, u = row.select_one(".name"), row.select_one(".unit")
            if n:
                materials.append(
                    {
                        "name": n.get_text(" ", strip=True),
                        "unit": u.get_text(" ", strip=True) if u else "按原文",
                    }
                )
        methods = methods or [
            n.get_text(" ", strip=True) for n in soup.select(".steps li p.text, .steps li p")
        ]
        who = soup.select_one(".author .name,.author a")
        author = author or (who.get_text(strip=True) if who else "")
    elif source == "meishichina":
        for row in soup.select(".recipeCategory_sub_R li"):
            n, u = row.select_one(".category_s1"), row.select_one(".category_s2")
            if n:
                materials.append(
                    {
                        "name": n.get_text(" ", strip=True),
                        "unit": u.get_text(" ", strip=True) if u else "按原文",
                    }
                )
        for node in soup.select(".recipeStep_word"):
            clone = BeautifulSoup(str(node), "html.parser")
            for index in clone.select(".recipeStep_num"):
                index.decompose()
            methods.append(clone.get_text(" ", strip=True))
        who = soup.select_one(".recipe_De_author a,#recipe_DeAuthor a,#recipe_DeAuthor,.userInfo .name")
        author = author or (who.get_text(" ", strip=True) if who else "")
    elif source == "douguo":
        for row in soup.select(".retamr tr,.material tr"):
            cells = row.select("td")
            for i in range(0, len(cells), 2):
                if i + 1 < len(cells):
                    materials.append(
                        {
                            "name": cells[i].get_text(" ", strip=True),
                            "unit": cells[i + 1].get_text(" ", strip=True) or "按原文",
                        }
                    )
        methods = methods or [
            n.get_text(" ", strip=True) for n in soup.select(".stepinfo,.cookstepdesc,.step .text")
        ]
        who = soup.select_one(".author-info .nickname,.author-name,.author a")
        author = author or (who.get_text(" ", strip=True) if who else "")
    elif source == "xiaohongshu":
        note = xhs_note(soup)
        name = clean_text(note.get("title", "")) or name
        original = note.get("desc", "")[:15000]
        who = note.get("user", {})
        author = clean_text(who.get("nickname", "")) if isinstance(who, dict) else ""
        # Only explicitly numbered instructions or a labelled method section count.
        method_section = re.search(r"(?:做法|步骤|制作方法)\s*[:：]?\s*\n?([\s\S]+)", original)
        if method_section:
            methods = [
                v.strip()
                for v in re.split(r"\n+|[。；;]+", method_section[1])
                if v.strip() and not v.strip().startswith("#")
            ]
        else:
            methods = [
                re.sub(r"^\s*\d+[.、．)）]\s*", "", v).strip()
                for v in original.splitlines()
                if re.match(r"^\s*\d+[.、．)）]", v)
            ]
    # Preserve exact words; do not translate or infer missing ingredients/amounts.
    name = (name or fallback_name).strip()[:100]
    methods = list(dict.fromkeys(m.strip() for m in methods if m.strip()))[:60]
    if any(len(m) > 2000 for m in methods):
        raise ValueError("原文单步过长，请打开原文或粘贴可辨认的做法")
    materials = list({(m["name"], m["unit"]): m for m in materials if m["name"]}.values())[:80]
    if not methods or not name:
        challenge = any(
            t in soup.get_text(" ", strip=True)[:3000]
            for t in [
                "滑动验证",
                "安全验证",
                "访问验证",
                "Just a moment",
                "Attention Required",
                "请先登录",
                "登录后查看",
            ]
        )
        return {
            "status": "partial",
            "name": fallback_name or name,
            "author": author,
            "source_url": url,
            "narration": original,
            "materials": materials,
            "message": "来源要求登录或验证，未读取到完整做法。可打开原文、粘贴可见正文，或换一个来源。"
            if challenge
            else "公开页面未包含可辨认的完整做法；没有推测或补写步骤。可粘贴原文或换来源。",
        }
    recipe = Recipe(
        name=name,
        materials=materials,
        methods=methods,
        source_url=url,
        author=author[:200],
        xcf_id=re.search(r"/recipe/(\d+)", url)[1]
        if source == "xiachufang" and re.search(r"/recipe/(\d+)", url)
        else None,
        description="从公开原文提取；用时、人份和食材克重请按实际校正。",
        original_text=original,
    )
    return {
        "status": "ready",
        "recipe": recipe.model_dump(),
        "source": SOURCES[source]["name"],
        "warnings": (["原文未提供独立食材表，食材待补充；暂不核算热量。"] if not materials else [])
        + ["用时和人份为待校正的默认值，热量以实际用料为准。"],
    }


class RecipeFinder:
    def __init__(self):
        self.cache = {}
        self.lock = threading.Lock()

    @staticmethod
    def _get(url, params=None):
        response = requests.get(
            url,
            params=params,
            timeout=(3, 8),
            allow_redirects=False,
            stream=True,
            headers={"User-Agent": "HealthRecipe/3.0 (personal public recipe reader)"},
        )
        return response

    def fetch(self, value, name=""):
        url, source = checked_url(value)
        key = ("page", url)
        with self.lock:
            cached = self.cache.get(key)
        if cached and time.time() - cached[0] < 300:
            return cached[1]
        try:
            for _ in range(4):
                with self._get(url) as response:
                    if response.status_code in {301, 302, 303, 307, 308}:
                        url, _ = checked_url(
                            urljoin(url, response.headers.get("Location", "")), expected=source
                        )
                        continue
                    if response.status_code != 200:
                        return {
                            "status": "blocked",
                            "name": name,
                            "source_url": url,
                            "source": SOURCES[source]["name"],
                            "message": f"来源返回 {response.status_code}，可能需要登录或稍后重试；可以换来源或粘贴公开正文。",
                        }
                    chunks = []
                    total = 0
                    started = time.monotonic()
                    for chunk in response.iter_content(65536):
                        total += len(chunk)
                        if total > MAX_BYTES or time.monotonic() - started > 15:
                            raise ValueError("页面过大或读取超时，请打开原文或粘贴正文")
                        chunks.append(chunk)
                    result = parse_public_recipe(b"".join(chunks), url, name)
                    with self.lock:
                        self.cache[key] = (time.time(), result)
                    return result
            raise ValueError("分享链接跳转过多，请粘贴最终菜谱链接")
        except requests.RequestException as exc:
            raise ValueError("暂时无法读取这个来源，可以换一个来源或粘贴正文") from exc

    def _bing(self, name, sources):
        try:
            with self._get(
                "https://www.bing.com/search", {"q": name + " 菜谱 做法", "format": "rss", "count": 20}
            ) as response:
                if response.status_code != 200:
                    return [], "搜索服务暂不可用"
                data = response.content
                if len(data) > MAX_BYTES:
                    return [], "搜索响应过大"
            tree = ET.fromstring(data)
            items = []
            for entry in tree.findall(".//item"):
                title = clean_text(entry.findtext("title", ""))
                link = entry.findtext("link", "")
                try:
                    url, source = checked_url(link)
                except ValueError:
                    continue
                if source not in sources or not relevant(name, title):
                    continue
                if source == "xiachufang" and "/recipe/" not in url:
                    continue
                if source == "meishichina" and not re.search(r"/(?:recipe-|recipe/)\d+", url):
                    continue
                if source == "douguo" and not re.search(r"/(?:cookbook|recipe)/", url):
                    continue
                items.append(
                    {
                        "title": title[:200],
                        "url": url,
                        "source": source,
                        "source_name": SOURCES[source]["name"],
                        "summary": "搜索结果；点击提取后确认实际做法。",
                        "language": "en" if source == "woks" else "zh",
                    }
                )
            return items, None
        except (requests.RequestException, ET.ParseError, ValueError):
            return [], "搜索服务暂不可用"

    def _woks(self, name):
        try:
            terms = list(dict.fromkeys([name, SEARCH_TERMS.get(dish_key(name), name)]))
            found = []
            for term in terms:
                with self._get(
                    "https://thewoksoflife.com/wp-json/wp/v2/search",
                    {"search": term, "per_page": 12, "type": "post"},
                ) as response:
                    if response.status_code != 200:
                        continue
                    data = response.json()
                if not isinstance(data, list):
                    continue
                found.extend(
                    {
                        "title": clean_text(r["title"])[:200],
                        "url": checked_url(r["url"], "woks")[0],
                        "source": "woks",
                        "source_name": SOURCES["woks"]["name"],
                        "summary": "公开食谱搜索结果，保留英文原文。",
                        "language": "en",
                    }
                    for r in data
                    if isinstance(r, dict) and r.get("url") and relevant(name, clean_text(r.get("title", "")))
                )
                if len(found) >= 3:
                    break
            return list({i["url"]: i for i in found}.values())[:8], None
        except (requests.RequestException, ValueError, KeyError, TypeError):
            return [], "双语食谱搜索暂不可用"

    def search(self, name, sources):
        sources = list(dict.fromkeys(sources))
        key = ("search", name, tuple(sorted(sources)))
        with self.lock:
            cached = self.cache.get(key)
        if cached and time.time() - cached[0] < 300:
            return cached[1]
        with ThreadPoolExecutor(max_workers=2) as pool:
            general = pool.submit(self._bing, name, sources)
            bilingual = pool.submit(self._woks, name) if "woks" in sources else None
            items, error = general.result()
            other, other_error = bilingual.result() if bilingual else ([], None)
        combined = list({source_identity(i["url"]): i for i in [*items, *other]}.values())[:18]
        # Exact Chinese matches first; retrieval has not yet proved that every result is a recipe.
        combined.sort(
            key=lambda i: (dish_key(name) not in dish_key(i["title"]), i["source"] != "woks", len(i["title"]))
        )
        result = {
            "query": name,
            "items": combined,
            "warnings": [m for m in [error, other_error] if m],
            "sources": [
                {
                    "id": s,
                    "name": SOURCES[s]["name"],
                    "search_url": SOURCES[s]["search"].format(q=quote(name)),
                    "count": sum(i["source"] == s for i in combined),
                    "note": "可粘贴分享链接尝试读取公开文字；站内搜索可能需要登录。"
                    if s == "xiaohongshu"
                    else "直接打开站内搜索，或从下面选择公开结果。",
                }
                for s in sources
            ],
            "message": "选择一个结果提取并预览；网站限制时可换来源，不会编造缺少的做法。",
        }
        with self.lock:
            self.cache[key] = (time.time(), result)
        return result


def relevant(name, title):
    key = dish_key(name)
    candidate = dish_key(html.unescape(title))
    if key and key in candidate:
        return True
    aliases = {
        "番茄炒蛋": ["tomatoegg", "tomatoandegg"],
        "红烧肉": ["braisedporkbelly", "hongshaorou"],
        "宫保鸡丁": ["kungpaochicken"],
        "麻婆豆腐": ["mapotofu"],
        "酸辣汤": ["hotandsoursoup"],
    }
    if key == "番茄炒蛋":
        return all(word in candidate for word in ["tomato", "egg"]) and any(
            word in candidate for word in ["stir", "scrambl"]
        )
    translated = SEARCH_TERMS.get(key, "").split()
    return (
        bool(translated)
        and all(part in candidate for part in translated)
        or any(alias in candidate for alias in aliases.get(key, []))
    )
