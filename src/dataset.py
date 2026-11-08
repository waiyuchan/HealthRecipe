"""Small data facade for scripts and notebooks."""

from src.storage.sqlite import Store


class Dataset:
    def __init__(self, path="data/healthrecipe.db"):
        self.store = Store(path)

    def get_menu(self):
        return self.store.recipes()

    def get_history(self):
        return self.store.records("history")
