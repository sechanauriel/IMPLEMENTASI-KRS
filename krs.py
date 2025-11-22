
import json
import os
from typing import Dict, List, Optional, Any

# HTTP server (require installed dependencies)
from fastapi import FastAPI, HTTPException
from fastapi.openapi.docs import get_swagger_ui_html, get_swagger_ui_oauth2_redirect_html
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import uvicorn
_HAS_FASTAPI = True

DATA_FILE = "krs_data.json"

class Student:
    def __init__(self, student_id: str, name: str):
        self.student_id = student_id
        self.name = name

    def to_dict(self):
        return {"student_id": self.student_id, "name": self.name}

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> 'Student':
        return Student(d["student_id"], d["name"])

class Course:
    def __init__(self, code: str, name: str, credits: int):
        self.code = code
        self.name = name
        self.credits = credits

    def to_dict(self):
        return {"code": self.code, "name": self.name, "credits": self.credits}

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> 'Course':
        return Course(d["code"], d["name"], d["credits"])

class KRSManager:
    def __init__(self):
        self.students: Dict[str, Student] = {}
        self.courses: Dict[str, Course] = {}
        # enrollments: student_id -> list of course codes
        self.enrollments: Dict[str, List[str]] = {}
        # krs_status: student_id -> one of 'draft', 'submitted', 'approved'
        self.krs_status: Dict[str, str] = {}
        # approvals: student_id -> approver id (dosen PA) when approved
        self.krs_approvals: Dict[str, Optional[str]] = {}

    # Student operations
    def add_student(self, student_id: str, name: str) -> bool:
        if student_id in self.students:
            return False
        self.students[student_id] = Student(student_id, name)
        self.enrollments[student_id] = []
        # initialize KRS status for new student
        self.krs_status[student_id] = "draft"
        self.krs_approvals[student_id] = None
        return True

    def remove_student(self, student_id: str) -> bool:
        if student_id not in self.students:
            return False
        del self.students[student_id]
        if student_id in self.enrollments:
            del self.enrollments[student_id]
        if student_id in self.krs_status:
            del self.krs_status[student_id]
        if student_id in self.krs_approvals:
            del self.krs_approvals[student_id]
        return True

    # Course operations
    def add_course(self, code: str, name: str, credits: int) -> bool:
        if code in self.courses:
            return False
        self.courses[code] = Course(code, name, credits)
        return True

    def remove_course(self, code: str) -> bool:
        if code not in self.courses:
            return False
        del self.courses[code]
        # remove course from all enrollments
        for sid, lst in self.enrollments.items():
            if code in lst:
                lst.remove(code)
        # if enrollments changed, ensure statuses remain appropriate (keep as-is)
        return True

    # Enrollment operations
    def enroll(self, student_id: str, course_code: str) -> str:
        if student_id not in self.students:
            return "student_not_found"
        if course_code not in self.courses:
            return "course_not_found"
        if course_code in self.enrollments.get(student_id, []):
            return "already_enrolled"
        self.enrollments[student_id].append(course_code)
        return "ok"

    def drop(self, student_id: str, course_code: str) -> str:
        if student_id not in self.students:
            return "student_not_found"
        if course_code not in self.courses:
            return "course_not_found"
        if course_code not in self.enrollments.get(student_id, []):
            return "not_enrolled"
        self.enrollments[student_id].remove(course_code)
        return "ok"

    def get_student_courses(self, student_id: str) -> List[Course]:
        codes = self.enrollments.get(student_id, [])
        return [self.courses[c] for c in codes if c in self.courses]

    def get_course_students(self, course_code: str) -> List[Student]:
        s = []
        for sid, lst in self.enrollments.items():
            if course_code in lst and sid in self.students:
                s.append(self.students[sid])
        return s

    # KRS lifecycle operations
    def validate_krs(self, student_id: str) -> Dict[str, Any]:
        """Validate KRS rules for a student.
        Rules implemented:
        - student must exist
        - all enrolled course codes must exist
        - total SKS (credits) must be <= 24
        - at least 1 course when submitting (validation still returns errors if none)
        Returns: {"valid": bool, "errors": [str], "total_credits": int}
        """
        errors: List[str] = []
        if student_id not in self.students:
            return {"valid": False, "errors": ["student_not_found"], "total_credits": 0}
        codes = self.enrollments.get(student_id, [])
        total = 0
        seen = set()
        for c in codes:
            if c in seen:
                errors.append(f"duplicate_course:{c}")
                continue
            seen.add(c)
            if c not in self.courses:
                errors.append(f"course_not_found:{c}")
            else:
                total += self.courses[c].credits

        if total == 0:
            errors.append("no_courses_selected")
        if total > 24:
            errors.append("exceeds_max_credits")

        return {"valid": len(errors) == 0, "errors": errors, "total_credits": total}

    def submit_krs(self, student_id: str) -> str:
        """Attempt to change status draft->submitted after validation."""
        v = self.validate_krs(student_id)
        if not v.get("valid", False):
            return "validation_failed"
        # mark submitted
        self.krs_status[student_id] = "submitted"
        self.krs_approvals[student_id] = None
        self.save()
        return "submitted"

    def approve_krs(self, student_id: str, dosen_pa_id: str) -> str:
        """Approve a submitted KRS by dosen PA; status becomes 'approved'."""
        if student_id not in self.students:
            return "student_not_found"
        current = self.krs_status.get(student_id, "draft")
        if current != "submitted":
            return "not_submitted"
        # approve
        self.krs_status[student_id] = "approved"
        self.krs_approvals[student_id] = dosen_pa_id
        self.save()
        return "approved"

    # Persistence
    def save(self, filepath: str = DATA_FILE):
        data = {
            "students": [s.to_dict() for s in self.students.values()],
            "courses": [c.to_dict() for c in self.courses.values()],
            "enrollments": self.enrollments,
            "krs_status": self.krs_status,
            "krs_approvals": self.krs_approvals,
        }
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def load(self, filepath: str = DATA_FILE):
        if not os.path.exists(filepath):
            return
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        self.students = {d["student_id"]: Student.from_dict(d) for d in data.get("students", [])}
        self.courses = {d["code"]: Course.from_dict(d) for d in data.get("courses", [])}
        self.enrollments = data.get("enrollments", {})
        self.krs_status = data.get("krs_status", {})
        self.krs_approvals = data.get("krs_approvals", {})
        # Ensure enrollments has entries for students
        for sid in list(self.students.keys()):
            if sid not in self.enrollments:
                self.enrollments[sid] = []
            if sid not in self.krs_status:
                self.krs_status[sid] = "draft"
            if sid not in self.krs_approvals:
                self.krs_approvals[sid] = None


def print_menu():
    print("\n== Modul KRS Sederhana ==")
    print("1. Tambah mahasiswa")
    print("2. Tambah mata kuliah")
    print("3. Daftarkan mahasiswa ke MK (KRS)")
    print("4. Batalkan pendaftaran mahasiswa dari MK")
    print("5. Tampilkan KRS mahasiswa")
    print("6. Tampilkan daftar mahasiswa pada MK")
    print("7. Simpan data")
    print("8. Muat data")
    print("9. Hapus mahasiswa")
    print("10. Hapus mata kuliah")
    print("0. Keluar")


def input_nonempty(prompt: str) -> str:
    while True:
        v = input(prompt).strip()
        if v:
            return v
        print("Masukan tidak boleh kosong.")


def main():
    mgr = KRSManager()
    # try load existing
    mgr.load()

    while True:
        print_menu()
        choice = input("Pilih (0-10): ").strip()
        if choice == "1":
            sid = input_nonempty("ID mahasiswa: ")
            name = input_nonempty("Nama: ")
            ok = mgr.add_student(sid, name)
            print("Berhasil menambah mahasiswa." if ok else "Gagal: ID sudah ada.")
        elif choice == "2":
            code = input_nonempty("Kode MK: ")
            name = input_nonempty("Nama MK: ")
            while True:
                try:
                    credits = int(input_nonempty("SKS (angka): "))
                    break
                except ValueError:
                    print("Masukan SKS harus angka.")
            ok = mgr.add_course(code, name, credits)
            print("Berhasil menambah mata kuliah." if ok else "Gagal: Kode MK sudah ada.")
        elif choice == "3":
            sid = input_nonempty("ID mahasiswa: ")
            code = input_nonempty("Kode MK: ")
            res = mgr.enroll(sid, code)
            msgs = {
                "student_not_found": "Mahasiswa tidak ditemukan.",
                "course_not_found": "Mata kuliah tidak ditemukan.",
                "already_enrolled": "Mahasiswa sudah terdaftar pada MK ini.",
                "ok": "Pendaftaran berhasil."}
            print(msgs.get(res, "Kesalahan."))
        elif choice == "4":
            sid = input_nonempty("ID mahasiswa: ")
            code = input_nonempty("Kode MK: ")
            res = mgr.drop(sid, code)
            msgs = {
                "student_not_found": "Mahasiswa tidak ditemukan.",
                "course_not_found": "Mata kuliah tidak ditemukan.",
                "not_enrolled": "Mahasiswa tidak terdaftar pada MK ini.",
                "ok": "Pembatalan berhasil."}
            print(msgs.get(res, "Kesalahan."))
        elif choice == "5":
            sid = input_nonempty("ID mahasiswa: ")
            if sid not in mgr.students:
                print("Mahasiswa tidak ditemukan.")
            else:
                courses = mgr.get_student_courses(sid)
                if not courses:
                    print("Belum terdaftar pada mata kuliah apapun.")
                else:
                    print(f"KRS untuk {mgr.students[sid].name} ({sid}):")
                    total_sks = 0
                    for c in courses:
                        print(f"- {c.code}: {c.name} ({c.credits} SKS)")
                        total_sks += c.credits
                    print(f"Total SKS: {total_sks}")
        elif choice == "6":
            code = input_nonempty("Kode MK: ")
            if code not in mgr.courses:
                print("Mata kuliah tidak ditemukan.")
            else:
                students = mgr.get_course_students(code)
                if not students:
                    print("Belum ada mahasiswa terdaftar pada MK ini.")
                else:
                    print(f"Daftar mahasiswa pada {mgr.courses[code].name} ({code}):")
                    for s in students:
                        print(f"- {s.student_id}: {s.name}")
        elif choice == "7":
            mgr.save()
            print(f"Data disimpan ke {DATA_FILE}.")
        elif choice == "8":
            mgr.load()
            print(f"Data dimuat dari {DATA_FILE} jika ada.")
        elif choice == "9":
            sid = input_nonempty("ID mahasiswa yang dihapus: ")
            ok = mgr.remove_student(sid)
            print("Mahasiswa dihapus." if ok else "Mahasiswa tidak ditemukan.")
        elif choice == "10":
            code = input_nonempty("Kode MK yang dihapus: ")
            ok = mgr.remove_course(code)
            print("Mata kuliah dihapus." if ok else "Mata kuliah tidak ditemukan.")
        elif choice == "0":
            print("Keluar. Menyimpan data...")
            mgr.save()
            break
        else:
            print("Pilihan tidak valid. Coba lagi.")


# --- HTTP / API integration ---
if _HAS_FASTAPI:
    # disable the default /docs/redoc so we can serve our own (local assets)
    app = FastAPI(title="KRS Service", docs_url=None, redoc_url=None)

    class StudentIn(BaseModel):
        student_id: str
        name: str

    class CourseIn(BaseModel):
        code: str
        name: str
        credits: int

    class EnrollReq(BaseModel):
        student_id: str
        course_code: str

    # manager instance for server
    _mgr = KRSManager()
    _mgr.load()

    # serve local static files (Swagger UI assets) from ./static
    app.mount("/static", StaticFiles(directory="static"), name="static")

    @app.get("/")
    def health():
        return {"status": "ok"}

    @app.get("/students")
    def list_students():
        return [s.to_dict() for s in _mgr.students.values()]

    @app.post("/students", status_code=201)
    def create_student(s: StudentIn):
        ok = _mgr.add_student(s.student_id, s.name)
        if not ok:
            raise HTTPException(status_code=400, detail="student_exists")
        _mgr.save()
        return {"status": "created"}

    @app.get("/students/{student_id}/courses")
    def get_student_courses(student_id: str):
        if student_id not in _mgr.students:
            raise HTTPException(status_code=404, detail="student_not_found")
        courses = _mgr.get_student_courses(student_id)
        return [c.to_dict() for c in courses]

    @app.get("/courses")
    def list_courses():
        return [c.to_dict() for c in _mgr.courses.values()]

    @app.post("/courses", status_code=201)
    def create_course(c: CourseIn):
        ok = _mgr.add_course(c.code, c.name, c.credits)
        if not ok:
            raise HTTPException(status_code=400, detail="course_exists")
        _mgr.save()
        return {"status": "created"}

    @app.post("/enroll")
    def enroll(req: EnrollReq):
        res = _mgr.enroll(req.student_id, req.course_code)
        if res != "ok":
            # map to HTTP errors
            if res == "student_not_found":
                raise HTTPException(status_code=404, detail=res)
            if res == "course_not_found":
                raise HTTPException(status_code=404, detail=res)
            if res == "already_enrolled":
                raise HTTPException(status_code=400, detail=res)
            raise HTTPException(status_code=400, detail=res)
        _mgr.save()
        return {"status": "ok"}

    @app.delete("/enroll")
    def drop(req: EnrollReq):
        res = _mgr.drop(req.student_id, req.course_code)
        if res != "ok":
            if res == "student_not_found" or res == "course_not_found":
                raise HTTPException(status_code=404, detail=res)
            if res == "not_enrolled":
                raise HTTPException(status_code=400, detail=res)
            raise HTTPException(status_code=400, detail=res)
        _mgr.save()
        return {"status": "ok"}

    @app.post("/save")
    def save_data():
        _mgr.save()
        return {"status": "saved"}

    @app.post("/load")
    def load_data():
        _mgr.load()
        return {"status": "loaded"}

    class ApproveReq(BaseModel):
        dosen_pa_id: str

    @app.post("/krs/validate/{student_id}")
    def api_validate_krs(student_id: str):
        res = _mgr.validate_krs(student_id)
        if not res.get("valid", False):
            return {"status": "invalid", **res}
        return {"status": "valid", **res}

    @app.post("/krs/submit/{student_id}")
    def api_submit_krs(student_id: str):
        result = _mgr.submit_krs(student_id)
        if result == "validation_failed":
            raise HTTPException(status_code=400, detail="validation_failed")
        return {"status": result}

    @app.post("/krs/approve/{student_id}")
    def api_approve_krs(student_id: str, req: ApproveReq):
        result = _mgr.approve_krs(student_id, req.dosen_pa_id)
        if result == "student_not_found":
            raise HTTPException(status_code=404, detail=result)
        if result == "not_submitted":
            raise HTTPException(status_code=400, detail=result)
        return {"status": result}

    # Explicit Swagger UI endpoints (serve HTML even if template engines differ)
    @app.get("/docs", include_in_schema=False)
    def custom_swagger_ui_html():
        return get_swagger_ui_html(
            openapi_url="/openapi.json",
            title="KRS Service - Swagger UI",
            swagger_js_url="/static/swagger-ui-bundle.js",
            swagger_css_url="/static/swagger-ui.css",
        )

    @app.get("/docs/oauth2-redirect", include_in_schema=False)
    def swagger_ui_redirect():
        return get_swagger_ui_oauth2_redirect_html()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="KRS CLI and HTTP server")
    parser.add_argument("--serve", action="store_true", help="Run HTTP server at localhost:8000")
    parser.add_argument("--host", default="127.0.0.1", help="Host for HTTP server")
    parser.add_argument("--port", type=int, default=8000, help="Port for HTTP server")
    args = parser.parse_args()

    if args.serve:
        if not _HAS_FASTAPI:
            print("FastAPI/uvicorn not installed. Install from requirements.txt or pip install fastapi uvicorn")
        else:
            print(f"Starting HTTP server at http://{args.host}:{args.port}")
            uvicorn.run(app, host=args.host, port=args.port, reload=False)
    else:
        main()
