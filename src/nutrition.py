"""Auditable estimates from edible weights; unknown quantities never become zero."""

import json
import re
from collections import Counter
from datetime import date, timedelta
from pathlib import Path

from src.food_entry import dish_key

REFERENCE = json.loads((Path(__file__).resolve().parents[1] / "data/nutrition.json").read_text())
FOODS = {name: item for item in REFERENCE["foods"] for name in [item["name"], *item["aliases"]]}
# Typical edible kitchen portions, explicitly reported as assumptions, not measured facts.
PORTIONS = {
    "番茄": ("个", 150),
    "鸡蛋": ("个", 50),
    "香菇": ("朵", 15),
    "西兰花": ("颗", 300),
    "嫩豆腐": ("盒", 300),
    "豆腐": ("盒", 300),
    "胡萝卜": ("根", 150),
    "黄瓜": ("根", 200),
    "彩椒": ("个", 150),
    "白萝卜": ("根", 500),
    "大蒜": ("瓣", 3),
    "生姜": ("片", 2),
    "小葱": ("根", 5),
    "玉米": ("根", 150),
    "青菜": ("棵", 50),
}
DENSITY = {"食用油": 0.92, "香油": 0.92, "生抽": 1.16, "蒸鱼豉油": 1.16, "牛奶": 1.03, "淀粉": 0.54}


def ingredient_weight(material):
    if material.get("grams") is not None:
        return float(material["grams"]), []
    name, unit = material["name"], material.get("unit", "").replace(" ", "").lower()
    match = re.search(r"(\d+(?:\.\d+)?)\s*(千克|公斤|kg|克|g|毫升|ml|升|l)", unit)
    warnings = []
    if re.search(r"-\s*\d", unit):
        return None, ["用量出现负数，请确认可食克重"]
    if match:
        value, measure = float(match[1]), match[2]
        value *= 1000 if measure in {"千克", "公斤", "kg", "升", "l"} else 1
        if value <= 0 or value > 100000:
            return None, ["用量超出可核算范围，请确认可食克重"]
        if measure in {"毫升", "ml", "升", "l"}:
            value *= DENSITY.get(name, 1)
            warnings.append(f"{name}：液体体积按参考密度折算克重")
        if name in {"排骨", "鲈鱼"}:
            factor = 0.6 if name == "排骨" else 0.55
            value *= factor
            warnings.append(f"{name}：含骨重量暂按 {factor:.0%} 可食率估算，请填去骨克重校正")
        return value, warnings
    match = re.search(r"(\d+(?:\.\d+)?|半)(汤匙|茶匙|勺|个|颗|根|盒|瓣|朵|片|棵)", unit)
    if not match:
        return None, []
    count = 0.5 if match[1] == "半" else float(match[1])
    if match[2] in {"汤匙", "茶匙", "勺"}:
        volume = 5 if match[2] == "茶匙" else 15
        grams = count * volume * DENSITY.get(name, 1)
        return grams, [f"{name}：按每{match[2]} {volume} 毫升及参考密度估算"]
    portion = PORTIONS.get(name)
    if portion and portion[0] == match[2]:
        return count * portion[1], [f"{name}：按每{match[2]}约 {portion[1]} 克可食部分估算"]
    return None, []


def estimate(recipe):
    totals = {"kcal": 0.0, "protein": 0.0, "carbs": 0.0, "fat": 0.0}
    items, warnings, known = [], [], 0
    for material in recipe["materials"]:
        name = material["name"]
        food = FOODS.get(name)
        grams, assumptions = ingredient_weight(material)
        override = material.get("kcal_per100g")
        row = {
            "name": name,
            "grams": round(grams, 1) if grams is not None else None,
            "kcal": None,
            "source_url": food["source_url"] if food else None,
            "assumptions": assumptions,
        }
        if name in {"盐", "水"}:
            row["kcal"] = 0.0
            known += 1
        elif grams is None or (food is None and override is None):
            warnings.append(f"{name}：" + ("缺少可换算的克重" if grams is None else "暂无匹配营养数据"))
        else:
            energy = override if override is not None else food["kcal"]
            row["kcal"] = round(energy * grams / 100, 1)
            totals["kcal"] += energy * grams / 100
            if override is None:
                for nutrient in ["protein", "carbs", "fat"]:
                    totals[nutrient] += food[nutrient] * grams / 100
            else:
                row["source_url"] = None
                assumptions.append(f"{name}：使用你填写的标签热量；未据此推断宏量营养")
            if food and food.get("approximation") and override is None:
                assumptions.append(f"{name}：{food['approximation']}")
            known += 1
        warnings.extend(assumptions)
        items.append(row)
    if not items:
        warnings.append("食材表尚未填写，无法核算热量")
    servings = recipe.get("servings", 2)
    complete = bool(items) and known == len(items)
    return {
        "total": {k: round(v, 1) for k, v in totals.items()},
        "per_serving": {k: round(v / servings, 1) for k, v in totals.items()},
        "servings": servings,
        "complete": complete,
        "macros_complete": complete
        and not any(m.get("kcal_per100g") is not None for m in recipe["materials"]),
        "coverage": round(known / len(items), 2) if items else 0,
        "estimated": True,
        "items": items,
        "warnings": list(dict.fromkeys(warnings)),
        "label": "参考估算" if complete else "已知部分小计，未计完整",
        "source": REFERENCE["source"],
        "source_url": REFERENCE["source_url"],
    }


def snapshot(recipe, servings_eaten):
    if servings_eaten is None:
        return None
    nutrition = estimate(recipe)
    if nutrition["coverage"] == 0:
        return None
    return {
        "consumed": {k: round(v * servings_eaten, 1) for k, v in nutrition["per_serving"].items()},
        "servings_eaten": servings_eaten,
        "complete": nutrition["complete"],
        "macros_complete": nutrition["macros_complete"],
        "warnings": nutrition["warnings"],
        "source": nutrition["source"],
        "recipe_servings": recipe.get("servings", 2),
    }


def recent_summary(store, days=14):
    today = date.today()
    recipes = {r["id"]: r for r in store.recipes()}
    history = [
        h
        for h in store.records("history")
        if str(today - timedelta(days=days - 1)) <= h["cooked_on"] <= str(today)
    ]
    entries = []
    for h in history:
        r = recipes[h["recipe_id"]]
        nutrition = h.get("nutrition_snapshot")
        entries.append(
            {
                **h,
                "kind": "recipe",
                "recipe_name": r["name"],
                "category": r["category"],
                "ingredients": [i["name"] for i in r["materials"]],
                "nutrition_snapshot": nutrition,
            }
        )
    for h in store.meal_logs():
        if str(today - timedelta(days=days - 1)) <= h["cooked_on"] <= str(today):
            recipe = recipes.get(h["recipe_id"])
            entries.append(
                {
                    **h,
                    "kind": "quick",
                    "recipe_name": h["name"],
                    "category": recipe["category"] if recipe else "未分类",
                    "ingredients": [i["name"] for i in recipe["materials"]] if recipe else [],
                    "rating": None,
                }
            )
    entries.sort(key=lambda h: (h["cooked_on"], h["id"]), reverse=True)
    today_entries = [h for h in entries if h["cooked_on"] == str(today)]
    consumed = {
        k: round(
            sum(
                h["nutrition_snapshot"]["consumed"].get(k, 0)
                for h in today_entries
                if h.get("nutrition_snapshot")
            ),
            1,
        )
        for k in ["kcal", "protein", "carbs", "fat"]
    }
    counted = [h for h in today_entries if h.get("nutrition_snapshot")]
    return {
        "days": days,
        "entries": entries,
        "today": {
            "totals": consumed,
            "logged_dishes": len(today_entries),
            "counted_dishes": len(counted),
            "partial": any(not h["nutrition_snapshot"]["complete"] for h in counted),
            "unquantified": len(today_entries) - len(counted),
            "target": store.settings().daily_kcal_target,
        },
        "categories": dict(Counter(h["category"] for h in entries)),
        "unique_recipes": len({dish_key(h["recipe_name"]) for h in entries}),
        "note": "只累计具有可核算食材和个人份量的记录，不代表完整一日摄入；只有菜名或用量未知的食物不猜热量。",
    }
