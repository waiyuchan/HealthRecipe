"""HealthRecipe HTTP API and same-origin, build-free mobile web app."""

import json
import logging
import os
import re
import sqlite3
import time
from contextlib import asynccontextmanager
from datetime import date, timedelta
from pathlib import Path
from typing import Annotated, Literal

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi import Path as APIPath
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import Field

from src.assistant import MealAssistant
from src.collection.recipe_extractor import recipe_extractor, recipe_id_from_input
from src.collection.web_recipes import SOURCES, RecipeFinder, checked_url, parse_narration
from src.food_entry import resolve_dish
from src.middleware import BodyLimitMiddleware
from src.models import (
    Backup,
    CaptureInput,
    CaptureSave,
    ChatInput,
    History,
    MemoryInput,
    Model,
    NutritionInput,
    Plan,
    PlanBatch,
    QuickLogUpdate,
    QuickMeal,
    Recipe,
    RecipeDraft,
    RecipeSearch,
    Settings,
)
from src.nutrition import REFERENCE, estimate, recent_summary
from src.recommendation.recommend import Recommendation, matches
from src.search.entrance import SearchEntrance
from src.storage.sqlite import Store
from src.weather import WeatherService

Identifier = Annotated[int, APIPath(ge=1, le=2**63 - 1)]
MAX_PLAN_START = date(9999, 11, 30)

ROOT = Path(__file__).resolve().parents[1]
logger = logging.getLogger("uvicorn.error.healthrecipe")


class ImportRequest(Model):
    source: str = Field(min_length=1, max_length=500)


class Favorite(Model):
    favorite: bool


def create_app(db_path=None, seed=True):
    path = db_path or os.getenv("HEALTHRECIPE_DB", str(ROOT / "data/healthrecipe.db"))

    @asynccontextmanager
    async def lifespan(app):
        app.state.store = Store(path)
        if seed:
            app.state.store.seed(json.loads((ROOT / "data/recipes.json").read_text()))
        app.state.finder = RecipeFinder()
        app.state.weather = WeatherService()
        app.state.assistant = MealAssistant(app.state.store, app.state.weather)
        yield

    app = FastAPI(title="HealthRecipe", version="3.0.0", lifespan=lifespan, docs_url=None, redoc_url=None)

    @app.middleware("http")
    async def request_log(request: Request, call_next):
        start = time.monotonic()
        # Browser writes must come from this origin; no wildcard CORS.
        origin = request.headers.get("origin")
        if request.method not in {"GET", "HEAD", "OPTIONS"} and origin:
            from urllib.parse import urlparse

            parsed = urlparse(origin)
            if parsed.netloc != request.headers.get("host") or parsed.scheme != request.url.scheme:
                return JSONResponse({"detail": "请从应用页面进行操作"}, status_code=403)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "same-origin"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'; "
            "connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
        )
        logger.info(
            "%s %s %s %.0fms",
            request.method,
            request.url.path,
            response.status_code,
            (time.monotonic() - start) * 1000,
        )
        return response

    @app.exception_handler(sqlite3.IntegrityError)
    async def conflict(_request, _exc):
        return JSONResponse(
            {"detail": "数据冲突：菜谱来源、记录 ID 不可重复，关联菜谱必须存在"}, status_code=409
        )

    def store():
        return app.state.store

    def require_recipe(recipe_id):
        recipe = store().recipe(recipe_id)
        if not recipe:
            raise HTTPException(404, "菜谱不存在或已删除")
        return recipe

    def enrich(records):
        names = {r["id"]: r["name"] for r in store().recipes()}
        return [{**r, "recipe_name": names.get(r["recipe_id"], "已删除菜谱")} for r in records]

    @app.get("/api/health")
    def health():
        with store().connection() as db:
            db.execute("SELECT 1")
        return {"status": "ok", "version": "3.0.0", "storage": "sqlite"}

    @app.get("/api/recipes")
    def recipes(
        q: str = Query("", max_length=200),
        category: str = Query("", max_length=30),
        favorite: bool = False,
        offset: int = Query(0, ge=0),
        limit: int = Query(60, ge=1, le=200),
    ):
        items = SearchEntrance(store()).search(q, category, favorite)
        return {
            "items": [{**r, "nutrition": estimate(r)} for r in items[offset : offset + limit]],
            "total": len(items),
        }

    @app.get("/api/categories")
    def categories():
        counts = {}
        for recipe in store().recipes():
            counts[recipe["category"]] = counts.get(recipe["category"], 0) + 1
        return [{"name": key, "count": value} for key, value in sorted(counts.items())]

    @app.post("/api/recipes", status_code=201)
    def create_recipe(recipe: Recipe):
        return store().save_recipe(recipe)

    @app.post("/api/import/xiachufang", status_code=201)
    def import_xcf(item: ImportRequest):
        try:
            recipe_id = recipe_id_from_input(item.source)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        existing = next((r for r in store().recipes() if r["xcf_id"] == recipe_id), None)
        if existing:
            return {"recipe": existing, "created": False}
        try:
            recipe = Recipe.model_validate(recipe_extractor(recipe_id))
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        return {"recipe": store().save_recipe(recipe), "created": True}

    @app.post("/api/import/xiachufang/preview")
    def preview_xcf(item: ImportRequest):
        try:
            recipe_id = recipe_id_from_input(item.source)
            existing = next((r for r in store().recipes() if r["xcf_id"] == recipe_id), None)
            if existing:
                return {"recipe": existing, "exists": True}
            recipe = Recipe.model_validate(recipe_extractor(recipe_id))
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        return {"recipe": recipe.model_dump(), "exists": False}

    @app.get("/api/recipes/{recipe_id}")
    def detail(recipe_id: Identifier):
        recipe = require_recipe(recipe_id)
        related = []
        names = {m["name"] for m in recipe["materials"]}
        for other in store().recipes():
            shared = sorted(names & {m["name"] for m in other["materials"]} - {"盐", "食用油", "水"})
            if other["id"] != recipe_id and shared:
                related.append({"id": other["id"], "name": other["name"], "shared": shared})
        related.sort(key=lambda r: -len(r["shared"]))
        return {**recipe, "related": related[:6], "nutrition": estimate(recipe)}

    @app.put("/api/recipes/{recipe_id}")
    def update_recipe(recipe_id: Identifier, recipe: Recipe):
        require_recipe(recipe_id)
        return store().save_recipe(recipe, recipe_id)

    @app.patch("/api/recipes/{recipe_id}/favorite")
    def favorite(recipe_id: Identifier, item: Favorite):
        recipe = require_recipe(recipe_id)
        recipe.pop("id")
        recipe["favorite"] = item.favorite
        return store().save_recipe(Recipe.model_validate(recipe), recipe_id)

    @app.delete("/api/recipes/{recipe_id}", status_code=204)
    def delete_recipe(recipe_id: Identifier):
        if not store().delete("recipes", recipe_id):
            raise HTTPException(404, "菜谱不存在")

    @app.get("/api/recommendations")
    def recommendations(
        limit: int = Query(6, ge=1, le=30),
        ingredients: str = Query("", max_length=500),
        season: Literal["春", "夏", "秋", "冬"] | None = None,
        temperature: float | None = Query(None, ge=-50, le=60),
        mode: Literal["smart", "random"] = "smart",
    ):
        terms = [v.strip() for v in re.split(r"[,，、\n]", ingredients) if v.strip()]
        weather = app.state.weather.current(store().settings().location)
        if temperature is None and weather["status"] == "ok":
            temperature = weather["temperature"]
        return Recommendation(store()).recommend(
            limit=limit,
            ingredients=terms,
            season=season or weather["season"],
            temperature=temperature,
            mode=mode,
        )

    @app.get("/api/history")
    def history(days: int = Query(14, ge=1, le=3650)):
        cutoff = str(date.today() - timedelta(days=days - 1))
        return enrich([r for r in store().records("history") if r["cooked_on"] >= cutoff])

    @app.post("/api/history", status_code=201)
    def add_history(item: History):
        require_recipe(item.recipe_id)
        return store().add_history(item)

    @app.put("/api/history/{item_id}")
    def update_history(item_id: Identifier, item: History):
        require_recipe(item.recipe_id)
        result = store().update_history(item_id, item)
        if result is None:
            raise HTTPException(404, "记录不存在")
        return result

    @app.delete("/api/history/{item_id}", status_code=204)
    def delete_history(item_id: Identifier):
        if not store().delete("history", item_id):
            raise HTTPException(404, "记录不存在")

    @app.get("/api/plans")
    def plans(
        start: Annotated[date | None, Query(le=MAX_PLAN_START)] = None, days: int = Query(7, ge=1, le=31)
    ):
        start = start or date.today()
        end = start + timedelta(days=days)
        return enrich([r for r in store().records("plans") if str(start) <= r["planned_on"] < str(end)])

    @app.post("/api/plans", status_code=201)
    def add_plan(item: Plan):
        require_recipe(item.recipe_id)
        return store().add_plan(item)

    @app.delete("/api/plans/{item_id}", status_code=204)
    def delete_plan(item_id: Identifier):
        if not store().delete("plans", item_id):
            raise HTTPException(404, "计划不存在")

    @app.get("/api/shopping")
    def shopping(
        start: Annotated[date | None, Query(le=MAX_PLAN_START)] = None, days: int = Query(7, ge=1, le=31)
    ):
        start = start or date.today()
        end = start + timedelta(days=days)
        pantry = store().settings().pantry
        recipes = {r["id"]: r for r in store().recipes()}
        items = {}
        for plan in store().records("plans"):
            if not str(start) <= plan["planned_on"] < str(end):
                continue
            recipe = recipes[plan["recipe_id"]]
            for material in recipe["materials"]:
                name = material["name"]
                item = items.setdefault(
                    name, {"name": name, "uses": [], "in_pantry": any(matches(p, name) for p in pantry)}
                )
                item["uses"].append(
                    {
                        "recipe": recipe["name"],
                        "amount": material["unit"],
                        "planned_on": plan["planned_on"],
                        "meal": plan["meal"],
                    }
                )
        return sorted(items.values(), key=lambda r: (r["in_pantry"], r["name"]))

    @app.get("/api/weather")
    def weather():
        return app.state.weather.current(store().settings().location)

    @app.get("/api/locations")
    def locations(q: str = Query(min_length=2, max_length=100)):
        try:
            return app.state.weather.search(q)
        except ValueError as exc:
            raise HTTPException(502, str(exc)) from exc

    @app.get("/api/nutrition/reference")
    def nutrition_reference():
        return REFERENCE

    @app.post("/api/nutrition/estimate")
    def nutrition_estimate(item: NutritionInput):
        return estimate(item.model_dump())

    @app.get("/api/nutrition/summary")
    def nutrition_summary(days: int = Query(14, ge=1, le=365)):
        return recent_summary(store(), days)

    @app.get("/api/assistant/status")
    def assistant_status():
        return app.state.assistant.status()

    @app.get("/api/assistant/messages")
    def assistant_messages():
        return store().messages()

    @app.post("/api/assistant/chat")
    def assistant_chat(item: ChatInput):
        try:
            return app.state.assistant.respond(item)
        except RuntimeError as exc:
            raise HTTPException(409, str(exc)) from exc

    @app.delete("/api/assistant/messages", status_code=204)
    def clear_chat(forget_memories: bool = False):
        store().clear_chat(forget=forget_memories)

    @app.get("/api/memories")
    def memories():
        return store().memories(active_only=False)

    @app.post("/api/memories", status_code=201)
    def add_memory(item: MemoryInput):
        if item.kind == "身体感受" and item.expires_on is None:
            item = item.model_copy(update={"expires_on": date.today() + timedelta(days=14)})
        return store().save_memory(item)

    @app.put("/api/memories/{item_id}")
    def update_memory(item_id: Identifier, item: MemoryInput):
        if item.kind == "身体感受" and item.expires_on is None:
            item = item.model_copy(update={"expires_on": date.today() + timedelta(days=14)})
        result = store().save_memory(item, item_id=item_id)
        if not result:
            raise HTTPException(404, "记忆不存在")
        return result

    @app.delete("/api/memories/{item_id}", status_code=204)
    def forget_memory(item_id: Identifier):
        if not store().forget_memory(item_id):
            raise HTTPException(404, "记忆不存在")

    @app.post("/api/plans/batch", status_code=201)
    def batch_plans(item: PlanBatch):
        for plan in item.items:
            require_recipe(plan.recipe_id)
        return store().add_plans(item.items)

    @app.get("/api/food-log")
    def food_log(days: int = Query(14, ge=1, le=3650)):
        return recent_summary(store(), days)

    @app.post("/api/food-log", status_code=201)
    def record_food(item: QuickMeal):
        try:
            input_text = item.model_dump_json(exclude={"request_id"})
            item = item.model_copy(update={"dishes": [resolve_dish(store(), d) for d in item.dishes]})
            return {"items": store().record_meal(item, input_text)}
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc

    @app.put("/api/food-log/{item_id}")
    def update_food(item_id: Identifier, item: QuickLogUpdate):
        try:
            item = resolve_dish(store(), item)
            result = store().update_meal_log(item_id, item)
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc
        if not result:
            raise HTTPException(404, "吃饭记录不存在")
        return result

    @app.delete("/api/food-log/{item_id}", status_code=204)
    def delete_food(item_id: Identifier):
        if not store().delete_meal_log(item_id):
            raise HTTPException(404, "吃饭记录不存在")

    @app.post("/api/capture/search")
    def search_recipe(item: RecipeSearch):
        return app.state.finder.search(item.name, item.sources)

    @app.post("/api/capture/preview")
    def preview_capture(item: CaptureInput):
        try:
            if item.narration.strip():
                if not item.name:
                    raise ValueError("口述做法请同时填一个菜名")
                recipe = parse_narration(item.name, item.narration, item.materials).model_copy(
                    update={"author": item.author}
                )
                if item.url:
                    recipe = recipe.model_copy(
                        update={"source_url": checked_url(item.url)[0], "author": item.author}
                    )
                return {
                    "status": "ready",
                    "recipe": recipe.model_dump(),
                    "source": "你的口述",
                    "warnings": [] if recipe.materials else ["食材尚未填写，不推算配料与热量，可稍后补充。"],
                }
            if item.url:
                return app.state.finder.fetch(item.url, item.name)
            return {
                "status": "search",
                **app.state.finder.search(item.name, list(SOURCES)),
            }
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc

    @app.post("/api/capture/save", status_code=201)
    def save_capture(item: CaptureSave):
        return store().save_capture(item.recipe, item.draft_id)

    @app.get("/api/capture/drafts")
    def drafts():
        return store().drafts()

    @app.post("/api/capture/drafts", status_code=201)
    def add_draft(item: RecipeDraft):
        return store().add_draft(item)

    @app.put("/api/capture/drafts/{item_id}")
    def update_draft(item_id: Identifier, item: RecipeDraft):
        result = store().update_draft(item_id, item)
        if not result:
            raise HTTPException(404, "待找菜谱不存在")
        return result

    @app.delete("/api/capture/drafts/{item_id}", status_code=204)
    def delete_draft(item_id: Identifier):
        if not store().delete_draft(item_id):
            raise HTTPException(404, "待找菜谱不存在")

    @app.get("/api/settings")
    def settings():
        return store().settings()

    @app.put("/api/settings")
    def save_settings(item: Settings):
        return store().save_settings(item)

    @app.get("/api/backup")
    def backup():
        return JSONResponse(
            store().export(),
            headers={"Content-Disposition": f'attachment; filename="healthrecipe-{date.today()}.json"'},
        )

    @app.post("/api/restore")
    def restore(item: Backup):
        store().restore(item)
        return {"recipes": len(item.recipes), "history": len(item.history), "plans": len(item.plans)}

    @app.get("/")
    def index():
        return FileResponse(ROOT / "web/index.html")

    @app.get("/docs", include_in_schema=False)
    def api_docs():
        return FileResponse(ROOT / "web/api.html")

    app.mount("/static", StaticFiles(directory=ROOT / "web"), name="static")
    app.add_middleware(BodyLimitMiddleware)
    return app


app = create_app()
