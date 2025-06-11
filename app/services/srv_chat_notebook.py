from sqlalchemy.orm import Session
from sqlalchemy.future import select
from app.models.model_message import Message
from app.models.model_thread import Thread
from app.schemas.sche_message import MessageRequest
from app.utils.enums import SenderType
import uuid
from typing import List

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from langgraph.graph import StateGraph, START, MessagesState
from langgraph.checkpoint.memory import MemorySaver
from langchain.vectorstores.faiss import FAISS
from langchain.embeddings import OpenAIEmbeddings
from langchain.embeddings import HuggingFaceEmbeddings

model = ChatOpenAI(model="gpt-4o-mini")
SYSTEM_PROMPT = "You are a helpful assistant. Answer all questions to the best of your ability."

def create_message(
    db: Session, data: MessageRequest, sender: SenderType
) -> Message:
    message = Message(
        thread_id=data.thread_id,
        sender=sender,
        content=data.message,
        meta_info={}
    )
    db.add(message)
    db.commit()
    db.refresh(message)
    return message

def get_chat_history(
    db: Session, thread_id: str, limit: int = 50
) -> List[Message]:
    print(f"Fetching chat history for thread_id: {thread_id} with limit: {limit}")
    
    try:
        result = db.execute(
            select(Message)
            .where(Message.thread_id == thread_id)
            .order_by(Message.created_at.asc())
            .limit(limit)
        )
        messages = result.scalars().all()
        print(f"Query executed, fetched {len(messages)} messages.")
        return messages
    except Exception as e:
        print(f"Error fetching chat history: {e}")
        raise e

def load_vectorstore(thread_id: str) -> FAISS:
    vs_path = f"vectorstore/{thread_id}"
    embeddings = HuggingFaceEmbeddings(model_name="BAAI/bge-m3")
    return FAISS.load_local(vs_path, embeddings, allow_dangerous_deserialization=True)

def get_langgraph_app():
    workflow = StateGraph(state_schema=MessagesState)

    def call_model(state: MessagesState):
        messages = [SystemMessage(content=SYSTEM_PROMPT)] + state["messages"]
        response = model.invoke(messages)
        return {"messages": response}

    workflow.add_node("model", call_model)
    workflow.add_edge(START, "model")
    memory = MemorySaver()
    return workflow.compile(checkpointer=memory)

langgraph_app = get_langgraph_app()

async def chat_with_thread(
    db: Session,
    thread_id: str,
    user_id: str,
    query: str,
    history: List[Message]
) -> str:
    # Load vectorstore
    vectorstore = load_vectorstore(thread_id)
    retriever = vectorstore.as_retriever()
    docs = retriever.invoke(query)
    print(f"docs loaded for thread_id: {docs}")
    context = "\n".join(doc.page_content for doc in docs)
    print(f"Context retrieved: {context}")

    # Tạo danh sách messages từ history
    past_messages = []
    for msg in history:
        if msg.sender == SenderType.user:
            past_messages.append(HumanMessage(content=msg.content))
        else:
            past_messages.append(AIMessage(content=msg.content))

    # Gộp message hiện tại + context
    user_message = f"{query}\n\nContext:\n{context}"
    past_messages.append(HumanMessage(content=user_message))

    # Gọi LangGraph
    result = langgraph_app.invoke(
        {"messages": past_messages},
        config={"configurable": {"thread_id": thread_id}},
    )
    response = result["messages"][-1].content

    # Lưu message user
    db.add(Message(
        thread_id=thread_id,
        sender=SenderType.user,
        content=query,
        meta_info={"context": context}
    ))

    # Lưu message AI
    db.add(Message(
        thread_id=thread_id,
        sender=SenderType.ai,
        content=response,
        meta_info={}
    ))

    db.commit()
    return response
