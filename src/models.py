"""Shared validation for the API, imports and SQLite writes."""

from datetime import date
from typing import Annotated, Literal
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Ingredient(Model):
    name: str = Field(min_length=1, max_length=80)
    unit: str = Field(default="适量", max_length=80)
    grams: float | None = Field(default=None, gt=0, le=100000)
    kcal_per100g: float | None = Field(default=None, ge=0, le=1000)


class Recipe(Model):
    name: str = Field(min_length=1, max_length=100)
    description: str = Field(default="", max_length=1000)
    materials: list[Ingredient] = Field(default_factory=list, max_length=80)
    methods: list[str] = Field(min_length=1, max_length=60)
    tags: list[str] = Field(default_factory=list, max_length=20)
    seasons: list[Literal["春", "夏", "秋", "冬"]] = Field(default_factory=list)
    minutes: int = Field(default=20, ge=1, le=1440)
    servings: int = Field(default=2, ge=1, le=30)
    category: str = Field(default="家常菜", min_length=1, max_length=30)
    source_url: str = Field(default="", max_length=1500)
    author: str = Field(default="", max_length=200)
    xcf_id: str | None = Field(default=None, pattern=r"^\d{1,20}$")
    favorite: bool = False
    original_text: str = Field(default="", max_length=15000)

    @field_validator("methods", "tags")
    @classmethod
    def clean_strings(cls, values):
        if any(not v.strip() or len(v) > 2000 for v in values):
            raise ValueError("步骤和标签不能为空，单项不超过 2000 字")
        return [v.strip() for v in values]

    @field_validator("source_url")
    @classmethod
    def safe_url(cls, value):
        if value and (urlparse(value).scheme not in ("https", "http") or not urlparse(value).netloc):
            raise ValueError("来源必须是 http(s) 链接")
        return value


class RecipeRecord(Recipe):
    id: int = Field(gt=0, le=2**63 - 1)


class History(Model):
    recipe_id: int = Field(gt=0, le=2**63 - 1)
    cooked_on: date = Field(default_factory=date.today)
    rating: int | None = Field(default=None, ge=1, le=5)
    note: str = Field(default="", max_length=1000)
    servings_eaten: float | None = Field(default=None, gt=0, le=30)
    meal: Literal["早餐", "午餐", "晚餐", "加餐", "其他"] = "其他"

    @field_validator("cooked_on")
    @classmethod
    def no_future(cls, value):
        if value > date.today():
            raise ValueError("做菜日期不能晚于今天")
        return value


class MacroValues(Model):
    kcal: float = Field(ge=0, le=1e9)
    protein: float = Field(ge=0, le=1e8)
    carbs: float = Field(ge=0, le=1e8)
    fat: float = Field(ge=0, le=1e8)


class NutritionSnapshot(Model):
    consumed: MacroValues
    servings_eaten: float = Field(gt=0, le=30)
    complete: bool
    macros_complete: bool = True
    warnings: list[Annotated[str, Field(max_length=1000)]] = Field(max_length=300)
    source: str = Field(max_length=200)
    recipe_servings: int = Field(ge=1, le=30)


class HistoryRecord(History):
    nutrition_snapshot: NutritionSnapshot | None = None
    id: int = Field(gt=0, le=2**63 - 1)


class Plan(Model):
    recipe_id: int = Field(gt=0, le=2**63 - 1)
    planned_on: date
    meal: Literal["早餐", "午餐", "晚餐"] = "晚餐"


class PlanRecord(Plan):
    id: int = Field(gt=0, le=2**63 - 1)


class Location(Model):
    name: str = Field(min_length=1, max_length=100)
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    country: str = Field(default="", max_length=100)
    admin1: str = Field(default="", max_length=100)
    timezone: str = Field(default="auto", max_length=100)


class MemoryInput(Model):
    kind: Literal["身体感受", "饮食偏好", "饮食目标", "生活习惯"]
    content: str = Field(min_length=1, max_length=500)
    expires_on: date | None = None


class MemoryRecord(MemoryInput):
    id: int = Field(gt=0, le=2**63 - 1)
    evidence: str = Field(default="", max_length=1000)
    created_on: date = Field(default_factory=date.today)


class ChatInput(Model):
    message: str = Field(min_length=1, max_length=3000)
    remember: bool = True
    request_id: str = Field(min_length=8, max_length=100, pattern=r"^[a-zA-Z0-9_-]+$")


class ChatRecord(Model):
    id: int = Field(gt=0, le=2**63 - 1)
    role: Literal["user", "assistant"]
    content: str = Field(max_length=15000)
    created_at: str = Field(max_length=60)
    payload: dict = Field(default_factory=dict)


class Settings(Model):
    excluded_ingredients: list[str] = Field(default_factory=list, max_length=100)
    pantry: list[str] = Field(default_factory=list, max_length=100)
    max_minutes: int = Field(default=60, ge=1, le=1440)
    avoid_days: int = Field(default=14, ge=0, le=90)
    location: Location | None = None
    daily_kcal_target: int | None = Field(default=None, ge=1200, le=5000)
    memory_enabled: bool = True

    @field_validator("excluded_ingredients", "pantry")
    @classmethod
    def names(cls, values):
        if any(not value or len(value) > 80 for value in values):
            raise ValueError("食材名称需为 1–80 字")
        return list(dict.fromkeys(values))


class NutritionInput(Model):
    materials: list[Ingredient] = Field(min_length=1, max_length=80)
    servings: float = Field(default=1, gt=0, le=100)


class PlanBatch(Model):
    items: list[Plan] = Field(min_length=1, max_length=21)


class QuickDish(Model):
    name: str = Field(min_length=1, max_length=100)
    recipe_id: int | None = Field(default=None, gt=0, le=2**63 - 1)
    servings_eaten: float | None = Field(default=1, gt=0, le=30)


class QuickMeal(Model):
    dishes: list[QuickDish] = Field(min_length=1, max_length=30)
    cooked_on: date = Field(default_factory=date.today)
    meal: Literal["早餐", "午餐", "晚餐", "加餐", "其他"] = "午餐"
    note: str = Field(default="", max_length=1000)
    request_id: str = Field(min_length=8, max_length=100, pattern=r"^[a-zA-Z0-9_-]+$")

    @field_validator("cooked_on")
    @classmethod
    def no_future(cls, value):
        if value > date.today():
            raise ValueError("吃饭日期不能晚于今天")
        return value


class QuickLogRecord(QuickDish):
    id: int = Field(gt=0, le=2**63 - 1)
    cooked_on: date
    meal: Literal["早餐", "午餐", "晚餐", "加餐", "其他"]
    note: str = Field(default="", max_length=1000)
    nutrition_snapshot: NutritionSnapshot | None = None


class QuickLogUpdate(QuickDish):
    cooked_on: date
    meal: Literal["早餐", "午餐", "晚餐", "加餐", "其他"]
    note: str = Field(default="", max_length=1000)

    @field_validator("cooked_on")
    @classmethod
    def no_future(cls, value):
        if value > date.today():
            raise ValueError("吃饭日期不能晚于今天")
        return value


class RecipeDraft(Model):
    name: str = Field(min_length=1, max_length=100)
    narration: str = Field(default="", max_length=15000)
    source_url: str = Field(default="", max_length=1500)
    author: str = Field(default="", max_length=200)
    materials: list[Ingredient] = Field(default_factory=list, max_length=80)

    @field_validator("source_url")
    @classmethod
    def safe_url(cls, value):
        return Recipe.safe_url(value)


class DraftRecord(RecipeDraft):
    id: int = Field(gt=0, le=2**63 - 1)
    created_at: str = Field(max_length=60)


class CaptureSave(Model):
    recipe: Recipe
    draft_id: int | None = Field(default=None, gt=0, le=2**63 - 1)


class CaptureInput(Model):
    author: str = Field(default="", max_length=200)
    name: str = Field(default="", max_length=100)
    narration: str = Field(default="", max_length=15000)
    materials: list[Ingredient] = Field(default_factory=list, max_length=80)
    url: str = Field(default="", max_length=1500)

    @model_validator(mode="after")
    def has_content(self):
        if not self.name and not self.url:
            raise ValueError("至少填写菜名或分享链接")
        return self


class RecipeSearch(Model):
    name: str = Field(min_length=1, max_length=100)
    sources: list[Literal["xiachufang", "meishichina", "douguo", "xiaohongshu", "woks"]] = Field(
        default_factory=lambda: ["xiachufang", "meishichina", "douguo", "xiaohongshu", "woks"],
        min_length=1,
        max_length=5,
    )


class Backup(Model):
    version: Literal[1, 2, 3] = 3
    recipes: list[RecipeRecord] = Field(max_length=10000)
    history: list[HistoryRecord] = Field(default_factory=list, max_length=50000)
    plans: list[PlanRecord] = Field(default_factory=list, max_length=10000)
    settings: Settings = Field(default_factory=Settings)
    memories: list[MemoryRecord] = Field(default_factory=list, max_length=10000)
    messages: list[ChatRecord] = Field(default_factory=list, max_length=50000)

    meal_logs: list[QuickLogRecord] = Field(default_factory=list, max_length=50000)
    drafts: list[DraftRecord] = Field(default_factory=list, max_length=10000)

    @model_validator(mode="after")
    def unique_ids(self):
        for records in (
            self.recipes,
            self.history,
            self.plans,
            self.memories,
            self.messages,
            self.meal_logs,
            self.drafts,
        ):
            ids = [item.id for item in records]
            if len(ids) != len(set(ids)):
                raise ValueError("备份内的记录 ID 不能重复")
        return self
