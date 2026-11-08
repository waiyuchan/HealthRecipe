"""Name-only food records stay independent from the recipe collection."""

import re
import unicodedata


def dish_key(name):
    value = unicodedata.normalize("NFKC", name).lower()
    for old, new in [
        ("西红柿", "番茄"),
        ("鸡蛋", "蛋"),
        ("淮山", "山药"),
        ("马铃薯", "土豆"),
        ("西兰花", "西蓝花"),
    ]:
        value = value.replace(old, new)
    return re.sub(r"[\s·・,，。\-_/（）()]", "", value)


def dish_keys(name):
    aliases = [dish_key(name)]
    for chunk in re.findall(r"[（(]([^）)]+)[）)]", name):
        if re.search(r"[\u4e00-\u9fff]", chunk):
            aliases.append(dish_key(chunk))
    return set(aliases)


def resolve_dish(store, dish):
    recipes = store.recipes()
    if dish.recipe_id:
        recipe = next((r for r in recipes if r["id"] == dish.recipe_id), None)
        if not recipe or not (dish_keys(recipe["name"]) & dish_keys(dish.name)):
            raise ValueError("菜名与所选菜谱不一致，请重新选择")
    else:
        recipe = next((r for r in recipes if dish_keys(r["name"]) & dish_keys(dish.name)), None)
    return dish.model_copy(update={"recipe_id": recipe["id"] if recipe else None})
