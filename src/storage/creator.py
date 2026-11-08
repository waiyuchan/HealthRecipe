"""Explicit, rate-limited collection. Importing this module performs no I/O."""

import time
from pathlib import Path

from src.collection.recipe_extractor import recipe_extractor
from src.models import Recipe
from src.storage.sqlite import Store


def get_xcf_id_list_from_txt(file_path):
    return list(
        dict.fromkeys(line.strip() for line in Path(file_path).read_text().splitlines() if line.strip())
    )


class Creator:
    def __init__(self, path="data/healthrecipe.db"):
        self.store = Store(path)

    def extract(self, xcf_id):
        return recipe_extractor(xcf_id)

    def insert(self, xcf_id):
        recipe = Recipe.model_validate(self.extract(xcf_id))
        existing = next((r for r in self.store.recipes() if r.get("xcf_id") == recipe.xcf_id), None)
        return self.store.save_recipe(recipe, existing["id"] if existing else None)

    def batch_insert(self, xcf_id_list):
        results = []
        for xcf_id in dict.fromkeys(xcf_id_list):
            try:
                results.append({"xcf_id": xcf_id, "recipe": self.insert(xcf_id)})
            except (ValueError, OSError) as exc:
                results.append({"xcf_id": xcf_id, "error": str(exc)})
            time.sleep(2)
        return results
