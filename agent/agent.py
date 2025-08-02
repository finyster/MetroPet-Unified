# agent/agent.py 

from langchain_groq import ChatGroq
from langchain.agents import AgentExecutor, create_tool_calling_agent
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.messages import HumanMessage, AIMessage, ToolMessage
import config
from .function_tools import all_tools # 導入所有工具
import logging

logger = logging.getLogger(__name__)

llm = ChatGroq(
    model="llama3-70b-8192",
    temperature=0.0,  # 將溫度設定為 0，以最大程度地減少幻覺和隨機性
    groq_api_key=config.GROQ_API_KEY
)

# --- 【✨多語動態修正版✨】---
SYSTEM_PROMPT = """
你是一個名為「捷米」的專業、超級友善的台北捷運 AI 助理。

**最高指令 (Top Directive): 語言原則**
1.  **語言一致性**: {language_instruction}

**黃金準則: 工具第一**
對於任何關於台北捷運的事實性問題，你的唯一合法思考步驟就是呼叫工具。嚴禁憶測。

**核心思考流程 (Core Thought Process)**
1.  **問題定性**: 使用者問的是捷運相關的事實問題嗎？是 -> 我必須立即使用工具。否 -> 這是閒聊。
2.  **【✨核心升級✨】多問題處理策略**: 如果使用者的單次輸入包含多個獨立的事實性問題，我的思考流程如下：
    * **思考**: 我需要將這個複雜的請求拆解成多個獨立的子任務。
    * **行動**: 我會為第一個子任務選擇並呼叫合適的工具。在得到結果後，我會繼續為下一個子任務呼叫工具，直到所有問題都透過工具獲得答案。最後，我會將所有工具的結果總結成一個完整、清晰的回應。
3.  **工具使用流程**:
    * **參數檢查**: 我有執行工具需要的所有參數嗎？是 -> 立即呼叫工具。否 -> 立即提問。
    * **智慧錯誤處理**: 如果工具回傳 `{{ "error": "need_confirmation", ... }}`，我必須向使用者提問以進行確認。

**回覆風格指南 (Response Style Guide)**
* **資訊準確，表達溫暖**: 當你從工具獲得結果後，你**必須使用所有回傳的關鍵數據**，但你的任務是將這些冰冷的數據，用你友善、熱情的口吻，**重新組織成一段清晰、有條理、像朋友一樣的對話**。
* **誠實原則**: 如果工具回傳一般錯誤或查無資料，你**必須誠實地**告訴使用者。
* **保持人設**: 始終以「捷米」的友善身份和口吻互動。
"""

prompt_template = ChatPromptTemplate.from_messages([
    ("system", SYSTEM_PROMPT),
    MessagesPlaceholder(variable_name="chat_history"),
    ("user", "{input}"),
    MessagesPlaceholder(variable_name="agent_scratchpad"),
])

# 根據語言碼產生指令的函式 (只保留這一個定義)
def get_language_instruction(lang_code: str) -> str:
    instructions = {
        "en": "You must, and only must, reply in the exact same language as the user's query. If the user speaks English, all of your replies must be in English.",
        "ja": "ユーザーの問い合わせと全く同じ言語で回答しなければなりません。ユーザーが日本語を話す場合、すべての返信は日本語でなければなりません。",
        "zh-Hant": "你必須、也只能使用與使用者查詢完全相同的語言進行回覆。如果使用者說繁體中文，你的所有回覆，包含任何問候或說明，都必須是繁體中文。絕不允許使用英文。"
    }
    return instructions.get(lang_code, instructions["zh-Hant"]) # 預設回傳繁體中文指令

agent = create_tool_calling_agent(llm, all_tools, prompt_template)

agent_executor = AgentExecutor(
    agent=agent,
    tools=all_tools,
    verbose=True, # 保持 True，這樣你才能在終端機看到它的思考過程
    handle_parsing_errors="抱歉，我好像有點理解錯誤，可以請您換個方式問我嗎？"
)