import pytest
import tempfile
import shutil
from pathlib import Path
import sqlite3


@pytest.fixture(autouse=True)
def temp_db(tmp_path, monkeypatch):
    # create a temporary DB by applying schema.sql
    root = Path(__file__).parent.parent
    schema = root / 'schema.sql'
    db_path = tmp_path / 'krs.db'
    conn = sqlite3.connect(db_path)
    sql = schema.read_text(encoding='utf-8')
    conn.executescript(sql)
    conn.commit()
    conn.close()
    # monkeypatch DB path in krs_service
    import krs_service
    monkeypatch.setattr(krs_service, 'DB_PATH', db_path)
    yield
    # cleanup
    try:
        db_path.unlink()
    except Exception:
        pass
