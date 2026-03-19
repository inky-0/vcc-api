"""VCC API — receives card details from Chrome extension, inserts ×2 into Railway DB."""
import os
from fastapi import FastAPI, HTTPException, Header
from pydantic import BaseModel
from typing import Optional
import asyncpg

DB_URL = os.environ["DATABASE_URL"]
API_KEY = os.environ["VCC_API_KEY"]

app = FastAPI()
_pool = None

async def get_pool():
    global _pool
    if not _pool:
        _pool = await asyncpg.create_pool(DB_URL, min_size=1, max_size=5)
    return _pool

@app.on_event("startup")
async def startup():
    await get_pool()

@app.get("/health")
async def health():
    return {"ok": True}

class VCCPayload(BaseModel):
    number: str
    exp_month: str
    exp_year: str
    cvv: str
    zip: str = "33432"
    nickname: Optional[str] = None

@app.post("/add_vcc")
async def add_vcc(payload: VCCPayload, x_api_key: str = Header(...)):
    if x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")

    # Build raw_line for compatibility
    raw = f"{payload.number}|{payload.exp_month}|{payload.exp_year}|{payload.cvv}|{payload.zip}"

    pool = await get_pool()
    async with pool.acquire() as conn:
        # Check for duplicate
        existing = await conn.fetchval(
            "SELECT COUNT(*) FROM vccs WHERE card_number = $1 AND status = 'fresh'",
            payload.number
        )
        if existing > 0:
            return {"ok": False, "message": "Card already in DB"}

        # Insert ×2 (puff-bot consumes both copies atomically)
        await conn.executemany(
            """INSERT INTO vccs (card_number, exp_month, exp_year, cvv, zip, raw_line, status, created_at, updated_at)
               VALUES ($1, $2, $3, $4, $5, $6, 'fresh', NOW(), NOW())""",
            [
                (payload.number, payload.exp_month, payload.exp_year, payload.cvv, payload.zip, raw),
                (payload.number, payload.exp_month, payload.exp_year, payload.cvv, payload.zip, raw),
            ]
        )

    print(f"[VCC] Inserted ×2: ...{payload.number[-4:]}")
    return {"ok": True, "message": f"Card ...{payload.number[-4:]} added ×2"}
