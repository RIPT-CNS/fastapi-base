from pydantic import BaseModel

class VectorSessionCreate (BaseModel):
    thread_id: int
    # Đường dẫn mặc định là vectorstore, nếu truyền vào none thì sẽ sử dụng đường dẫn mặc định
    vector_path: str = "vectorstore"
    embed_model: str = "BAAI/bge-m3"  # Mặc định là BAAI/bge-m3, có thể thay đổi nếu cần

class VectorSessionOut (BaseModel):
    id: int
    thread_id: int
    vector_path: str
    embed_model: str = "BAAI/bge-m3"  # Mặc định là BAAI/bge-m3, có thể thay đổi nếu cần

    class Config:
        orm_mode = True  # Cho phép chuyển đổi từ ORM model sang Pydantic model