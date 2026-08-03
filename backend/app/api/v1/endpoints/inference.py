import json
from datetime import datetime
from pathlib import Path

import anyio
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_account
from app.db.session import get_db
from app.models import SysAccount
from app.schemas.common import ok
from app.services.anomaly_client import AnomalyClient
from app.services.ingest import ingest_anomaly_result

router = APIRouter()

MAX_VIDEO_MB = 500


@router.post("/jobs")
async def run_inference_job(
    video: UploadFile = File(...),
    device_id: int = Form(default=0),
    calibration: str = Form(default="{}"),
    db: AsyncSession = Depends(get_db),
    account: SysAccount = Depends(get_current_account),
):
    if not video.filename:
        raise HTTPException(status_code=400, detail="视频文件名为空")

    raw = await video.read()
    if len(raw) > MAX_VIDEO_MB * 1024 * 1024:
        raise HTTPException(status_code=413, detail=f"视频大小超过 {MAX_VIDEO_MB}MB 限制")

    suffix = Path(video.filename).suffix or ".mp4"
    temp_dir = Path("./storage/temp").resolve()
    temp_dir.mkdir(parents=True, exist_ok=True)
    temp_video = temp_dir / f"_inf_{account.account_id}_{datetime.now().strftime('%Y%m%d%H%M%S%f')}{suffix}"
    temp_video.write_bytes(raw)

    try:
        cal = json.loads(calibration) if calibration else {}
        client = AnomalyClient()
        result = await anyio.to_thread.run_sync(client.analyze, str(temp_video), cal)
        summary = await ingest_anomaly_result(
            db,
            result,
            device_id=device_id or None,
            account_id=account.account_id,
            create_work_orders=True,
            video_start=datetime.now(),
        )
    finally:
        if temp_video.exists():
            temp_video.unlink()

    return ok(summary)
