import json

import pytest

from src.cli import main
from src.storage.sqlite import Store


def test_legacy_import_backup_restore_and_validation(tmp_path):
    db = tmp_path / "recipes.db"
    source = tmp_path / "legacy.json"
    recipe = {
        "xcf_id": "123",
        "name": "旧菜谱",
        "materials": [{"name": "鸡蛋", "unit": "2个"}],
        "methods": ["煮熟"],
    }
    source.write_text(json.dumps({"hits": {"hits": [{"_source": recipe}]}}))
    assert main(["--db", str(db), "import-recipes", str(source)]) == 0
    assert main(["--db", str(db), "import-recipes", str(source)]) == 0
    assert len(Store(db).recipes()) == 1
    backup = tmp_path / "backup.json"
    assert main(["--db", str(db), "backup", str(backup)]) == 0
    Store(db).delete("recipes", 1)
    assert main(["--db", str(db), "restore", str(backup), "--replace"]) == 0
    assert Store(db).recipe(1)["name"] == "旧菜谱"
    source.write_text(json.dumps([recipe, {"name": "缺失字段"}]))
    with pytest.raises(SystemExit) as failure:
        main(["--db", str(db), "import-recipes", str(source)])
    assert failure.value.code == 1
    assert len(Store(db).recipes()) == 1
    with pytest.raises(SystemExit):
        main(["--db", str(db), "backup", str(backup)])


def test_empty_init_prevents_demo_seed(tmp_path):
    db = tmp_path / "empty.db"
    main(["--db", str(db), "init", "--no-demo"])
    Store(db).seed([{"name": "不该出现", "materials": [{"name": "米"}], "methods": ["煮"]}])
    assert Store(db).recipes() == []
