# app/main.py

from fastapi import FastAPI, Request
# 【修正】從 fastapi.templating 導入 Jinja2Templates
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from agent.agent import agent_executor

# 初始化 FastAPI 應用
app = FastAPI(
    title="MetroPet AI Agent",
    description="An AI agent for Taipei Metro.",
    version="1.0.0"
)

# 設定樣板目錄，FastAPI 會從這裡找你的 index.html
templates = Jinja2Templates(directory="templates")

# 定義 API 的請求和回應格式
class ChatRequest(BaseModel):
    message: str

class ChatResponse(BaseModel):
    response: str

# 這個路由會回傳你的聊天室前端頁面
@app.get("/", response_class=HTMLResponse)
async def get_root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

# 這個路由會接收前端傳來的訊息，並回傳 Agent 的回覆
@app.post("/chat", response_model=ChatResponse)
async def chat_with_agent(request: ChatRequest):
    try:
        # 呼叫我們用 Llama 3 和各種工具建立好的 Agent
        result = await agent_executor.ainvoke({
            "input": request.message,
            "chat_history": [] 
        })
        return ChatResponse(response=result['output'])
    except Exception as e:
        print(f"Agent 執行出錯: {e}")
        return ChatResponse(response="抱歉，我現在有點問題，請稍後再試。")