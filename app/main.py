from fastapi import FastAPI, Request, HTTPException
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field
from typing import List, Dict, Any

from agent.agent import agent_executor

app = FastAPI(
    title="MetroPet AI Agent",
    description="An AI agent for Taipei Metro.",
    version="1.0.0"
)

templates = Jinja2Templates(directory="templates")

# 【修正】定義更完整的請求與回應模型，以支援對話歷史
class ChatHistory(BaseModel):
    role: str
    content: str

class ChatRequest(BaseModel):
    message: str
    chat_history: List[ChatHistory] = Field(default_factory=list)

class ChatResponse(BaseModel):
    response: str
    chat_history: List[Dict[str, Any]]

@app.get("/", response_class=HTMLResponse)
async def get_root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.post("/chat", response_model=ChatResponse)
async def chat_with_agent(request: ChatRequest):
    try:
        # 將 Pydantic 模型轉換為 LangChain 需要的格式
        history_tuples = [(item.role, item.content) for item in request.chat_history]

        # 【✨ 核心修正】將前端傳來的 chat_history 傳遞給 agent
        result = await agent_executor.ainvoke({
            "input": request.message,
            "chat_history": history_tuples
        })

        # 更新對話歷史
        updated_history = request.chat_history + [
            ChatHistory(role="user", content=request.message),
            ChatHistory(role="assistant", content=result['output'])
        ]
        
        # 將 Pydantic 模型轉回字典列表以便 JSON 序列化
        history_dicts = [item.model_dump() for item in updated_history]

        return ChatResponse(
            response=result['output'],
            chat_history=history_dicts
        )
    except Exception as e:
        print(f"Agent 執行出錯: {e}")
        raise HTTPException(status_code=500, detail="抱歉，我現在有點問題，請稍後再試。")