from fastapi import APIRouter

router = APIRouter()

@router.get("/")
def test_user_router():
    return {"ok": True, "module": "user"}