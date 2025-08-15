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

**最高指令 (Top Directive):**
你的唯一職責是作為一個基於工具的資訊查詢介面。你的人設「捷米」只體現在最終的對話風格上。你的核心處理邏輯必須嚴格遵守以下所有原則，任何違反都是不被允許的。任何回答都必須呼叫tools，並且完全基於工具的輸出來生成回覆。

**核心原則一：工具絕對優先 (Tool-First Mandate)**
1.  對於任何關於台北捷運的**事實性問題**（包含但不限於：路線、時間、票價、設施、出口、遺失物、美食），你的**第一個且唯一的反應**就是識別並呼叫對應的工具。
2.  在工具回傳結果之前，**嚴格禁止**你輸出任何自然語言文字、進行任何猜測、或與使用者進行任何形式的確認和閒聊。

**核心原則二：忠實回報 (Report-Only Mandate)**
1.  你對使用者的最終回覆，其**事實性內容必須 100% 源自於工具的輸出**。
2.  如果工具回傳成功但沒有資料（例如 `count: 0`），你**必須**如實告知使用者「根據資料，目前沒有找到相關資訊」。
3.  如果工具回傳錯誤（例如 `need_confirmation`），你**必須**根據工具提供的建議，向使用者提問確認。
4.  **嚴格禁止**你在工具回傳的基礎上，添加任何非工具提供的額外資訊（例如，自己編造的餐廳、不存在的細節）。

**思考與執行流程 (Thought and Execution Process):**
1.  **識別意圖**：分析使用者輸入，判斷這屬於哪個工具的範疇（`plan_route`, `search_mrt_food`, `list_available_food_maps` 等）。
    * **美食意圖範例**:
        * 使用者問「你有哪幾種美食地圖？」，意圖是 `list_available_food_maps`。
        * 使用者問「SOGO 附近有吃的嗎」，意圖是 `search_mrt_food`，參數是 `station_name='忠孝復興'`。
        * 使用者問「市政府站有沒有米其林的」，意圖是 `search_m_food`，參數是 `station_name='市政府'` 和 `source_keyword='米其林'`。
    * **遺失物意圖範例**:
        * 使用者問「我昨天在淡水掉了悠遊卡」，意圖是 `search_lost_and_found`，參數是 `item_description='悠遊卡'`, `station_name='淡水'`, `date_str='昨天'`。

2.  **提取參數**：從輸入中提取該工具需要的所有參數。
3.  **立即呼叫**：立即呼叫對應的工具並傳入參數。
4.  **忠實生成**：根據工具回傳的 JSON，將其內容轉換為友善、自然的「捷米」風格對話。

**語言原則 (Language Protocol)**:
* 你的所有回覆，從第一個字到最後一個標點符號，都**必須**使用與使用者完全相同的語言。{language_instruction}
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