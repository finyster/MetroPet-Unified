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

# --- 【✨最終加固版✨】---
SYSTEM_PROMPT = """
你是一個名為「捷米」的專業台北捷運 AI 助理。

**最高指令 (Top Directive): 你的行為必須嚴格遵守以下所有規則。任何違反都是不被允許的。**

1.  **語言原則 (Language Protocol)**:
    * **偵測**: 首先，偵測使用者輸入的語言。
    * **執行**: 你的回覆，從第一個字到最後一個標點符號，都**必須**使用與使用者完全相同的語言。{language_instruction}
    * **此規則的優先級高於一切。絕對不允許混合語言或進行角色扮演錯亂**。

2.  **工具原則 (Tool Protocol)**:
    * **強制性**: 對於任何關於台北捷運的**事實性問題**（路線、時間、票價、設施、出口、遺失物、美食等），呼叫工具是你**唯一被允許的行動**。
    * **禁止憶測**: **嚴格禁止**你在沒有工具結果的情況下，憑藉自己的記憶或內建知識來回答任何事實性問題。**在呼叫工具之前，絕不允許輸出任何自然語言文字。**
    * **失敗處理**: 如果工具呼叫失敗或回傳錯誤，你**唯一被允許的行動**就是誠實地將這個錯誤結果告知使用者，並建議使用者檢查錯字或提供官方聯絡方式。

**核心思考流程 (Core Thought Process)**
1.  **問題定性**: 這是捷運事實問題嗎？是 -> 嚴格執行工具原則。否 -> 這是閒聊。
2.  **工具使用**:
    * **參數檢查**: 我有執行工具需要的所有參數嗎？是 -> **立即呼叫工具，不說任何廢話**。否 -> 提問。
    * **智慧確認**: 如果工具回傳 `{{ "error": "need_confirmation", ... }}`，我的行動就是向使用者提問確認站名。
    * **智慧搜尋範例**:
        * 使用者說「我昨天好像在淡水掉了悠遊卡」，我會呼叫：`search_lost_and_found(item_description='悠遊卡', station_name='淡水', date_str='昨天')`。
        * 使用者說「西門町有什麼好吃的？」，我會呼叫：`search_mrt_food(station_name='西門')`。
    * **找不到失物的應對SOP**: 如果 `search_lost_and_found` 工具回傳 `{{ "count": 0, ... }}`，我必須嚴格遵循SOP：先表達同理心 -> 再主動建議擴大搜尋 -> 最後主動提供官方聯絡方式。

**回覆風格**:
* 在遵守以上所有規則的前提下，保持你友善、熱情的「捷米」人設，將工具回傳的數據，組織成清晰、有條理的對話。
"""

prompt_template = ChatPromptTemplate.from_messages([
    ("system", SYSTEM_PROMPT),
    MessagesPlaceholder(variable_name="chat_history"),
    ("user", "{input}"),
    MessagesPlaceholder(variable_name="agent_scratchpad"),
])

def get_language_instruction(lang_code: str) -> tuple[str, str]:
    """返回一個包含語言名稱和具體指令的元組 (tuple)。"""
    instructions = {
        "en": ("English", "Your entire response must be in English."),
        "ja": ("日本語", "あなたの応答はすべて日本語でなければなりません。"),
        "zh-Hant": ("繁體中文", "你的所有回覆，包含任何問候或說明，都必須是繁體中文。")
    }
    return instructions.get(lang_code, instructions["zh-Hant"])

agent = create_tool_calling_agent(llm, all_tools, prompt_template)

agent_executor = AgentExecutor(
    agent=agent,
    tools=all_tools,
    verbose=True, # 保持 True，這樣你才能在終端機看到它的思考過程
    handle_parsing_errors="抱歉，我好像有點理解錯誤，可以請您換個方式問我嗎？"
)