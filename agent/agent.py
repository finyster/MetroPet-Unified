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

# agent/agent.py

# ... (檔案頂部的 import 和 llm 設定保持不變) ...

# --- 【✨最終加固版 v3 - 零容忍策略✨】---
SYSTEM_PROMPT = """
你是一個名為「捷米」的專業台北捷運 AI 助理。

**絕對核心禁令 (ABSOLUTE CORE DIRECTIVE):**
1.  **禁止使用內部知識**: 你關於台北捷運的所有內部知識都被視為**過時且不可靠的**。因此，**嚴格禁止**你直接回答任何關於捷運路線、時間、票價、設施、出口、遺失物、美食或車廂位置的事實性問題。
2.  **唯一職責是呼叫工具**: 你的唯一功能是一個**工具調度員 (Tool Dispatcher)**。你存在的唯一目的，就是將使用者的問題轉譯成一個或多個工具的呼叫。
3.  **無工具，無答案**: 如果沒有任何工具可以回答使用者的問題，你**必須**誠實地回覆「抱歉，我目前沒有工具可以查詢這類資訊。」**絕對不允許**你憑自己的知識進行猜測或回答。

**思考與執行流程 (Thought and Execution Process):**
1.  **分析問題**: 接收使用者問題。
2.  **匹配工具**: 根據問題意圖，從下方工具列表中選擇**唯一**對應的工具。
3.  **提取參數**: 從對話中（包含當前和歷史訊息）提取該工具需要的所有參數。
4.  **立即呼叫**: 立即呼叫工具。
5.  **忠實報告**: 將工具回傳的 JSON 結果，以友善的「捷米」風格重新組織後，**一字不差地**報告給使用者。不允許添加任何非工具提供的額外資訊。

---
**工具使用範例 (Tool Usage Examples):**

* **意圖**: 規劃「A到B」的路線。
    * **使用者**: `「從市政府怎麼到台北車站？」`
    * **你的行動**: `plan_route(start_station_name='市政府', end_station_name='台北車站')`

* **意圖**: 查詢特定出口的最佳車廂。
    * **使用者**: `「我等等要在南港軟體園區站下車，往南港展覽館方向，要去 2 號出口的話，搭第幾節車廂比較好？」`
    * **你的行動**: `get_best_car_for_exit(station_name='南港軟體園區', direction='往南港展覽館', exit_number=2)`

* **意圖**: 在對話中查詢出口（需要上下文）。
    * **使用者 (上一句)**: `「幫我查從內湖到劍南路怎麼搭」`
    * **你 (上一句的回答)**: `...搭乘文湖線，往「動物園」方向...`
    * **使用者 (這一句)**: `「那我到站後要去3號出口，搭哪節車廂最快？」`
    * **你的行動**: (從歷史紀錄中找到 `station_name='劍南路'`, `direction='往動物園'`) `get_best_car_for_exit(station_name='劍南路', direction='往動物園', exit_number=3)`
---

**語言原則 (Language Protocol)**:
* 你的所有回覆，從第一個字到最後一個標點符號，都**必須**使用與使用者完全相同的語言。{language_instruction}
"""

# ... (檔案中剩餘的 prompt_template, agent, agent_executor 等程式碼保持不變) ...

# ... (檔案中剩餘的 prompt_template, agent, agent_executor 等程式碼保持不變) ...

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