from fastapi import APIRouter, UploadFile, File, Form, Depends, HTTPException
from sqlalchemy.orm import Session
from uuid import UUID, uuid4
from typing import List, Optional
import shutil
import tempfile
from pathlib import Path

from app.schemas.sche_document import DocumentOut
from app.models.model_document import Document
from app.models.model_thread import Thread
from app.models.model_vector_session import VectorSession
from app.core.database import get_db

from app.services.srv_rag import load_file, load_url, chunk_and_embed

router = APIRouter(prefix=f"/document")

# Get documents by thread
@router.get("/thread/{thread_id}", response_model=List[DocumentOut])
def get_documents_by_thread(thread_id: UUID, db: Session = Depends(get_db)):
    docs = db.query(Document).filter(Document.thread_id == thread_id).all()
    return docs

# Upload + Ingest route
@router.post("/upload/ingest")
async def upload_and_ingest(
    thread_id: int = Form(...),
    urls: Optional[List[str]] = Form(None),
    files: Optional[List[UploadFile]] = File(None),
    db: Session = Depends(get_db),
):
    # Kiểm tra thread tồn tại
    thread = db.query(Thread).filter(Thread.id == thread_id).first()
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")
    if not urls and not files:
        return {"message": "No files or URLs provided. Still working as expected."}
    
    all_docs = []
    temp_dir = tempfile.mkdtemp()

    # Load from files
    if files and len(files) > 0:
        for uploaded_file in files:
            file_ext = Path(uploaded_file.filename).suffix.lower()
            file_path = Path(temp_dir) / uploaded_file.filename
            with open(file_path, "wb") as f:
                shutil.copyfileobj(uploaded_file.file, f)
            docs = load_file(str(file_path), file_ext)
            all_docs.extend(docs)

            # Lưu metadata mỗi file
            for doc in docs:
                db_doc = Document(
                    thread_id=thread_id,
                    name=uploaded_file.filename,
                    source_type=file_ext.lstrip('.'),
                    source_info=doc.metadata,
                    content=doc.page_content,
                )
                db.add(db_doc)

    # Load từ URL
    if urls and len(urls) > 0:
        for url in urls:
            url = url.strip()
            docs = load_url(url)
            all_docs.extend(docs)
            for doc in docs:
                db_doc = Document(
                    thread_id=thread_id,
                    name=url,
                    source_type="url",
                    source_info=doc.metadata,
                    content=doc.page_content,
                )
                db.add(db_doc)

    db.commit()

    if not all_docs:
        return {"message": "No valid documents to process."}

    # Chunk + Embed + Save
    vectorstore = chunk_and_embed(all_docs)
    save_path = Path("vectorstore") / str(thread_id)
    save_path.mkdir(parents=True, exist_ok=True)
    vectorstore.save_local(str(save_path))
    
    if db.query(VectorSession).filter(VectorSession.thread_id == thread_id).first():
        # Nếu đã có vectorstore cho thread này, cập nhật lại
        vector_session = db.query(VectorSession).filter(VectorSession.thread_id == thread_id).first()
        vector_session.vector_path = str(save_path)
        vector_session.embed_model = "BAAI/bge-m3"
    else:
        # Tạo mới vectorstore cho thread này
        vector_session = VectorSession(
            thread_id=thread_id,
            vector_path=str(save_path),
            embed_model="BAAI/bge-m3"
        )
        db.add(vector_session)
    # Lưu vector session
    db.commit()
    db.refresh(vector_session)

    return {
        "message": "Documents processed and embedded successfully.",
        "vectorstore_path": str(save_path),
    }
