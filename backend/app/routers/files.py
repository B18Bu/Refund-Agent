"""文件上传路由：POST /api/tickets/{ticket_id}/files。"""
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.deps import get_current_user, get_db
from app.models import Ticket
from app.schemas import FileUploadResponse, FileUploadResult
from app.storage import save_upload

router = APIRouter(prefix="/api/tickets", tags=["files"])


@router.post("/{ticket_id}/files", response_model=FileUploadResponse)
async def upload_files(
    ticket_id: int,
    files: list[UploadFile] = File(...),
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    t = db.get(Ticket, ticket_id)
    if t is None:
        raise HTTPException(404, "工单不存在")
    if user.id != t.user_id and user.role.value != "sv":
        raise HTTPException(403, "仅工单创建人或主管可上传文件")

    if len(files) > 3:
        raise HTTPException(413, "最多上传 3 张图片")

    results: list[FileUploadResult] = []
    for uf in files:
        meta = await save_upload(uf)
        t.image_paths = (t.image_paths or []) + [meta["storage_key"]]
        results.append(
            FileUploadResult(
                id=len(results) + 1,
                filename=meta["filename"],
                content_type=meta["content_type"],
                size_bytes=meta["size_bytes"],
            )
        )
    db.commit()
    return FileUploadResponse(ticket_id=ticket_id, files=results)
