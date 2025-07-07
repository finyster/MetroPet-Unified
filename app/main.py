# app/app.py

import sys
import os
from typing import List, Dict, Any

# 將專案根目錄手動加入 Python 的搜尋路徑，確保能找到 agent 和 services
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI
from pydantic import BaseModel
# 導入我們在 agent/agent.py 中建立好的 agent_executor
from agent.agent import agent_executor

# 初始化 FastAPI App
app = FastAPI(
    title="捷米 AI 助理 API (本地版)",
    description="一個完全使用本地 CSV 資料運作的捷運問答 API。",
    version="1.0.0-local",
)

class ChatRequest(BaseModel):
    message: str
    chat_history: List[Dict[str, Any]] = []

class ChatResponse(BaseModel):
    answer: str

@app.post("/chat", response_model=ChatResponse)
async def chat_with_agent(request: ChatRequest):
    print(f"--- 收到使用者請求: message='{request.message}' ---")
    
    # 我們把 chat_history 也傳進去，這讓 AI 能夠記得上下文
    response = agent_executor.invoke({
        "input": request.message,
        "chat_history": request.chat_history
    })
    
    return ChatResponse(answer=response["output"])

@app.get("/")
async def root():
    return {"message": "歡迎使用捷米 AI 助理 API (本地版)！請訪問 /docs 查看 API。"}