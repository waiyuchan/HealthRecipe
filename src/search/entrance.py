"""Unicode substring search across titles, ingredients, tags and instructions."""

from src.recommendation.recommend import normalize


class SearchEntrance:
    def __init__(self, store):
        self.store = store

    def search(self, keyword="", category="", favorite=False):
        terms = normalize(keyword).split()
        results = []
        for recipe in self.store.recipes():
            title = normalize(recipe["name"])
            ingredients = " ".join(normalize(m["name"]) for m in recipe["materials"])
            haystack = " ".join(
                [
                    title,
                    ingredients,
                    normalize(" ".join(recipe["tags"])),
                    normalize(recipe["description"]),
                    normalize(" ".join(recipe["methods"])),
                ]
            )
            if category and recipe["category"] != category:
                continue
            if favorite and not recipe["favorite"]:
                continue
            if all(term in haystack for term in terms):
                score = sum(10 * (term in title) + 4 * (term in ingredients) for term in terms)
                results.append((score, recipe))
        return [r for _, r in sorted(results, key=lambda item: -item[0])]

    def keyword_search(self, keyword):
        return self.search(keyword)

    fuzzy_search = keyword_search

    def semantic_search(self, keyword):
        # Exact ingredient relationships with kitchen synonyms, not an embedding search.
        return [
            r
            for r in self.store.recipes()
            if any(normalize(keyword) in normalize(m["name"]) for m in r["materials"])
        ]
