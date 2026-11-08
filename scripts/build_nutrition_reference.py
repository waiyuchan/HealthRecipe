"""Build the small offline reference from the official USDA SR Legacy CSV ZIP.

Usage: python scripts/build_nutrition_reference.py /path/to/usda-sr-legacy.zip
The original archive is not bundled. Exact food IDs and original descriptions remain auditable.
"""

import csv
import io
import json
import sys
import zipfile
from pathlib import Path

# Chinese kitchen names map to specified generic food types, never to branded products.
FOODS = [
    ("香油", 171016, [], None),
    ("熟米饭", 168878, [], "使用熟白米饭数据，不适用于干米"),
    ("土豆", 170026, ["马铃薯"], None),
    ("番茄", 170457, ["西红柿"], None),
    ("鸡蛋", 171287, [], None),
    ("老豆腐", 172475, ["豆腐"], None),
    ("嫩豆腐", 172476, [], "以普通豆腐近似，嫩豆腐品牌含水量不同"),
    ("香干", 172475, [], "以硬豆腐近似，香干应优先使用包装热量"),
    ("香菇", 169242, [], None),
    ("西兰花", 170379, ["西蓝花"], None),
    ("虾仁", 175179, ["虾"], None),
    ("鸡胸肉", 171077, [], None),
    ("鸡腿肉", 173627, [], None),
    ("南瓜", 168448, [], None),
    ("小米", 169702, [], None),
    ("黄瓜", 168409, [], None),
    ("干木耳", 168581, [], None),
    ("白萝卜", 168451, [], None),
    ("菠菜", 168462, [], None),
    ("面条", 169755, [], "以干蛋面近似，鲜面需确认包装营养与含水量"),
    ("芹菜", 169988, [], None),
    ("玉米", 169998, [], None),
    ("胡萝卜", 170393, [], None),
    ("红薯", 168482, [], None),
    ("即食燕麦", 169705, ["燕麦"], "以干燕麦近似"),
    ("牛奶", 171265, [], "按全脂牛奶计算，具体品牌以包装为准"),
    ("彩椒", 170108, ["红椒", "甜椒"], "以生红甜椒近似混合彩椒"),
    ("大蒜", 169230, [], None),
    ("生姜", 169231, ["姜"], None),
    ("小葱", 170005, ["葱"], None),
    ("食用油", 171411, ["植物油"], "按大豆烹调油计算，全量计入，未扣除锅中余油"),
    ("生抽", 174277, ["酱油", "蒸鱼豉油"], "以普通酱油近似，具体品牌以包装为准"),
    ("莲藕", 169250, [], None),
    ("荷兰豆", 170010, [], None),
    ("鲈鱼", 175142, [], "以生海鲈鱼近似"),
    ("排骨", 167853, [], None),
    ("牛腩", 168664, [], None),
    ("香醋", 172237, ["醋"], "以蒸馏醋近似，调味醋含糖量可能不同"),
    ("盐", 173468, [], None),
    ("水", 173647, [], None),
    ("淀粉", 169698, [], None),
]


def build(path):
    archive = zipfile.ZipFile(path)
    foods = {r["fdc_id"]: r for r in csv.DictReader(io.TextIOWrapper(archive.open("food.csv")))}
    wanted = {str(item[1]) for item in FOODS}
    nutrients = {}
    for row in csv.DictReader(io.TextIOWrapper(archive.open("food_nutrient.csv"))):
        if row["fdc_id"] in wanted and row["nutrient_id"] in {"1008", "1003", "1004", "1005"}:
            nutrients.setdefault(row["fdc_id"], {})[row["nutrient_id"]] = float(row["amount"])
    result = []
    for name, identifier, aliases, approximation in FOODS:
        original = foods[str(identifier)]
        n = nutrients[str(identifier)]
        result.append(
            {
                "name": name,
                "aliases": aliases,
                "fdc_id": identifier,
                "description": original["description"],
                "kcal": n["1008"],
                "protein": n.get("1003", 0),
                "fat": n.get("1004", 0),
                "carbs": n.get("1005", 0),
                "approximation": approximation,
                "source_url": f"https://fdc.nal.usda.gov/food-details/{identifier}/nutrients",
            }
        )
    target = Path(__file__).resolve().parents[1] / "data/nutrition.json"
    target.write_text(
        json.dumps(
            {
                "source": "USDA FoodData Central SR Legacy (2018)",
                "source_url": "https://fdc.nal.usda.gov/download-datasets/",
                "basis": "per 100 g edible portion; preparation state follows each original description",
                "foods": result,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    print(f"Wrote {len(result)} foods to {target}")


if __name__ == "__main__":
    build(sys.argv[1])
