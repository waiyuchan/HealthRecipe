import json
from pathlib import Path

import pytest

from src.collection.recipe_category_extractor import extract_categories
from src.collection.recipe_extractor import parse_recipe, recipe_id_from_input


def test_html_and_structured_parsers():
    html = '<h1 class="page-title"> 家常菜 </h1><table class="ings"><tr><td class="name">豆腐</td><td class="unit">一盒</td></tr></table><div class="steps"><li><p class="text">煮熟即可</p></li></div>'
    result = parse_recipe(html, "123")
    assert result["name"] == "家常菜"
    assert result["materials"] == [{"name": "豆腐", "unit": "一盒"}]
    assert result["methods"] == ["煮熟即可"]
    structured = {
        "@graph": [
            {
                "@type": ["Recipe"],
                "name": "蛋羹",
                "recipeIngredient": ["鸡蛋2个"],
                "recipeInstructions": [{"@type": "HowToSection", "itemListElement": [{"text": "蒸熟"}]}],
            }
        ]
    }
    parsed = parse_recipe('<script type="application/ld+json">' + json.dumps(structured) + "</script>", "456")
    assert parsed["name"] == "蛋羹" and parsed["methods"] == ["蒸熟"]
    with pytest.raises(ValueError, match="未包含完整菜谱"):
        parse_recipe("<h1>请登录</h1>", "123")


@pytest.mark.parametrize(
    "value",
    [
        "file:///etc/passwd",
        "https://evil.test/recipe/1/",
        "https://www.xiachufang.com@evil.test/recipe/1/",
        "../1",
        "https://www.xiachufang.com:443/recipe/1/",
    ],
)
def test_import_source_is_restricted(value):
    with pytest.raises(ValueError):
        recipe_id_from_input(value)


def test_category_snapshot_keeps_all_items():
    root = Path(__file__).resolve().parents[1]
    result = extract_categories((root / "data/category.html").read_text())
    assert len(result["热门专题"]["菜式"]["items"]) == 8
    count = sum(len(section["items"]) for group in result.values() for section in group.values())
    assert count > 300
    assert result == json.loads((root / "data/category.json").read_text())
