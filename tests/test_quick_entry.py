import copy
import json
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from src.app import create_app
from src.collection.web_recipes import (
    RecipeFinder,
    checked_url,
    parse_narration,
    parse_public_recipe,
    source_identity,
)


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("HEALTHRECIPE_LLM_PROVIDER", "local")
    with TestClient(create_app(tmp_path / "test.db", seed=False)) as c:
        yield c


def recipe(client, name="番茄炒鸡蛋"):
    return client.post(
        "/api/recipes",
        json={
            "name": name,
            "materials": [{"name": "鸡蛋", "grams": 100}],
            "methods": ["炒熟"],
            "servings": 2,
        },
    ).json()


def meal(client, names, request_id="quick-meal-001"):
    return client.post(
        "/api/food-log",
        json={
            "dishes": [{"name": n} for n in names],
            "request_id": request_id,
            "meal": "午餐",
            "cooked_on": str(date.today()),
        },
    )


def test_name_only_multi_dish_meal_needs_no_recipe_or_method(client):
    response = meal(client, ["外卖牛肉饭", "食堂青菜", "酸奶"])
    assert response.status_code == 201, response.text
    assert client.get("/api/recipes").json()["total"] == 0
    summary = client.get("/api/food-log").json()
    assert len(summary["entries"]) == 3
    assert summary["today"]["counted_dishes"] == 0
    assert summary["today"]["unquantified"] == 3
    assert all(r["nutrition_snapshot"] is None for r in summary["entries"])
    assert client.get("/api/nutrition/summary").json()["unique_recipes"] == 3


def test_repeat_save_and_edit_delete_do_not_duplicate_or_lose_other_dishes(client):
    first = meal(client, ["面条", "酸奶"]).json()["items"]
    assert meal(client, ["面条", "酸奶"]).json()["items"] == first
    assert meal(client, ["面条", "米饭"]).status_code == 409
    changed = client.put(
        "/api/food-log/" + str(first[0]["id"]),
        json={
            "name": "牛肉面",
            "servings_eaten": 0.5,
            "cooked_on": str(date.today()),
            "meal": "晚餐",
            "note": "味道不错",
        },
    )
    assert changed.status_code == 200, changed.text
    assert changed.json()["nutrition_snapshot"] is None
    assert client.delete("/api/food-log/" + str(first[0]["id"])).status_code == 204
    assert [i["recipe_name"] for i in client.get("/api/food-log").json()["entries"]] == ["酸奶"]


def test_exact_alias_links_nutrition_and_recent_random_exclusion(client):
    r = recipe(client)
    entry = meal(client, ["番茄炒蛋"]).json()["items"][0]
    assert entry["recipe_id"] == r["id"]
    assert entry["nutrition_snapshot"]["consumed"]["kcal"] == 71.5
    assert not client.get("/api/recommendations?mode=random").json()["items"]
    client.delete("/api/recipes/" + str(r["id"]))
    # Free food logs outlive deleting their source recipe, along with the historical snapshot.
    preserved = client.get("/api/food-log").json()["entries"][0]
    assert preserved["recipe_id"] is None and preserved["recipe_name"] == "番茄炒蛋"
    assert preserved["nutrition_snapshot"]["consumed"]["kcal"] == 71.5
    assert meal(client, ["番茄炒蛋"]).json()["items"][0]["id"] == entry["id"]


def test_unlinked_names_still_exclude_a_recipe_added_later_and_future_is_rejected(client):
    meal(client, ["番茄炒蛋"])
    recipe(client)
    assert client.get("/api/recommendations?mode=random").json()["items"] == []
    assert (
        client.post(
            "/api/food-log",
            json={
                "dishes": [{"name": "米饭"}],
                "request_id": "future-001",
                "cooked_on": str(date.today() + timedelta(days=1)),
            },
        ).status_code
        == 422
    )


def test_narration_is_preserved_without_inventing_ingredients(client):
    text = "先把番茄切块。鸡蛋炒好盛出。番茄出汁以后倒回鸡蛋。"
    result = client.post("/api/capture/preview", json={"name": "家里的番茄蛋", "narration": text}).json()
    assert result["status"] == "ready"
    assert result["recipe"]["materials"] == []
    assert result["recipe"]["original_text"] == text
    assert result["recipe"]["methods"] == ["先把番茄切块", "鸡蛋炒好盛出", "番茄出汁以后倒回鸡蛋"]
    saved = client.post("/api/capture/save", json={"recipe": result["recipe"]})
    assert saved.status_code == 201, saved.text
    details = client.get("/api/recipes/" + str(saved.json()["recipe"]["id"])).json()
    assert details["nutrition"]["complete"] is False and details["nutrition"]["coverage"] == 0


def test_name_only_search_does_not_generate_a_method_or_write_a_recipe(client, monkeypatch):
    calls = []
    monkeypatch.setattr(
        client.app.state.finder,
        "search",
        lambda name, sources: (
            calls.append(name) or {"query": name, "items": [], "sources": [], "warnings": []}
        ),
    )
    result = client.post("/api/capture/preview", json={"name": "不会做的新菜"}).json()
    assert result["status"] == "search" and calls == ["不会做的新菜"]
    assert client.get("/api/recipes").json()["total"] == 0


def test_drafts_and_free_logs_roundtrip_and_publish_is_deduplicated(client):
    draft = client.post("/api/capture/drafts", json={"name": "想吃的红烧肉"}).json()
    meal(client, ["米饭"])
    original = client.get("/api/backup").json()
    assert original["version"] == 3 and original["drafts"] and original["meal_logs"]
    assert client.post("/api/restore", json=original).status_code == 200
    assert client.get("/api/backup").json() == original
    bad = copy.deepcopy(original)
    bad["meal_logs"][0]["recipe_id"] = 9999
    assert client.post("/api/restore", json=bad).status_code == 409
    assert client.get("/api/backup").json() == original
    r = parse_narration("红烧肉", "先焯水，再炖熟。").model_dump()
    r["source_url"] = "https://www.douguo.com/cookbook/123.html"
    one = client.post("/api/capture/save", json={"recipe": r, "draft_id": draft["id"]}).json()
    r["source_url"] = "https://m.douguo.com/recipe/amp/123"
    two = client.post("/api/capture/save", json={"recipe": r}).json()
    assert one["created"] and not two["created"]
    assert one["recipe"]["id"] == two["recipe"]["id"]
    assert client.get("/api/capture/drafts").json() == []


def test_legacy_backups_without_new_data_restore(client):
    recipe(client)
    original = client.get("/api/backup").json()
    original.pop("meal_logs")
    original.pop("drafts")
    original["version"] = 2
    meal(client, ["外卖饭"])
    assert client.post("/api/restore", json=original).status_code == 200
    assert client.get("/api/food-log").json()["entries"] == []


@pytest.mark.parametrize(
    "url",
    [
        "http://localhost/recipe/1",
        "https://www.xiachufang.com@evil.example/recipe/1/",
        "https://www.xiachufang.com:9999/recipe/1/",
        "file:///etc/passwd",
        "https://evil.example/a",
    ],
)
def test_import_urls_are_restricted(url):
    with pytest.raises(ValueError):
        checked_url(url)


def test_share_url_extraction_and_equivalent_identities():
    url, source = checked_url("这道菜真好吃，复制链接打开 http://xhslink.com/a/hello 。")
    assert url == "https://xhslink.com/a/hello" and source == "xiaohongshu"
    assert source_identity("https://m.xiachufang.com/recipe/123/") == source_identity(
        "https://www.xiachufang.com/recipe/123/"
    )


def test_structured_recipe_and_visible_chinese_site_steps():
    ld = {
        "@graph": [
            {
                "@type": ["Recipe"],
                "name": "真实原菜名",
                "recipeIngredient": ["番茄 2个"],
                "author": {"name": "原作者"},
                "recipeInstructions": [
                    {"@type": "HowToSection", "itemListElement": [{"text": "先切块"}, {"text": "再煮熟"}]}
                ],
            }
        ]
    }
    result = parse_public_recipe(
        '<script type="application/ld+json">' + json.dumps(ld) + "</script>",
        "https://thewoksoflife.com/example/",
    )
    assert result["status"] == "ready" and result["recipe"]["methods"] == ["先切块", "再煮熟"]
    assert result["recipe"]["author"] == "原作者"
    html = '<h1>番茄炒蛋</h1><ul class="recipeCategory_sub_R"><li><span class="category_s1">鸡蛋</span><span class="category_s2">两个</span></li></ul><div class="recipeStep_word"><span class="recipeStep_num">1</span>先炒熟</div>'
    result = parse_public_recipe(html, "https://home.meishichina.com/recipe-123.html")
    assert result["recipe"]["methods"] == ["先炒熟"]
    assert result["recipe"]["materials"][0]["unit"] == "两个"


def test_xhs_public_note_only_and_missing_steps_remain_partial():
    note = {
        "note": {
            "noteDetailMap": {
                "abc": {
                    "note": {
                        "title": "家里的汤",
                        "desc": "做法：先洗菜。再煮熟。",
                        "user": {"nickname": "原作者"},
                    }
                }
            }
        }
    }
    result = parse_public_recipe(
        "<script>window.__INITIAL_STATE__=" + json.dumps(note) + ";</script>",
        "https://www.xiaohongshu.com/explore/abc",
    )
    assert result["status"] == "ready" and result["recipe"]["author"] == "原作者"
    assert result["recipe"]["methods"] == ["先洗菜", "再煮熟"]
    partial = parse_public_recipe(
        "<h1>滑动验证</h1>请先登录", "https://www.xiachufang.com/recipe/123/", "想做的菜"
    )
    assert partial["status"] == "partial" and "recipe" not in partial
    assert partial["name"] == "想做的菜"
    assert (
        parse_public_recipe(
            "<script>window.__INITIAL_STATE__=[];</script>", "https://www.xiaohongshu.com/explore/abc"
        )["status"]
        == "partial"
    )


class FakeResponse:
    def __init__(self, status=200, body=b"", headers=None):
        self.status_code = status
        self.content = body
        self.headers = headers or {}

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def iter_content(self, size):
        yield self.content

    def json(self):
        return json.loads(self.content)


def test_redirects_and_blocked_pages_do_not_bypass_login(monkeypatch):
    finder = RecipeFinder()
    monkeypatch.setattr(
        finder, "_get", lambda *args: FakeResponse(302, headers={"Location": "http://127.0.0.1/admin"})
    )
    with pytest.raises(ValueError):
        finder.fetch("https://xhslink.com/a/abc")
    monkeypatch.setattr(finder, "_get", lambda *args: FakeResponse(403))
    result = finder.fetch("https://www.douguo.com/cookbook/123.html", "菜名")
    assert result["status"] == "blocked" and "recipe" not in result


def test_search_filters_irrelevant_results_and_caches(monkeypatch):
    finder = RecipeFinder()
    calls = []
    xml = b"<rss><channel><item><title>\xe7\xba\xa2\xe7\x83\xa7\xe8\x82\x89</title><link>https://www.douguo.com/cookbook/123.html</link></item><item><title>Novel</title><link>https://evil.example/</link></item></channel></rss>"

    def get(url, params=None):
        calls.append(url)
        return FakeResponse(body=xml)

    monkeypatch.setattr(finder, "_get", get)
    first = finder.search("红烧肉", ["douguo"])
    assert len(first["items"]) == 1
    assert finder.search("红烧肉", ["douguo"]) == first and len(calls) == 1


def test_imported_english_ingredients_respect_existing_allergies(client):
    client.post(
        "/api/recipes",
        json={
            "name": "Shrimp with broccoli",
            "materials": [{"name": "large shrimp", "unit": "1 cup"}],
            "methods": ["Cook thoroughly"],
        },
    )
    client.put("/api/settings", json={"excluded_ingredients": ["虾"]})
    assert client.get("/api/recommendations?mode=random").json()["items"] == []


def test_same_draft_save_is_idempotent_and_updates_do_not_duplicate(client):
    one = client.post("/api/capture/drafts", json={"name": "以后做的菜"}).json()
    two = client.post("/api/capture/drafts", json={"name": "以后做的菜"}).json()
    assert one["id"] == two["id"]
    response = client.put(
        "/api/capture/drafts/" + str(one["id"]), json={"name": "改了名字的菜", "narration": "待补充"}
    )
    assert response.status_code == 200
    assert len(client.get("/api/capture/drafts").json()) == 1


def test_search_relevance_rejects_soup_for_stir_fry():
    from src.collection.web_recipes import relevant

    assert relevant("番茄炒蛋", "Chinese Tomato Egg Stir-fry")
    assert not relevant("番茄炒蛋", "Tomato Egg Drop Soup")
    assert not relevant("番茄炒蛋", "Pasta Alla Norma with Roasted Eggplant & Tomatoes")


def test_recipe_with_only_instructions_is_not_counted_as_zero_calorie_food(client):
    r = client.post("/api/recipes", json={"name": "只知道做法", "methods": ["按自己的口述做熟"]}).json()
    h = client.post("/api/history", json={"recipe_id": r["id"], "servings_eaten": 1}).json()
    assert h["nutrition_snapshot"] is None
    q = meal(client, ["只知道做法"]).json()["items"][0]
    assert q["nutrition_snapshot"] is None
    summary = client.get("/api/nutrition/summary").json()["today"]
    assert summary["counted_dishes"] == 0 and summary["unquantified"] == 2
    updated = {k: v for k, v in r.items() if k != "id"}
    updated["materials"] = [{"name": "鸡蛋", "grams": 100}]
    client.put("/api/recipes/" + str(r["id"]), json=updated)
    # A note/rating edit does not turn an originally unknown meal into guessed historical intake.
    client.put("/api/history/" + str(h["id"]), json={"recipe_id": r["id"], "servings_eaten": 1, "rating": 5})
    assert client.get("/api/history").json()[0]["nutrition_snapshot"] is None
