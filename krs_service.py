import sqlite3
from typing import List, Tuple, Optional

DB_SCHEMA = [
    """
    CREATE TABLE IF NOT EXISTS matakuliah (
        code TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        credits INTEGER NOT NULL,
        day TEXT,            -- e.g. 'Mon', 'Tue'
        start_time TEXT,     -- 'HH:MM'
        end_time TEXT        -- 'HH:MM'
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS prerequisite (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        kode_mk TEXT NOT NULL,
        prereq_kode TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS krs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nim TEXT NOT NULL,
        semester TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'draft', -- draft, submitted, approved
        dosen_pa_id TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS krs_detail (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        krs_id INTEGER NOT NULL,
        kode_mk TEXT NOT NULL,
        FOREIGN KEY(krs_id) REFERENCES krs(id),
        FOREIGN KEY(kode_mk) REFERENCES matakuliah(code)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS grades (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nim TEXT NOT NULL,
        kode_mk TEXT NOT NULL,
        grade TEXT NOT NULL -- A,B,C,D,E,F
    )
    """,
]

PASSING_GRADES = {"A", "B", "C"}

class KRSService:
    def __init__(self, db_path: str = "krs.db", semester: str = "2025-1"):
        self.db_path = db_path
        self.semester = semester
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self):
        cur = self.conn.cursor()
        for s in DB_SCHEMA:
            cur.execute(s)
        self.conn.commit()

    # Helper: create KRS if none exists (draft)
    def _ensure_krs(self, nim: str) -> int:
        cur = self.conn.cursor()
        cur.execute("SELECT id FROM krs WHERE nim=? AND semester=?", (nim, self.semester))
        row = cur.fetchone()
        if row:
            return row[0]
        cur.execute("INSERT INTO krs(nim, semester, status) VALUES(?,?, 'draft')", (nim, self.semester))
        self.conn.commit()
        return cur.lastrowid

    # Course CRUD for test setup
    def add_matakuliah(self, code: str, name: str, credits: int, day: Optional[str] = None, start_time: Optional[str] = None, end_time: Optional[str] = None):
        cur = self.conn.cursor()
        cur.execute("INSERT OR REPLACE INTO matakuliah(code,name,credits,day,start_time,end_time) VALUES(?,?,?,?,?,?)",
                    (code, name, credits, day, start_time, end_time))
        self.conn.commit()

    def add_prerequisite(self, kode_mk: str, prereq_kode: str):
        cur = self.conn.cursor()
        cur.execute("INSERT INTO prerequisite(kode_mk, prereq_kode) VALUES(?,?)", (kode_mk, prereq_kode))
        self.conn.commit()

    def set_grade(self, nim: str, kode_mk: str, grade: str):
        cur = self.conn.cursor()
        cur.execute("INSERT INTO grades(nim,kode_mk,grade) VALUES(?,?,?)", (nim, kode_mk, grade))
        self.conn.commit()

    def _get_krs_id(self, nim: str) -> Optional[int]:
        cur = self.conn.cursor()
        cur.execute("SELECT id FROM krs WHERE nim=? AND semester=?", (nim, self.semester))
        row = cur.fetchone()
        return row[0] if row else None

    def get_enrolled_course_codes(self, nim: str) -> List[str]:
        krs_id = self._get_krs_id(nim)
        if not krs_id:
            return []
        cur = self.conn.cursor()
        cur.execute("SELECT kode_mk FROM krs_detail WHERE krs_id=?", (krs_id,))
        return [r[0] for r in cur.fetchall()]

    def _get_course(self, code: str):
        cur = self.conn.cursor()
        cur.execute("SELECT * FROM matakuliah WHERE code=?", (code,))
        return cur.fetchone()

    def add_course(self, nim: str, kode_mk: str) -> Tuple[bool, str]:
        # Ensure course exists
        course = self._get_course(kode_mk)
        if not course:
            return False, "course_not_found"
        krs_id = self._ensure_krs(nim)
        # check double enrollment
        cur = self.conn.cursor()
        cur.execute("SELECT 1 FROM krs_detail WHERE krs_id=? AND kode_mk=?", (krs_id, kode_mk))
        if cur.fetchone():
            return False, "already_enrolled"
        # check schedule conflict
        enrolled = self.get_enrolled_course_codes(nim)
        for ecode in enrolled:
            ec = self._get_course(ecode)
            if self._schedule_conflict_rows(course, ec):
                return False, "schedule_conflict"
        # check total SKS
        total = self._total_credits_for_codes(enrolled) + course["credits"]
        if total > 24:
            return False, "exceed_sks"
        # check prerequisites
        missing = self._missing_prereqs(nim, kode_mk)
        if missing:
            return False, "prereq_not_met"
        cur.execute("INSERT INTO krs_detail(krs_id,kode_mk) VALUES(?,?)", (krs_id, kode_mk))
        self.conn.commit()
        return True, "ok"

    def remove_course(self, nim: str, kode_mk: str) -> Tuple[bool, str]:
        krs_id = self._get_krs_id(nim)
        if not krs_id:
            return False, "krs_not_found"
        cur = self.conn.cursor()
        cur.execute("DELETE FROM krs_detail WHERE krs_id=? AND kode_mk=?", (krs_id, kode_mk))
        self.conn.commit()
        return True, "ok"

    def _total_credits_for_codes(self, codes: List[str]) -> int:
        if not codes:
            return 0
        cur = self.conn.cursor()
        q = f"SELECT SUM(credits) FROM matakuliah WHERE code IN ({','.join(['?']*len(codes))})"
        cur.execute(q, tuple(codes))
        row = cur.fetchone()
        return row[0] or 0

    def _missing_prereqs(self, nim: str, kode_mk: str) -> List[str]:
        # returns list of prereq codes not satisfied
        cur = self.conn.cursor()
        cur.execute("SELECT prereq_kode FROM prerequisite WHERE kode_mk=?", (kode_mk,))
        prereqs = [r[0] for r in cur.fetchall()]
        missing = []
        for p in prereqs:
            # check grades for nim on p
            cur.execute("SELECT grade FROM grades WHERE nim=? AND kode_mk=?", (nim, p))
            row = cur.fetchone()
            if not row or row[0] not in PASSING_GRADES:
                missing.append(p)
        return missing

    def _schedule_conflict_rows(self, a, b) -> bool:
        # a and b are sqlite Row objects that may have day/start_time/end_time
        if not a or not b:
            return False
        if not a["day"] or not b["day"]:
            return False
        if a["day"] != b["day"]:
            return False
        try:
            a_start = self._time_to_minutes(a["start_time"]) if a["start_time"] else None
            a_end = self._time_to_minutes(a["end_time"]) if a["end_time"] else None
            b_start = self._time_to_minutes(b["start_time"]) if b["start_time"] else None
            b_end = self._time_to_minutes(b["end_time"]) if b["end_time"] else None
        except Exception:
            return False
        if a_start is None or a_end is None or b_start is None or b_end is None:
            return False
        return not (a_end <= b_start or b_end <= a_start)

    def _time_to_minutes(self, t: str) -> int:
        h, m = t.split(":")
        return int(h) * 60 + int(m)

    def validate_krs(self, nim: str) -> List[str]:
        errors = []
        codes = self.get_enrolled_course_codes(nim)
        # SKS total
        total = self._total_credits_for_codes(codes)
        if total > 24:
            errors.append("exceed_sks")
        # Duplicate check
        if len(codes) != len(set(codes)):
            errors.append("duplicate_mk")
        # Prereqs
        for code in codes:
            missing = self._missing_prereqs(nim, code)
            if missing:
                errors.append(f"prereq_missing:{code}")
        # Schedule conflicts
        rows = [self._get_course(c) for c in codes]
        n = len(rows)
        for i in range(n):
            for j in range(i + 1, n):
                if self._schedule_conflict_rows(rows[i], rows[j]):
                    errors.append(f"schedule_conflict:{rows[i]['code']}:{rows[j]['code']}")
        return errors

    def submit_krs(self, nim: str) -> Tuple[bool, List[str]]:
        errs = self.validate_krs(nim)
        if errs:
            return False, errs
        krs_id = self._get_krs_id(nim)
        if not krs_id:
            return False, ["krs_not_found"]
        cur = self.conn.cursor()
        cur.execute("UPDATE krs SET status='submitted' WHERE id=?", (krs_id,))
        self.conn.commit()
        return True, []

    def approve_krs(self, nim: str, dosen_pa_id: str) -> Tuple[bool, str]:
        krs_id = self._get_krs_id(nim)
        if not krs_id:
            return False, "krs_not_found"
        cur = self.conn.cursor()
        cur.execute("SELECT status FROM krs WHERE id=?", (krs_id,))
        status = cur.fetchone()[0]
        if status != 'submitted':
            return False, "krs_not_submitted"
        cur.execute("UPDATE krs SET status='approved', dosen_pa_id=? WHERE id=?", (dosen_pa_id, krs_id))
        self.conn.commit()
        return True, "ok"

    def close(self):
        self.conn.close()


if __name__ == '__main__':
    svc = KRSService(':memory:')
    # sample quick demo for manual run
    svc.add_matakuliah('MK001', 'Algoritma', 3, 'Mon', '09:00', '10:30')
    svc.add_matakuliah('MK002', 'Struktur Data', 3, 'Mon', '10:30', '12:00')
    nim = '12345'
    ok, msg = svc.add_course(nim, 'MK001')
    print(ok, msg)
    ok, msg = svc.add_course(nim, 'MK002')
    print(ok, msg)
    print('Validation:', svc.validate_krs(nim))
    svc.close()
