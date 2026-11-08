import copy
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from src.app import create_app
from src.storage.sqlite import Store


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(tmp_path / "test.db", seed=False)) as client:
        yield client


def recipe(name="番茄蛋汤", **kwargs):
    return {
        "name": name,
        "materials": [{"name": "番茄", "unit": "2个"}, {"name": "鸡蛋", "unit": "2个"}],
        "methods": ["炒番茄", "加水和蛋液煮熟"],
        "minutes": 15,
        **kwargs,
    }


def create(client, **kwargs):
    response = client.post("/api/recipes", json=recipe(**kwargs))
    assert response.status_code == 201, response.text
    return response.json()


def test_crud_search_synonyms_and_persistence(client):
    item = create(client)
    assert client.get("/api/recipes?q=西红柿%20鸡蛋").json()["total"] == 1
    assert client.get("/api/recipes?q=%27%20OR%201=1").json()["total"] == 0
    assert client.patch(f"/api/recipes/{item['id']}/favorite", json={"favorite": True}).status_code == 200
    assert client.get("/api/recipes?favorite=true").json()["total"] == 1
    response = client.put(
        f"/api/recipes/{item['id']}", json=recipe(name="改过的菜", materials=[{"name": "豆腐"}])
    )
    assert response.status_code == 200
    fresh = Store(client.app.state.store.path)
    assert fresh.recipe(item["id"])["name"] == "改过的菜"
    with fresh.connection() as db:
        assert [r[0] for r in db.execute("SELECT name FROM ingredients")] == ["豆腐"]
    assert client.delete(f"/api/recipes/{item['id']}").status_code == 204
    assert client.get(f"/api/recipes/{item['id']}").status_code == 404


def test_history_fourteen_day_boundary_and_settings(client):
    first = create(client)
    second = create(client, name="第二道菜")
    third = create(client, name="第三道菜")
    for item, days in [(first, 13), (second, 14), (third, 0)]:
        assert (
            client.post(
                "/api/history",
                json={"recipe_id": item["id"], "cooked_on": str(date.today() - timedelta(days=days))},
            ).status_code
            == 201
        )
    assert len(client.get("/api/history").json()) == 2
    assert [r["id"] for r in client.get("/api/recommendations").json()["items"]] == [second["id"]]
    assert client.put("/api/settings", json={"avoid_days": 0}).status_code == 200
    assert len(client.get("/api/recommendations").json()["items"]) == 3
    assert (
        client.post(
            "/api/history",
            json={"recipe_id": first["id"], "cooked_on": str(date.today() + timedelta(days=1))},
        ).status_code
        == 422
    )


def test_exclusions_duration_ingredient_filter_and_random_never_bypass(client):
    create(client)
    tofu = create(client, name="豆腐汤", materials=[{"name": "豆腐"}], minutes=20)
    create(client, name="慢炖", minutes=100)
    client.put("/api/settings", json={"excluded_ingredients": ["西红柿"], "max_minutes": 30})
    for mode in ["smart", "random"]:
        result = client.get("/api/recommendations", params={"mode": mode}).json()
        assert [r["id"] for r in result["items"]] == [tofu["id"]]
    assert not client.get("/api/recommendations?ingredients=虾").json()["items"]
    assert client.get("/api/recommendations?ingredients=豆腐").json()["items"][0]["id"] == tofu["id"]


def test_feedback_season_temperature_and_pantry_influence(client):
    other = create(client)
    favorite = create(client, name="清爽拌菜", tags=["清爽"], seasons=["夏"])
    client.post(
        "/api/history",
        json={"recipe_id": favorite["id"], "rating": 5, "cooked_on": str(date.today() - timedelta(days=20))},
    )
    client.put("/api/settings", json={"pantry": ["番茄"]})
    data = client.get("/api/recommendations?season=夏&temperature=30").json()["items"]
    assert data[0]["id"] == favorite["id"]
    assert data[0]["score"] > next(r["score"] for r in data if r["id"] == other["id"])
    assert any("评价" in reason for reason in data[0]["reasons"])
    history = client.get("/api/history?days=100").json()[0]
    assert (
        client.put(
            f"/api/history/{history['id']}",
            json={"recipe_id": favorite["id"], "rating": 1, "cooked_on": history["cooked_on"]},
        ).status_code
        == 200
    )
    assert client.get("/api/history?days=100").json()[0]["rating"] == 1


def test_plan_dedup_shopping_quantities_and_cascade(client):
    item = create(client)
    plan = {"recipe_id": item["id"], "planned_on": str(date.today()), "meal": "晚餐"}
    first = client.post("/api/plans", json=plan).json()
    assert client.post("/api/plans", json=plan).json()["id"] == first["id"]
    client.post("/api/plans", json={**plan, "meal": "午餐"})
    client.put("/api/settings", json={"pantry": ["西红柿"]})
    shopping = client.get("/api/shopping").json()
    tomatoes = next(i for i in shopping if i["name"] == "番茄")
    assert tomatoes["in_pantry"] is True
    assert len(tomatoes["uses"]) == 2
    assert [u["amount"] for u in tomatoes["uses"]] == ["2个", "2个"]
    client.post("/api/history", json={"recipe_id": item["id"]})
    assert client.delete(f"/api/recipes/{item['id']}").status_code == 204
    assert client.get("/api/history").json() == []
    assert client.get("/api/plans").json() == []


def test_backup_roundtrip_and_atomic_rollback(client):
    item = create(client)
    client.post("/api/history", json={"recipe_id": item["id"], "rating": 4, "note": "少放盐"})
    client.post("/api/plans", json={"recipe_id": item["id"], "planned_on": str(date.today())})
    original = client.get("/api/backup").json()
    create(client, name="额外菜谱")
    assert client.post("/api/restore", json=original).status_code == 200
    assert client.get("/api/backup").json() == original
    broken = copy.deepcopy(original)
    broken["history"][0]["recipe_id"] = 987654
    assert client.post("/api/restore", json=broken).status_code == 409
    assert client.get("/api/backup").json() == original
    duplicate = copy.deepcopy(original)
    duplicate["recipes"].append(duplicate["recipes"][0])
    assert client.post("/api/restore", json=duplicate).status_code == 422
    assert client.get("/api/backup").json() == original


def test_validation_origin_and_bounds(client):
    assert client.post("/api/recipes", json=recipe(name=" ")).status_code == 422
    assert client.post("/api/recipes", json=recipe(source_url="javascript:alert(1)")).status_code == 422
    assert client.get("/api/recommendations?temperature=nan").status_code == 422
    assert client.get("/api/recipes?limit=100000").status_code == 422
    assert client.post("/api/history", json={"recipe_id": 999}).status_code == 404
    assert (
        client.post("/api/recipes", json=recipe(), headers={"origin": "https://evil.example"}).status_code
        == 403
    )
    assert client.get("/").headers["content-security-policy"].startswith("default-src 'self'")
    assert client.get("/api/health").json()["storage"] == "sqlite"


def test_seed_only_once_after_deleting_everything(tmp_path):
    path = tmp_path / "seed.db"
    with TestClient(create_app(path)) as c:
        recipes = c.get("/api/recipes").json()["items"]
        assert len(recipes) == 16
        for r in recipes:
            c.delete(f"/api/recipes/{r['id']}")
    with TestClient(create_app(path)) as c:
        assert c.get("/api/recipes").json()["total"] == 0


def test_preview_does_not_save_and_import_is_idempotent(client, monkeypatch):
    monkeypatch.setattr("src.app.recipe_extractor", lambda source: recipe(xcf_id=source))
    assert client.post("/api/import/xiachufang/preview", json={"source": "123"}).status_code == 200
    assert client.get("/api/recipes").json()["total"] == 0
    first = client.post("/api/import/xiachufang", json={"source": "123"}).json()
    second = client.post("/api/import/xiachufang", json={"source": "123"}).json()
    assert first["created"] is True and second["created"] is False
    assert first["recipe"]["id"] == second["recipe"]["id"]
    assert client.post("/api/import/xiachufang", json={"source": "http://127.0.0.1/"}).status_code == 422


def test_related_ingredients(client):
    a = create(client)
    b = create(client, name="另一个番茄菜")
    create(client, name="无关", materials=[{"name": "土豆"}])
    assert client.get(f"/api/recipes/{a['id']}").json()["related"][0]["id"] == b["id"]


def test_season_calendar():
    from src.recommendation.recommend import season_on

    assert [season_on(date(2026, m, 1)) for m in [1, 3, 6, 9, 12]] == ["冬", "春", "夏", "秋", "冬"]


def test_request_size_bounds_include_streamed_bodies(client):
    response = client.post(
        "/api/restore",
        content=iter([b" " * 5_100_000, b" " * 5_100_000]),
        headers={"content-type": "application/json"},
    )
    assert response.status_code == 413
    assert client.get("/api/recipes/999999999999999999999999").status_code == 422
    assert client.get("/api/plans?start=9999-12-31").status_code == 422
    assert client.get("/docs").status_code == 200
    assert "/static/api.js" in client.get("/docs").text
