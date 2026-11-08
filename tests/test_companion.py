import copy
import sqlite3
import time
from datetime import date, timedelta

import pytest
import requests
from fastapi.testclient import TestClient

from src.app import create_app
from src.assistant import Reply
from src.models import Location
from src.nutrition import estimate, snapshot
from src.recommendation.recommend import season_on
from src.storage.sqlite import Store
from src.weather import WeatherService


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("HEALTHRECIPE_LLM_PROVIDER", "local")
    with TestClient(create_app(tmp_path / "test.db", seed=False)) as c:
        yield c


def create(c, name="番茄炒蛋", materials=None):
    result = c.post(
        "/api/recipes",
        json={
            "name": name,
            "materials": materials
            or [
                {"name": "番茄", "grams": 200},
                {"name": "鸡蛋", "grams": 100},
                {"name": "食用油", "grams": 10},
            ],
            "methods": ["炒熟"],
            "servings": 2,
            "minutes": 15,
        },
    )
    assert result.status_code == 201, result.text
    return result.json()


def chat(c, message="帮我看看今天吃什么", request_id="test-message-001", remember=True):
    return c.post(
        "/api/assistant/chat", json={"message": message, "request_id": request_id, "remember": remember}
    )


def test_reference_calculation_includes_oil_and_portions(client):
    r = create(client)
    n = client.get(f"/api/recipes/{r['id']}").json()["nutrition"]
    assert n["total"]["kcal"] == pytest.approx(18 * 2 + 143 + 884 * 0.1)
    assert n["per_serving"]["kcal"] == pytest.approx(133.7)
    assert n["complete"] is True
    assert n["items"][0]["source_url"].endswith("/170457/nutrients")
    assert snapshot(r, 0.5)["consumed"]["kcal"] == 66.8


def test_unknown_units_and_unknown_food_never_look_complete(client):
    r = {
        "materials": [
            {"name": "神秘食材", "grams": 100},
            {"name": "食用油", "unit": "少许"},
            {"name": "番茄", "grams": 100},
        ],
        "servings": 1,
    }
    n = estimate(r)
    assert n["total"]["kcal"] == 18
    assert n["complete"] is False
    assert [i["kcal"] for i in n["items"]][:2] == [None, None]
    assert n["label"].startswith("已知部分")
    assert len(n["warnings"]) == 2


def test_spoon_assumptions_and_label_override(client):
    r = client.post(
        "/api/nutrition/estimate", json={"materials": [{"name": "食用油", "unit": "1汤匙"}]}
    ).json()
    assert r["items"][0]["grams"] == 13.8
    assert r["total"]["kcal"] == 122
    assert r["warnings"]
    r = client.post(
        "/api/nutrition/estimate",
        json={"materials": [{"name": "自有品牌", "grams": 80, "kcal_per100g": 200}]},
    ).json()
    assert r["total"]["kcal"] == 160
    assert r["macros_complete"] is False
    assert (
        client.post(
            "/api/nutrition/estimate", json={"materials": [{"name": "番茄", "grams": -1}]}
        ).status_code
        == 422
    )


def test_historical_snapshot_and_consumed_share_stay_stable(client):
    r = create(client)
    item = {"recipe_id": r["id"], "servings_eaten": 0.5, "meal": "午餐"}
    h = client.post("/api/history", json=item).json()
    assert h["nutrition_snapshot"]["consumed"]["kcal"] == 66.8
    recipe = {k: v for k, v in r.items() if k != "id"}
    recipe["materials"] = [{"name": "食用油", "grams": 100}]
    client.put(f"/api/recipes/{r['id']}", json=recipe)
    assert client.get("/api/nutrition/summary").json()["today"]["totals"]["kcal"] == 66.8
    client.put(f"/api/history/{h['id']}", json={**item, "rating": 5})
    assert client.get("/api/nutrition/summary").json()["today"]["totals"]["kcal"] == 66.8
    client.put(f"/api/history/{h['id']}", json={**item, "servings_eaten": 1})
    assert client.get("/api/nutrition/summary").json()["today"]["totals"]["kcal"] == 133.6
    client.post("/api/history", json={"recipe_id": r["id"]})
    summary = client.get("/api/nutrition/summary").json()["today"]
    assert summary["counted_dishes"] == 1 and summary["unquantified"] == 1


def test_memory_expiry_and_explicit_allergies_filter_recommendations(client):
    shrimp = create(client, name="炒虾", materials=[{"name": "虾仁", "grams": 100}])
    tofu = create(client, name="豆腐", materials=[{"name": "豆腐", "grams": 100}])
    mem = client.post("/api/memories", json={"kind": "饮食偏好", "content": "我对虾过敏"}).json()
    ids = [r["id"] for r in client.get("/api/recommendations").json()["items"]]
    assert ids == [tofu["id"]]
    client.put(
        "/api/memories/" + str(mem["id"]),
        json={
            "kind": "饮食偏好",
            "content": "我对虾过敏",
            "expires_on": str(date.today() - timedelta(days=1)),
        },
    )
    assert shrimp["id"] in [r["id"] for r in client.get("/api/recommendations").json()["items"]]
    body = client.post("/api/memories", json={"kind": "身体感受", "content": "最近想吃温热的"}).json()
    assert body["expires_on"] == str(date.today() + timedelta(days=14))


def test_chat_idempotency_local_mode_and_forgetting(client):
    r = create(client)
    client.post("/api/history", json={"recipe_id": r["id"], "servings_eaten": 1})
    response = chat(client, "记住我不吃香菜")
    assert response.status_code == 200, response.text
    first = response.json()
    assert first["payload"]["mode"] == "local"
    assert first["payload"]["warning"]
    assert len(client.get("/api/memories").json()) == 1
    assert chat(client, "记住我不吃香菜").json()["id"] == first["id"]
    assert len(client.get("/api/assistant/messages").json()) == 2
    assert chat(client, "另一条内容").status_code == 409
    memory = client.get("/api/memories").json()[0]
    client.delete("/api/memories/" + str(memory["id"]))
    assert client.get("/api/assistant/messages").json() == []
    assert len(client.get("/api/history").json()) == 1


def test_grounded_model_context_and_untrusted_memory_output(client, monkeypatch):
    a = create(client)
    b = create(client, name="豆腐", materials=[{"name": "豆腐", "grams": 100}])
    client.post("/api/history", json={"recipe_id": a["id"], "servings_eaten": 1, "rating": 4})
    client.post(
        "/api/memories",
        json={
            "kind": "身体感受",
            "content": "已过期体感",
            "expires_on": str(date.today() - timedelta(days=1)),
        },
    )
    contexts = []

    def fake(context, message):
        contexts.append(context)
        return Reply(
            reply="今天换一道豆腐，记录里的昨天不等于你完整的一日饮食。",
            recipe_ids=[b["id"], a["id"], 99999],
            memories=[
                {"kind": "身体感受", "evidence": "我最近胃有点不舒服", "days": 365},
                {"kind": "身体感受", "evidence": "已确诊胃炎", "days": 30},
            ],
            plan=[
                {"recipe_id": b["id"], "day_offset": 1, "meal": "晚餐"},
                {"recipe_id": 9999, "day_offset": 0, "meal": "晚餐"},
            ],
        )

    monkeypatch.setattr(client.app.state.assistant, "_model_reply", fake)
    result = chat(client, "我最近胃有点不舒服，想吃温热一些").json()
    assert result["payload"]["recipe_ids"] == [b["id"]]
    assert len(result["payload"]["plan"]) == 1
    memories = client.get("/api/memories").json()
    saved = next(m for m in memories if m["content"] == "我最近胃有点不舒服")
    assert saved["expires_on"] == str(date.today() + timedelta(days=14))
    assert all(m["content"] != "已确诊胃炎" for m in memories)
    assert contexts[0]["memories"] == []
    assert contexts[0]["recent_diet"]["entries"][0]["recipe_name"] == a["name"]
    assert contexts[0]["candidates"][0]["id"] == b["id"]


def test_no_memory_when_disabled_or_hypothetical(client, monkeypatch):
    create(client)

    def fake(context, message):
        return Reply(
            reply="需要先确认你的实际情况。", memories=[{"kind": "身体感受", "evidence": message, "days": 14}]
        )

    monkeypatch.setattr(client.app.state.assistant, "_model_reply", fake)
    chat(client, "如果我胃不舒服可以吃什么？")
    assert client.get("/api/memories").json() == []
    chat(client, "我想吃温热的", request_id="disabled-0001", remember=False)
    assert client.get("/api/memories").json() == []
    client.put("/api/settings", json={"memory_enabled": False})
    chat(client, "我想吃温热的", request_id="disabled-0002")
    assert client.get("/api/memories").json() == []


def test_acute_symptom_routes_to_care_not_a_menu(client, monkeypatch):
    def bad(*args):
        raise AssertionError("must not call the model")

    monkeypatch.setattr(client.app.state.assistant, "_model_reply", bad)
    result = chat(client, "我现在胸痛还呼吸困难").json()
    assert result["payload"]["mode"] == "safety"
    assert "立即就医" in result["content"]
    assert result["payload"]["recipe_ids"] == []


def test_batch_plan_is_deduplicated_and_atomic(client):
    r = create(client)
    plan = {"recipe_id": r["id"], "planned_on": str(date.today()), "meal": "晚餐"}
    assert client.post("/api/plans/batch", json={"items": [plan, plan]}).status_code == 201
    assert len(client.get("/api/plans").json()) == 1
    assert (
        client.post(
            "/api/plans/batch", json={"items": [{**plan, "meal": "午餐"}, {**plan, "recipe_id": 9999}]}
        ).status_code
        == 404
    )
    assert len(client.get("/api/plans").json()) == 1


def test_v2_backup_includes_memory_chat_and_nutrition(client):
    r = create(client)
    client.post("/api/history", json={"recipe_id": r["id"], "servings_eaten": 1})
    chat(client, "记住我不吃香菜")
    original = client.get("/api/backup").json()
    assert original["version"] == 3 and original["messages"] and original["memories"]
    client.delete("/api/assistant/messages?forget_memories=true")
    assert client.post("/api/restore", json=original).status_code == 200
    assert client.get("/api/backup").json() == original
    broken = copy.deepcopy(original)
    broken["history"][0]["nutrition_snapshot"]["consumed"] = {"bad": "data"}
    assert client.post("/api/restore", json=broken).status_code == 422
    assert client.get("/api/backup").json() == original
    legacy = {k: v for k, v in original.items() if k not in {"memories", "messages"}}
    legacy["version"] = 1
    for h in legacy["history"]:
        for k in ["nutrition_snapshot", "meal", "servings_eaten"]:
            h.pop(k, None)
    assert client.post("/api/restore", json=legacy).status_code == 200
    assert client.get("/api/memories").json() == []
    assert client.get("/api/nutrition/summary").json()["today"]["counted_dishes"] == 0


def test_migration_keeps_v1_data_and_rejects_future(tmp_path):
    path = tmp_path / "old.db"
    with sqlite3.connect(path) as db:
        db.executescript(
            'CREATE TABLE history(id INTEGER PRIMARY KEY AUTOINCREMENT,recipe_id INTEGER NOT NULL,cooked_on TEXT NOT NULL,rating INTEGER,note TEXT NOT NULL DEFAULT ""); PRAGMA user_version=1;'
        )
    store = Store(path)
    with store.connection() as db:
        assert db.execute("PRAGMA user_version").fetchone()[0] == 3
        assert "servings_eaten" in {r["name"] for r in db.execute("PRAGMA table_info(history)")}
        db.execute("PRAGMA user_version=4")
    with pytest.raises(RuntimeError):
        Store(path)


def test_weather_real_shape_cache_failure_and_southern_season(monkeypatch):
    service = WeatherService()
    location = Location(name="Sydney", latitude=-33.86, longitude=151.2)
    calls = []

    def fetch(url, params):
        calls.append(url)
        return {
            "timezone": "Australia/Sydney",
            "current": {
                "temperature_2m": 22,
                "apparent_temperature": 23,
                "weather_code": 2,
                "time": "2026-11-06T15:00",
            },
            "daily": {
                "time": ["2026-11-06"],
                "temperature_2m_min": [15],
                "temperature_2m_max": [25],
                "weather_code": [2],
            },
        }

    monkeypatch.setattr(service, "_json", fetch)
    first = service.current(location)
    assert first["status"] == "ok" and first["season"] == "春"
    assert service.current(location)["cached"] is True and len(calls) == 1
    key = (location.latitude, location.longitude)
    service.cache[key] = (time.time() - 1900, first)

    def fail(*args):
        raise requests.ConnectionError("network unavailable")

    monkeypatch.setattr(service, "_json", fail)
    stale = service.current(location)
    assert stale["status"] == "stale" and "不作为当前气温" in stale["message"]
    other = Location(name="Other", latitude=0, longitude=0)
    assert service.current(other)["status"] == "unavailable"
    assert season_on(date(2026, 1, 1), -20) == "夏"
    assert service.current(None)["status"] == "not_configured"


def test_city_and_optional_goal_validation(client):
    assert client.get("/api/locations?q=杭").status_code == 422
    assert (
        client.put(
            "/api/settings", json={"location": {"name": "bad", "latitude": 91, "longitude": 0}}
        ).status_code
        == 422
    )
    assert client.put("/api/settings", json={"daily_kcal_target": 500}).status_code == 422
    assert client.put("/api/settings", json={"daily_kcal_target": None}).status_code == 200


def test_allergy_statement_followed_by_question_still_excludes(client):
    from src.memory import explicit_exclusions

    assert explicit_exclusions([{"content": "我对虾过敏，今天吃什么？"}]) == ["虾"]
    assert explicit_exclusions([{"content": "我对虾过敏吗？"}]) == []
    assert explicit_exclusions([{"content": "如果我对虾过敏，应该怎么办？"}]) == []
    assert explicit_exclusions([{"content": "我对虾不过敏，但我不能吃鸡蛋。"}]) == ["鸡蛋"]


def test_generic_provider_is_opt_in_and_local_memory_stays_verbatim(client, monkeypatch):
    from src.assistant import model_config

    monkeypatch.delenv("HEALTHRECIPE_LLM_PROVIDER", raising=False)
    monkeypatch.delenv("HEALTHRECIPE_LLM_API_KEY", raising=False)
    monkeypatch.setenv("DASHSCOPE_API_KEY", "unrelated-existing-credential")
    assert model_config() is None
    create(client)
    response = chat(client, "我最近胃不舒服，想吃温热一些的。我对虾过敏，今天吃什么？").json()
    assert response["payload"]["mode"] == "local"
    memories = client.get("/api/memories").json()
    assert any(m["kind"] == "身体感受" and m["content"] == "我最近胃不舒服" for m in memories)
    assert any(m["content"] == "我对虾过敏" and m["expires_on"] is None for m in memories)


def test_common_food_group_exclusions_are_not_plain_substrings(client):
    from src.recommendation.recommend import matches

    assert matches("海鲜", "虾仁") and matches("海鲜", "鲈鱼")
    assert matches("奶制品", "牛奶")
    assert matches("大豆", "生抽")
    assert not matches("大豆", "土豆")
    assert estimate({"materials": [{"name": "番茄", "unit": "-100克"}], "servings": 1})["complete"] is False


def test_stated_allergy_is_not_automatically_forgotten_after_two_weeks(client, monkeypatch):
    monkeypatch.setattr(
        client.app.state.assistant,
        "_model_reply",
        lambda *_: Reply(
            reply="会避开含虾的候选菜谱。",
            memories=[{"kind": "饮食偏好", "evidence": "我对虾过敏", "days": 14}],
        ),
    )
    chat(client, "我对虾过敏，帮我记住")
    assert client.get("/api/memories").json()[0]["expires_on"] is None
