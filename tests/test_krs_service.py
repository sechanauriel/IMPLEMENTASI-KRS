import sys
import pathlib
import pytest
# ensure project root is on sys.path so tests can import krs_service
ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from krs_service import add_course, remove_course, validate_krs, submit_krs, approve_krs, KRSException, PrerequisiteError, ScheduleConflictError, SKSLimitError
import sqlite3
from pathlib import Path


def test_add_course_without_prereq_raises():
    # student 2001 exists in sample data; try to add CS102 which requires CS101
    with pytest.raises(PrerequisiteError):
        add_course('2001', 'CS102')


def test_schedule_conflict():
    # add CS101 (Senin 08:00-10:00) then create another course with same slot and try add
    # create a new conflicting matakuliah entry
    import sqlite3
    from krs_service import DB_PATH
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("INSERT INTO matakuliah (kode, nama, sks) VALUES (?, ?, ?)", ('X101', 'Conflicting Course', 3))
    mid = cur.lastrowid
    cur.execute("INSERT INTO jadwal (matakuliah_id, hari, mulai, selesai) VALUES (?, ?, ?, ?)", (mid, 'Senin', '08:30', '09:30'))
    conn.commit()
    conn.close()
    # add CS101 first (no prereq)
    res = add_course('2001', 'CS101')
    assert res['total_sks'] == 3
    # now adding X101 should raise ScheduleConflictError
    with pytest.raises(ScheduleConflictError):
        add_course('2001', 'X101')


def test_sks_limit_property():
    # Try to add many small courses until limit; ensure SKSLimitError raised when exceeding 24
    import sqlite3
    from krs_service import DB_PATH
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    # create 10 small courses 3 SKS each
    codes = []
    for i in range(1, 10):
        code = f'T{i:02d}'
        codes.append(code)
        cur.execute("INSERT INTO matakuliah (kode, nama, sks) VALUES (?, ?, ?)", (code, f'Course {i}', 3))
    conn.commit()
    conn.close()
    total = 0
    last_err = None
    for c in codes:
        try:
            r = add_course('2001', c)
            total = r['total_sks']
            assert total <= 24
        except SKSLimitError as e:
            last_err = e
            break
    assert last_err is not None
