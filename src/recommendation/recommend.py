"""Content-based ranking: no model downloads or fabricated nutrition scores."""

import random
import re
from datetime import date, timedelta

from src.food_entry import dish_key, dish_keys
from src.memory import explicit_exclusions
from src.nutrition import estimate


def season_on(day, latitude=None):
    index = (day.month % 12) // 3
    if latitude is not None and latitude < 0:
        index = (index + 2) % 4
    return ("冬", "春", "夏", "秋")[index]


# Common kitchen synonyms; exclusions are ingredient matching, not allergy certification.
ALIASES = {"番茄": "西红柿", "淮山": "山药", "马铃薯": "土豆", "西兰花": "西蓝花"}


def normalize(value):
    value = value.strip().lower()
    english = {
        "shrimp": "虾",
        "prawns": "虾",
        "prawn": "虾",
        "crab": "蟹",
        "fish": "鱼",
        "scallops": "扇贝",
        "milk": "牛奶",
        "butter": "黄油",
        "cream": "奶油",
        "cheese": "奶酪",
        "peanuts": "花生",
        "peanut": "花生",
        "eggs": "鸡蛋",
        "egg": "鸡蛋",
        "tofu": "豆腐",
        "soy sauce": "酱油",
        "tomatoes": "西红柿",
        "tomato": "西红柿",
        "broccoli": "西蓝花",
    }
    for original, alias in english.items():
        value = re.sub(r"\b" + re.escape(original) + r"\b", alias, value)
    for original, alias in ALIASES.items():
        value = value.replace(original, alias)
    return value


FOOD_GROUPS = {
    "海鲜": ["虾", "蟹", "鱼", "贝", "蚝", "蛤", "蛏", "鱿鱼", "章鱼"],
    "坚果": ["花生", "核桃", "杏仁", "腰果", "榛子", "开心果", "碧根果", "松子", "巴旦木", "夏威夷果"],
    "奶制品": ["牛奶", "酸奶", "奶酪", "黄油", "奶油", "乳", "奶粉"],
    "乳制品": ["牛奶", "酸奶", "奶酪", "黄油", "奶油", "乳", "奶粉"],
    "大豆": ["豆腐", "豆浆", "香干", "生抽", "酱油", "豆皮", "腐竹", "味噌"],
    "豆制品": ["豆腐", "豆浆", "香干", "生抽", "酱油", "豆皮", "腐竹", "味噌"],
    "蛋": ["鸡蛋", "鸭蛋", "鹌鹑蛋", "蛋白", "蛋黄", "蛋液"],
}


def matches(term, ingredient):
    normalized = normalize(ingredient)
    return any(normalize(value) in normalized for value in FOOD_GROUPS.get(term, [term]))


class Recommendation:
    def __init__(self, store):
        self.store = store

    def recommend(
        self,
        *,
        limit=6,
        ingredients=None,
        season=None,
        temperature=None,
        mode="smart",
        today=None,
        extra_excluded=None,
    ):
        today = today or date.today()
        settings = self.store.settings()
        season = season or season_on(today, settings.location.latitude if settings.location else None)
        excluded = list(settings.excluded_ingredients) + list(extra_excluded or [])
        if settings.memory_enabled:
            excluded += explicit_exclusions(self.store.memories())
        history = self.store.records("history")
        cutoff = today - timedelta(days=settings.avoid_days - 1)
        recent = {
            h["recipe_id"]
            for h in history
            if settings.avoid_days and cutoff <= date.fromisoformat(h["cooked_on"]) <= today
        }
        recent_names = {
            dish_key(h["name"])
            for h in self.store.meal_logs()
            if settings.avoid_days and cutoff <= date.fromisoformat(h["cooked_on"]) <= today
        }
        ratings = {}
        for h in history:
            if h["rating"] is not None:
                ratings.setdefault(h["recipe_id"], []).append(h["rating"])
        desired = ingredients or settings.pantry
        result = []
        for recipe in self.store.recipes():
            names = [m["name"] for m in recipe["materials"]]
            if (
                recipe["id"] in recent
                or bool(dish_keys(recipe["name"]) & recent_names)
                or recipe["minutes"] > settings.max_minutes
            ):
                continue
            if (excluded and not names) or any(matches(term, name) for term in excluded for name in names):
                continue
            hit = [term for term in desired if any(matches(term, name) for name in names)]
            if ingredients and not hit:
                continue
            score, reasons = 0, []
            if hit:
                score += round(40 * len(hit) / len(desired))
                reasons.append("用上现有食材：" + "、".join(hit))
            if season in recipe["seasons"]:
                score += 15
                reasons.append(f"适合{season}季的家常搭配")
            if recipe["favorite"]:
                score += 8
                reasons.append("你收藏的菜谱")
            feedback = ratings.get(recipe["id"], [])
            if feedback:
                avg = sum(feedback) / len(feedback)
                score += round((avg - 3) * 8)
                if avg >= 4:
                    reasons.append(f"以往评价 {avg:.1f} 分")
            if temperature is not None:
                if temperature >= 28 and any(t in recipe["tags"] for t in ["清爽", "凉拌"]):
                    score += 12
                    reasons.append("天气较热，试试清爽口味")
                elif temperature <= 12 and recipe["category"] in ("汤羹", "炖菜"):
                    score += 12
                    reasons.append("天气较凉，来一道热汤炖菜")
            if recipe["minutes"] <= 20:
                score += 5
                reasons.append("20 分钟内上桌")
            result.append(
                {
                    **recipe,
                    "nutrition": estimate(recipe),
                    "score": score,
                    "reasons": reasons or ["换一道家常菜，丰富餐桌"],
                }
            )
        if mode == "random":
            random.SystemRandom().shuffle(result)
            for recipe in result:
                recipe["reasons"] = ["随机选菜，已应用忌口、用时与近期去重条件"]
        else:
            result.sort(key=lambda r: (-r["score"], r["id"]))
        return {
            "items": result[:limit],
            "eligible": len(result),
            "season": season,
            "avoid_days": settings.avoid_days,
        }

    def rec_by_random(self, limit=6):
        return self.recommend(limit=limit, mode="random")["items"]
