import langchain.schema as lc
from langchain.document_loaders import PyPDFLoader, Docx2txtLoader, WebBaseLoader
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain.vectorstores import FAISS
from langchain.embeddings import HuggingFaceEmbeddings
# Utility: Load single file
def load_file(file_path: str, file_ext: str):
    if file_ext == ".pdf":
        document = PyPDFLoader(file_path).load()
    elif file_ext == ".docx":
        document = Docx2txtLoader(file_path).load()
    else:
        document = []
    return [lc.Document(page_content=document)] if isinstance(document, str) else document

# Utility: Load URL
def load_url(url: str):
    document = WebBaseLoader(url).load()
    return [lc.Document(page_content=document)] if isinstance(document, str) else document

# Utility: Chunk + Embed
def chunk_and_embed(docs):
    splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=250)
    chunks = []
    for document in docs:
        print(f"Processing document: {document}")
        content = document.page_content if hasattr(document, 'page_content') else document['content']
        metadata = document.metadata if hasattr(document, 'metadata') else document.get('metadata', {})
        doc_chunks = splitter.split_text(content)
        for chunk in doc_chunks:
            chunks.append(
                lc.Document(
                    page_content=chunk,
                    metadata=metadata
                )
            )
    embeddings = HuggingFaceEmbeddings(model_name="BAAI/bge-m3")
    vectorstore = FAISS.from_documents(chunks, embeddings)
    return vectorstore

