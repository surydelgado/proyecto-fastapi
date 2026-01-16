

from fastapi import APIRouter

router = APIRouter()

@router.get("/")
def test_event_router():
    return {"ok": True, "module": "event"}
