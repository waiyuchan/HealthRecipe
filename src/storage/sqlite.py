"""One local database, short transactions, foreign keys, WAL and portable backups."""

import hashlib
import json
import sqlite3
from contextlib import contextmanager
from datetime import UTC, date, datetime
from pathlib import Path

from src.models import Backup, Recipe, Settings
from src.nutrition import snapshot


class Store:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as db:
            if db.execute("PRAGMA user_version").fetchone()[0] > 3:
                raise RuntimeError("数据库来自更高版本，请使用对应版本的 HealthRecipe")
            db.execute("PRAGMA journal_mode=WAL")
            db.executescript("""
                CREATE TABLE IF NOT EXISTS recipes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    xcf_id TEXT UNIQUE,
                    payload TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS ingredients (
                    recipe_id INTEGER NOT NULL REFERENCES recipes(id) ON DELETE CASCADE,
                    name TEXT NOT NULL,
                    PRIMARY KEY(recipe_id, name)
                );
                CREATE INDEX IF NOT EXISTS ingredients_name ON ingredients(name);
                CREATE TABLE IF NOT EXISTS history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    recipe_id INTEGER NOT NULL REFERENCES recipes(id) ON DELETE CASCADE,
                    cooked_on TEXT NOT NULL, rating INTEGER CHECK(rating BETWEEN 1 AND 5),
                    note TEXT NOT NULL DEFAULT ''
                );
                CREATE INDEX IF NOT EXISTS history_date ON history(cooked_on, recipe_id);
                CREATE TABLE IF NOT EXISTS plans (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    recipe_id INTEGER NOT NULL REFERENCES recipes(id) ON DELETE CASCADE,
                    planned_on TEXT NOT NULL, meal TEXT NOT NULL,
                    UNIQUE(recipe_id, planned_on, meal)
                );
                CREATE INDEX IF NOT EXISTS plans_date ON plans(planned_on);
                CREATE TABLE IF NOT EXISTS settings (id INTEGER PRIMARY KEY CHECK(id=1), payload TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS memories (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    kind TEXT NOT NULL, content TEXT NOT NULL, evidence TEXT NOT NULL DEFAULT '',
                    created_on TEXT NOT NULL, expires_on TEXT
                );
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, role TEXT NOT NULL,
                    content TEXT NOT NULL, created_at TEXT NOT NULL, payload TEXT NOT NULL DEFAULT '{}'
                );
                CREATE TABLE IF NOT EXISTS meal_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    recipe_id INTEGER REFERENCES recipes(id) ON DELETE SET NULL,
                    servings_eaten REAL,
                    cooked_on TEXT NOT NULL, meal TEXT NOT NULL, note TEXT NOT NULL DEFAULT '',
                    nutrition_snapshot TEXT, batch_id TEXT
                );
                CREATE INDEX IF NOT EXISTS meal_logs_date ON meal_logs(cooked_on,recipe_id);
                CREATE TABLE IF NOT EXISTS meal_batches (
                    request_id TEXT PRIMARY KEY, fingerprint TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS recipe_drafts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, created_at TEXT NOT NULL, payload TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS chat_runs (
                    request_id TEXT PRIMARY KEY, reply_id INTEGER NOT NULL REFERENCES messages(id) ON DELETE CASCADE
                );
            """)
            columns = {r["name"] for r in db.execute("PRAGMA table_info(history)")}
            for name, declaration in [
                ("servings_eaten", "REAL"),
                ("meal", "TEXT NOT NULL DEFAULT '其他'"),
                ("nutrition_snapshot", "TEXT"),
            ]:
                if name not in columns:
                    db.execute(f"ALTER TABLE history ADD COLUMN {name} {declaration}")
            db.execute("PRAGMA user_version=3")

    @contextmanager
    def connection(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        try:
            with db:
                yield db
        finally:
            db.close()

    @staticmethod
    def _write_recipe(db, recipe, recipe_id=None):
        data = recipe.model_dump()
        payload = json.dumps(data, ensure_ascii=False)
        if recipe_id is None:
            recipe_id = db.execute(
                "INSERT INTO recipes(name,xcf_id,payload) VALUES(?,?,?)",
                (recipe.name, recipe.xcf_id, payload),
            ).lastrowid
        else:
            db.execute(
                "INSERT INTO recipes(id,name,xcf_id,payload) VALUES(?,?,?,?) "
                "ON CONFLICT(id) DO UPDATE SET name=excluded.name,xcf_id=excluded.xcf_id,payload=excluded.payload",
                (recipe_id, recipe.name, recipe.xcf_id, payload),
            )
            db.execute("DELETE FROM ingredients WHERE recipe_id=?", (recipe_id,))
        db.executemany(
            "INSERT OR IGNORE INTO ingredients VALUES(?,?)",
            [(recipe_id, item.name) for item in recipe.materials],
        )
        return {"id": recipe_id, **data}

    def seed(self, recipes):
        # A persistent marker prevents deleted demo recipes from returning after restart.
        with self.connection() as db:
            if db.execute("SELECT 1 FROM metadata WHERE key='initialized'").fetchone():
                return
            if not db.execute("SELECT 1 FROM recipes LIMIT 1").fetchone():
                for item in recipes:
                    self._write_recipe(db, Recipe.model_validate(item))
            db.execute("INSERT INTO metadata VALUES('initialized','1')")

    def save_recipe(self, recipe, recipe_id=None):
        with self.connection() as db:
            return self._write_recipe(db, recipe, recipe_id)

    def recipes(self):
        with self.connection() as db:
            return [
                {"id": row["id"], **json.loads(row["payload"])}
                for row in db.execute("SELECT id,payload FROM recipes ORDER BY id DESC")
            ]

    def import_recipes(self, recipes):
        """Validate first at the caller, then import the entire batch atomically."""
        with self.connection() as db:
            for recipe in recipes:
                existing = db.execute("SELECT id FROM recipes WHERE xcf_id=?", (recipe.xcf_id,)).fetchone()
                self._write_recipe(db, recipe, existing[0] if existing else None)
            db.execute("INSERT OR REPLACE INTO metadata VALUES('initialized','1')")

    def recipe(self, recipe_id):
        with self.connection() as db:
            row = db.execute("SELECT payload FROM recipes WHERE id=?", (recipe_id,)).fetchone()
            return {"id": recipe_id, **json.loads(row[0])} if row else None

    def delete(self, table, item_id):
        if table not in {"recipes", "history", "plans", "memories"}:
            raise ValueError("Unknown table")
        with self.connection() as db:
            return db.execute(f"DELETE FROM {table} WHERE id=?", (item_id,)).rowcount

    def settings(self):
        with self.connection() as db:
            row = db.execute("SELECT payload FROM settings WHERE id=1").fetchone()
            return Settings.model_validate_json(row[0]) if row else Settings()

    def save_settings(self, settings):
        with self.connection() as db:
            db.execute("INSERT OR REPLACE INTO settings VALUES(1,?)", (settings.model_dump_json(),))
        return settings

    def records(self, table):
        if table not in {"history", "plans"}:
            raise ValueError("Unknown table")
        order = "cooked_on DESC,id DESC" if table == "history" else "planned_on,meal,id"
        with self.connection() as db:
            rows = [dict(row) for row in db.execute(f"SELECT * FROM {table} ORDER BY {order}")]
            if table == "history":
                for row in rows:
                    row["nutrition_snapshot"] = (
                        json.loads(row["nutrition_snapshot"]) if row["nutrition_snapshot"] else None
                    )
            return rows

    def add_history(self, item):
        nutrition = snapshot(self.recipe(item.recipe_id), item.servings_eaten)
        with self.connection() as db:
            record_id = db.execute(
                "INSERT INTO history(recipe_id,cooked_on,rating,note,servings_eaten,meal,nutrition_snapshot) VALUES(?,?,?,?,?,?,?)",
                (
                    item.recipe_id,
                    str(item.cooked_on),
                    item.rating,
                    item.note,
                    item.servings_eaten,
                    item.meal,
                    json.dumps(nutrition) if nutrition else None,
                ),
            ).lastrowid
        return {"id": record_id, **item.model_dump(mode="json"), "nutrition_snapshot": nutrition}

    def update_history(self, item_id, item):
        with self.connection() as db:
            old = db.execute("SELECT * FROM history WHERE id=?", (item_id,)).fetchone()
            if old is None:
                return None
            if old["recipe_id"] == item.recipe_id and old["servings_eaten"] == item.servings_eaten:
                nutrition = json.loads(old["nutrition_snapshot"]) if old["nutrition_snapshot"] else None
            elif old["recipe_id"] == item.recipe_id and old["nutrition_snapshot"]:
                nutrition = json.loads(old["nutrition_snapshot"]) if item.servings_eaten is not None else None
                if nutrition and old["servings_eaten"]:
                    ratio = item.servings_eaten / old["servings_eaten"]
                    nutrition["consumed"] = {k: round(v * ratio, 1) for k, v in nutrition["consumed"].items()}
                    nutrition["servings_eaten"] = item.servings_eaten
            else:
                nutrition = snapshot(self.recipe(item.recipe_id), item.servings_eaten)
            changed = db.execute(
                "UPDATE history SET recipe_id=?,cooked_on=?,rating=?,note=?,servings_eaten=?,meal=?,nutrition_snapshot=? WHERE id=?",
                (
                    item.recipe_id,
                    str(item.cooked_on),
                    item.rating,
                    item.note,
                    item.servings_eaten,
                    item.meal,
                    json.dumps(nutrition) if nutrition else None,
                    item_id,
                ),
            ).rowcount
        return (
            {"id": item_id, **item.model_dump(mode="json"), "nutrition_snapshot": nutrition}
            if changed
            else None
        )

    def add_plan(self, item):
        with self.connection() as db:
            db.execute(
                "INSERT OR IGNORE INTO plans(recipe_id,planned_on,meal) VALUES(?,?,?)",
                (item.recipe_id, str(item.planned_on), item.meal),
            )
            return dict(
                db.execute(
                    "SELECT * FROM plans WHERE recipe_id=? AND planned_on=? AND meal=?",
                    (item.recipe_id, str(item.planned_on), item.meal),
                ).fetchone()
            )

    def export(self):
        # All tables are read in the same SQLite snapshot.
        with self.connection() as db:
            db.execute("BEGIN")
            recipes = [
                {"id": r["id"], **json.loads(r["payload"])} for r in db.execute("SELECT * FROM recipes")
            ]
            settings = db.execute("SELECT payload FROM settings WHERE id=1").fetchone()
            return {
                "version": 3,
                "recipes": recipes,
                "history": [
                    {
                        **dict(r),
                        "nutrition_snapshot": json.loads(r["nutrition_snapshot"])
                        if r["nutrition_snapshot"]
                        else None,
                    }
                    for r in db.execute("SELECT * FROM history")
                ],
                "memories": [dict(r) for r in db.execute("SELECT * FROM memories")],
                "messages": [
                    {**dict(r), "payload": json.loads(r["payload"])}
                    for r in db.execute("SELECT * FROM messages")
                ],
                "meal_logs": [self._log_row(r) for r in db.execute("SELECT * FROM meal_logs")],
                "drafts": [
                    {"id": r["id"], "created_at": r["created_at"], **json.loads(r["payload"])}
                    for r in db.execute("SELECT * FROM recipe_drafts")
                ],
                "plans": [dict(r) for r in db.execute("SELECT * FROM plans")],
                "settings": json.loads(settings[0]) if settings else Settings().model_dump(),
            }

    def restore(self, backup: Backup):
        with self.connection() as db:
            db.execute("DELETE FROM meal_logs")
            db.execute("DELETE FROM meal_batches")
            db.execute("DELETE FROM recipe_drafts")
            db.execute("DELETE FROM recipes")
            db.execute("DELETE FROM memories")
            db.execute("DELETE FROM messages")
            for item in backup.recipes:
                self._write_recipe(db, Recipe.model_validate(item.model_dump(exclude={"id"})), item.id)
            for item in backup.history:
                db.execute(
                    "INSERT INTO history(id,recipe_id,cooked_on,rating,note,servings_eaten,meal,nutrition_snapshot) VALUES(?,?,?,?,?,?,?,?)",
                    (
                        item.id,
                        item.recipe_id,
                        str(item.cooked_on),
                        item.rating,
                        item.note,
                        item.servings_eaten,
                        item.meal,
                        json.dumps(item.nutrition_snapshot.model_dump()) if item.nutrition_snapshot else None,
                    ),
                )
            for item in backup.plans:
                db.execute(
                    "INSERT INTO plans VALUES(?,?,?,?)",
                    (item.id, item.recipe_id, str(item.planned_on), item.meal),
                )
            for item in backup.memories:
                db.execute(
                    "INSERT INTO memories VALUES(?,?,?,?,?,?)",
                    (
                        item.id,
                        item.kind,
                        item.content,
                        item.evidence,
                        str(item.created_on),
                        str(item.expires_on) if item.expires_on else None,
                    ),
                )
            for item in backup.messages:
                db.execute(
                    "INSERT INTO messages VALUES(?,?,?,?,?)",
                    (
                        item.id,
                        item.role,
                        item.content,
                        item.created_at,
                        json.dumps(item.payload, ensure_ascii=False),
                    ),
                )
            for item in backup.meal_logs:
                db.execute(
                    "INSERT INTO meal_logs(id,name,recipe_id,servings_eaten,cooked_on,meal,note,nutrition_snapshot) VALUES(?,?,?,?,?,?,?,?)",
                    (
                        item.id,
                        item.name,
                        item.recipe_id,
                        item.servings_eaten,
                        str(item.cooked_on),
                        item.meal,
                        item.note,
                        item.nutrition_snapshot.model_dump_json() if item.nutrition_snapshot else None,
                    ),
                )
            for item in backup.drafts:
                db.execute(
                    "INSERT INTO recipe_drafts VALUES(?,?,?)",
                    (item.id, item.created_at, item.model_dump_json(exclude={"id", "created_at"})),
                )
            db.execute("INSERT OR REPLACE INTO settings VALUES(1,?)", (backup.settings.model_dump_json(),))
            db.execute("INSERT OR REPLACE INTO metadata VALUES('initialized','1')")

    def memories(self, active_only=True):
        with self.connection() as db:
            rows = [dict(r) for r in db.execute("SELECT * FROM memories ORDER BY id DESC")]
        return [
            r for r in rows if not active_only or not r["expires_on"] or r["expires_on"] >= str(date.today())
        ]

    def save_memory(self, item, evidence="", item_id=None):
        with self.connection() as db:
            if item_id is not None:
                changed = db.execute(
                    "UPDATE memories SET kind=?,content=?,expires_on=? WHERE id=?",
                    (item.kind, item.content, str(item.expires_on) if item.expires_on else None, item_id),
                ).rowcount
                # Editing facts invalidates raw conversation context and cached replies.
                db.execute("DELETE FROM messages")
                return {"id": item_id, **item.model_dump(mode="json")} if changed else None
            existing = db.execute(
                "SELECT id FROM memories WHERE kind=? AND content=?", (item.kind, item.content)
            ).fetchone()
            if existing:
                db.execute(
                    "UPDATE memories SET expires_on=? WHERE id=?",
                    (str(item.expires_on) if item.expires_on else None, existing["id"]),
                )
                return {"id": existing["id"], **item.model_dump(mode="json")}
            item_id = db.execute(
                "INSERT INTO memories(kind,content,evidence,created_on,expires_on) VALUES(?,?,?,?,?)",
                (
                    item.kind,
                    item.content,
                    evidence,
                    str(date.today()),
                    str(item.expires_on) if item.expires_on else None,
                ),
            ).lastrowid
        return {"id": item_id, **item.model_dump(mode="json")}

    def forget_memory(self, item_id):
        with self.connection() as db:
            changed = db.execute("DELETE FROM memories WHERE id=?", (item_id,)).rowcount
            if changed:
                db.execute("DELETE FROM messages")
            return changed

    def messages(self, limit=100):
        with self.connection() as db:
            rows = db.execute("SELECT * FROM messages ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
            return [{**dict(r), "payload": json.loads(r["payload"])} for r in reversed(rows)]

    def previous_reply(self, request_id):
        with self.connection() as db:
            row = db.execute(
                "SELECT m.* FROM messages m JOIN chat_runs c ON c.reply_id=m.id WHERE c.request_id=?",
                (request_id,),
            ).fetchone()
            return {**dict(row), "payload": json.loads(row["payload"])} if row else None

    def save_turn(self, request_id, message, response, payload):
        now = datetime.now(UTC).isoformat()
        with self.connection() as db:
            db.execute(
                "INSERT INTO messages(role,content,created_at,payload) VALUES(?,?,?,?)",
                ("user", message, now, "{}"),
            )
            reply_id = db.execute(
                "INSERT INTO messages(role,content,created_at,payload) VALUES(?,?,?,?)",
                ("assistant", response, now, json.dumps(payload, ensure_ascii=False)),
            ).lastrowid
            db.execute("INSERT INTO chat_runs VALUES(?,?)", (request_id, reply_id))
        return {
            "id": reply_id,
            "role": "assistant",
            "content": response,
            "created_at": now,
            "payload": payload,
        }

    def clear_chat(self, forget=False):
        with self.connection() as db:
            db.execute("DELETE FROM messages")
            if forget:
                db.execute("DELETE FROM memories")

    def add_plans(self, items):
        with self.connection() as db:
            for item in items:
                db.execute(
                    "INSERT OR IGNORE INTO plans(recipe_id,planned_on,meal) VALUES(?,?,?)",
                    (item.recipe_id, str(item.planned_on), item.meal),
                )
        return {"added_or_existing": len(items)}

    @staticmethod
    def _log_row(row):
        item = dict(row)
        item.pop("batch_id", None)
        item["nutrition_snapshot"] = (
            json.loads(item["nutrition_snapshot"]) if item["nutrition_snapshot"] else None
        )
        return item

    def meal_logs(self):
        with self.connection() as db:
            return [
                self._log_row(r)
                for r in db.execute("SELECT * FROM meal_logs ORDER BY cooked_on DESC,id DESC")
            ]

    def record_meal(self, item, input_text=None):
        fingerprint = hashlib.sha256(
            (input_text or item.model_dump_json(exclude={"request_id"})).encode()
        ).hexdigest()
        # Resolve links and take the nutrition snapshot in the same transaction as the batch.
        with self.connection() as db:
            previous = db.execute(
                "SELECT fingerprint FROM meal_batches WHERE request_id=?", (item.request_id,)
            ).fetchone()
            if previous:
                if previous["fingerprint"] != fingerprint:
                    raise ValueError("这次保存标识已用于另一条记录，请重新提交")
                return [
                    self._log_row(r)
                    for r in db.execute(
                        "SELECT * FROM meal_logs WHERE batch_id=? ORDER BY id", (item.request_id,)
                    )
                ]
            db.execute("INSERT INTO meal_batches VALUES(?,?)", (item.request_id, fingerprint))
            records = []
            for dish in item.dishes:
                r = (
                    db.execute("SELECT payload FROM recipes WHERE id=?", (dish.recipe_id,)).fetchone()
                    if dish.recipe_id
                    else None
                )
                if dish.recipe_id and not r:
                    raise ValueError("关联菜谱已删除，请重新选择")
                nutrition = snapshot(json.loads(r["payload"]), dish.servings_eaten) if r else None
                identifier = db.execute(
                    "INSERT INTO meal_logs(name,recipe_id,servings_eaten,cooked_on,meal,note,nutrition_snapshot,batch_id) VALUES(?,?,?,?,?,?,?,?)",
                    (
                        dish.name,
                        dish.recipe_id,
                        dish.servings_eaten,
                        str(item.cooked_on),
                        item.meal,
                        item.note,
                        json.dumps(nutrition) if nutrition else None,
                        item.request_id,
                    ),
                ).lastrowid
                records.append(
                    self._log_row(db.execute("SELECT * FROM meal_logs WHERE id=?", (identifier,)).fetchone())
                )
            return records

    def update_meal_log(self, identifier, item):
        with self.connection() as db:
            old = db.execute("SELECT * FROM meal_logs WHERE id=?", (identifier,)).fetchone()
            if not old:
                return None
            if old["recipe_id"] == item.recipe_id and old["name"] == item.name and old["nutrition_snapshot"]:
                nutrition = json.loads(old["nutrition_snapshot"]) if item.servings_eaten else None
                if nutrition:
                    ratio = item.servings_eaten / old["servings_eaten"]
                    nutrition["consumed"] = {k: round(v * ratio, 1) for k, v in nutrition["consumed"].items()}
                    nutrition["servings_eaten"] = item.servings_eaten
            else:
                r = (
                    db.execute("SELECT payload FROM recipes WHERE id=?", (item.recipe_id,)).fetchone()
                    if item.recipe_id
                    else None
                )
                if item.recipe_id and not r:
                    raise ValueError("关联菜谱不存在")
                nutrition = snapshot(json.loads(r["payload"]), item.servings_eaten) if r else None
            db.execute("DELETE FROM meal_batches WHERE request_id=?", (old["batch_id"],))
            db.execute(
                "UPDATE meal_logs SET name=?,recipe_id=?,servings_eaten=?,cooked_on=?,meal=?,note=?,nutrition_snapshot=?,batch_id=NULL WHERE id=?",
                (
                    item.name,
                    item.recipe_id,
                    item.servings_eaten,
                    str(item.cooked_on),
                    item.meal,
                    item.note,
                    json.dumps(nutrition) if nutrition else None,
                    identifier,
                ),
            )
            return self._log_row(db.execute("SELECT * FROM meal_logs WHERE id=?", (identifier,)).fetchone())

    def delete_meal_log(self, identifier):
        with self.connection() as db:
            old = db.execute("SELECT batch_id FROM meal_logs WHERE id=?", (identifier,)).fetchone()
            if not old:
                return False
            db.execute("DELETE FROM meal_batches WHERE request_id=?", (old["batch_id"],))
            db.execute("DELETE FROM meal_logs WHERE id=?", (identifier,))
            return True

    def drafts(self):
        with self.connection() as db:
            return [
                {"id": r["id"], "created_at": r["created_at"], **json.loads(r["payload"])}
                for r in db.execute("SELECT * FROM recipe_drafts ORDER BY id DESC")
            ]

    def add_draft(self, item):
        now = datetime.now(UTC).isoformat()
        with self.connection() as db:
            existing = db.execute(
                "SELECT * FROM recipe_drafts WHERE payload=?", (item.model_dump_json(),)
            ).fetchone()
            if existing:
                return {"id": existing["id"], "created_at": existing["created_at"], **item.model_dump()}
            identifier = db.execute(
                "INSERT INTO recipe_drafts(created_at,payload) VALUES(?,?)", (now, item.model_dump_json())
            ).lastrowid
        return {"id": identifier, "created_at": now, **item.model_dump()}

    def delete_draft(self, identifier):
        with self.connection() as db:
            return db.execute("DELETE FROM recipe_drafts WHERE id=?", (identifier,)).rowcount

    def save_capture(self, recipe, draft_id=None):
        from src.collection.web_recipes import source_identity

        with self.connection() as db:
            if recipe.source_url:
                key = source_identity(recipe.source_url)
                for row in db.execute("SELECT * FROM recipes"):
                    payload = json.loads(row["payload"])
                    if payload.get("source_url") and source_identity(payload["source_url"]) == key:
                        if draft_id:
                            db.execute("DELETE FROM recipe_drafts WHERE id=?", (draft_id,))
                        return {"recipe": {"id": row["id"], **payload}, "created": False}
            if recipe.xcf_id:
                existing = db.execute("SELECT * FROM recipes WHERE xcf_id=?", (recipe.xcf_id,)).fetchone()
                if existing:
                    if draft_id:
                        db.execute("DELETE FROM recipe_drafts WHERE id=?", (draft_id,))
                    return {
                        "recipe": {"id": existing["id"], **json.loads(existing["payload"])},
                        "created": False,
                    }
            result = self._write_recipe(db, recipe)
            if draft_id:
                db.execute("DELETE FROM recipe_drafts WHERE id=?", (draft_id,))
            return {"recipe": result, "created": True}

    def update_draft(self, identifier, item):
        with self.connection() as db:
            changed = db.execute(
                "UPDATE recipe_drafts SET payload=? WHERE id=?", (item.model_dump_json(), identifier)
            ).rowcount
            if not changed:
                return None
            row = db.execute("SELECT * FROM recipe_drafts WHERE id=?", (identifier,)).fetchone()
            return {"id": row["id"], "created_at": row["created_at"], **json.loads(row["payload"])}
