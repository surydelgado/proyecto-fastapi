from fastapi import APIRouter

router = APIRouter()

@router.get("/")
def test_attendance_router():
    return {"ok": True, "module": "attendance"}