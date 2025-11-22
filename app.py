from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Optional, List
from krs_service import KRSService

app = FastAPI(title="KRS Service API")

# Use a file DB in the project folder
svc = KRSService(db_path="krs_http.db")

class CourseIn(BaseModel):
    code: str
    name: str
    credits: int
    day: Optional[str] = None
    start_time: Optional[str] = None
    end_time: Optional[str] = None

class EnrollResult(BaseModel):
    ok: bool
    msg: str

@app.on_event("shutdown")
def shutdown_event():
    svc.close()

@app.post("/courses", status_code=201)
def create_course(course: CourseIn):
    svc.add_matakuliah(course.code, course.name, course.credits, course.day, course.start_time, course.end_time)
    return {"ok": True}

@app.get("/courses", response_model=List[CourseIn])
def list_courses():
    cur = svc.conn.cursor()
    cur.execute("SELECT code,name,credits,day,start_time,end_time FROM matakuliah")
    rows = cur.fetchall()
    return [CourseIn(code=r[0], name=r[1], credits=r[2], day=r[3], start_time=r[4], end_time=r[5]) for r in rows]

@app.post("/krs/{nim}/add/{kode_mk}")
def api_add_course(nim: str, kode_mk: str):
    ok, msg = svc.add_course(nim, kode_mk)
    if not ok:
        raise HTTPException(status_code=400, detail=msg)
    return {"ok": True, "msg": msg}

@app.post("/krs/{nim}/remove/{kode_mk}")
def api_remove_course(nim: str, kode_mk: str):
    ok, msg = svc.remove_course(nim, kode_mk)
    if not ok:
        raise HTTPException(status_code=400, detail=msg)
    return {"ok": True}

@app.get("/krs/{nim}/validate")
def api_validate_krs(nim: str):
    errs = svc.validate_krs(nim)
    return {"errors": errs}

@app.post("/krs/{nim}/submit")
def api_submit_krs(nim: str):
    ok, errs = svc.submit_krs(nim)
    if not ok:
        raise HTTPException(status_code=400, detail={"errors": errs})
    return {"ok": True}

@app.post("/krs/{nim}/approve/{dosen_pa_id}")
def api_approve_krs(nim: str, dosen_pa_id: str):
    ok, msg = svc.approve_krs(nim, dosen_pa_id)
    if not ok:
        raise HTTPException(status_code=400, detail=msg)
    return {"ok": True}

@app.post("/grades/{nim}/{kode_mk}")
def api_set_grade(nim: str, kode_mk: str, grade: str):
    svc.set_grade(nim, kode_mk, grade)
    return {"ok": True}

@app.get("/krs/{nim}")
def api_get_krs(nim: str):
    krs_id = svc._get_krs_id(nim)
    if not krs_id:
        return {"courses": []}
    codes = svc.get_enrolled_course_codes(nim)
    courses = [svc._get_course(c)['code'] for c in codes]
    return {"courses": courses}
