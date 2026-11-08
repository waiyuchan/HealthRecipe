"""Offline maintenance and migration: python -m src.cli --help."""

import argparse
import json
import os
import sqlite3
from pathlib import Path

from pydantic import ValidationError

from src.models import Backup, Recipe
from src.storage.sqlite import Store

ROOT = Path(__file__).resolve().parents[1]


def main(argv=None):
    parser = argparse.ArgumentParser(description="HealthRecipe 数据维护工具")
    parser.add_argument("--db", default=os.getenv("HEALTHRECIPE_DB", str(ROOT / "data/healthrecipe.db")))
    commands = parser.add_subparsers(dest="command", required=True)
    init = commands.add_parser("init", help="初始化数据库")
    init.add_argument("--no-demo", action="store_true", help="不添加示例菜谱")
    backup = commands.add_parser("backup", help="导出完整 JSON 备份（不覆盖已有文件）")
    backup.add_argument("file", type=Path)
    restore = commands.add_parser("restore", help="恢复完整备份")
    restore.add_argument("file", type=Path)
    restore.add_argument("--replace", action="store_true", required=True, help="确认替换全部当前数据")
    imp = commands.add_parser("import-recipes", help="导入菜谱 JSON 数组或 Elasticsearch hits.hits 导出")
    imp.add_argument("file", type=Path)
    args = parser.parse_args(argv)
    try:
        store = Store(args.db)
        if args.command == "init":
            store.seed([] if args.no_demo else json.loads((ROOT / "data/recipes.json").read_text()))
            print(f"已初始化：{args.db}")
        elif args.command == "backup":
            # Exclusive creation avoids accidentally losing an older backup.
            with args.file.open("x", encoding="utf-8") as target:
                json.dump(store.export(), target, ensure_ascii=False, indent=2)
            print(f"备份已写入：{args.file}")
        elif args.command == "restore":
            data = Backup.model_validate_json(args.file.read_text(encoding="utf-8"))
            store.restore(data)
            print(
                f"已恢复 {len(data.recipes)} 道菜谱、{len(data.history)} 条手记、{len(data.plans)} 道餐单安排"
            )
        elif args.command == "import-recipes":
            data = json.loads(args.file.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                data = data.get("hits", {}).get("hits", data.get("recipes"))
            if not isinstance(data, list):
                raise ValueError("需要菜谱 JSON 数组、完整备份或 Elasticsearch hits.hits 结构")
            items = []
            for item in data:
                raw = dict(item.get("_source", item))
                raw.pop("id", None)
                items.append(Recipe.model_validate(raw))
            store.import_recipes(items)
            print(f"已导入 {len(items)} 道菜谱；相同下厨房 ID 会更新，普通菜谱会新增")
    except (OSError, ValueError, ValidationError, sqlite3.Error) as exc:
        parser.exit(1, f"操作失败：{exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
