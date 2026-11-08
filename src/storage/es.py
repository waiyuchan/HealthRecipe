"""Compatibility shim for old scripts; Elasticsearch is no longer required."""

from src.models import Recipe
from src.storage.sqlite import Store


class ES:
    def __init__(self, path="data/healthrecipe.db"):
        self.store = Store(path)

    def insert(self, menu_item=None, menu_items=None):
        result = []
        for item in menu_items if menu_items is not None else [menu_item]:
            recipe = Recipe.model_validate(item)
            old = (
                next((r for r in self.store.recipes() if r["xcf_id"] == recipe.xcf_id), None)
                if recipe.xcf_id
                else None
            )
            result.append(self.store.save_recipe(recipe, old["id"] if old else None))
        return result
