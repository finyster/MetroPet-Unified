import logging
from fastapi import FastAPI, Request, HTTPException
# --- 【✨核心新增✨】在所有程式碼執行前，設定日誌的基礎配置 ---
logging.basicConfig(
    level=logging.INFO,  # 設定要顯示的最低日誌等級 (INFO, DEBUG, WARNING, ERROR, CRITICAL)
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', # 設定日誌的輸出格式
    force=True  # 強制覆蓋 Uvicorn 的預設配置
)
# -------------------------------------------------------------
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional

from agent.agent import agent_executor, get_language_instruction

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
    language: Optional[str] = "zh-Hant"  # 增加語言欄位，預設為繁體中文

class ChatResponse(BaseModel):
    response: str
    chat_history: List[Dict[str, Any]]

@app.get("/", response_class=HTMLResponse)
async def get_root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


# 【✨核心修改✨】我們在這裡建立一個新的、支援多語言的 ainvoke 函式
async def invoke_multilingual_agent(user_input: str, history: list, lang_code: str):
    """
    包裝原始的 agent_executor.ainvoke，動態加入多語言指令和語言名稱。
    """
    # 1. 根據 lang_code 獲取語言名稱和指令
    lang_name, lang_instruction = get_language_instruction(lang_code)
    
    # 2. 準備傳遞給 agent_executor 的字典
    input_payload = {
        "input": user_input,
        "chat_history": history,
        "language_name": lang_name, # 新增
        "language_instruction": lang_instruction
    }
    
    # 3. 呼叫原始的 agent_executor.ainvoke
    return await agent_executor.ainvoke(input_payload)


@app.post("/chat", response_model=ChatResponse)
async def chat_with_agent(request: ChatRequest):
    try:
        history_tuples = [(item.role, item.content) for item in request.chat_history]

        # 【✨核心修改✨】呼叫我們新建的包裝函式，而不是直接呼叫 agent_executor
        result = await invoke_multilingual_agent(
            user_input=request.message,
            history=history_tuples,
            lang_code=request.language
        )

        updated_history = request.chat_history + [
            ChatHistory(role="user", content=request.message),
            ChatHistory(role="assistant", content=result['output'])
        ]
        
        history_dicts = [item.dict() for item in updated_history]

        return ChatResponse(
            response=result['output'],
            chat_history=history_dicts
        )
    except Exception as e:
        print(f"Agent 執行出錯: {e}")
        raise HTTPException(status_code=500, detail="抱歉，我現在有點問題，請稍後再試。")