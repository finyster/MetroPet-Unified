# agent/agent.py

import google.generativeai as genai
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain.agents import AgentExecutor, create_tool_calling_agent
from langchain_core.prompts import ChatPromptTemplate
import config

# 從同層級的 function_tools.py 導入我們整理好的 all_tools 列表
from .function_tools import all_tools

# ---【關鍵修正】: 將 API 金鑰直接傳遞給 ChatGoogleGenerativeAI ---
# 我們不再依賴全域設定，而是確保在建立 LLM 時，金鑰就在它手上。
# 這可以 100% 解決 DefaultCredentialsError 的問題。
llm = ChatGoogleGenerativeAI(
    model="gemini-1.5-flash-latest",
    temperature=0,
    google_api_key=config.GEMINI_API_KEY # <-- 就是加上這一行！
)


# --- 以下程式碼完全不需要變動 ---

# 建立提示模板
prompt_template = ChatPromptTemplate.from_messages([
    ("system", (
        "你是一個名為「捷米」的台北捷運 AI 助理。\n"
        "你的主要任務是根據使用者的問題，判斷是否需要使用工具來查詢資訊。\n"
        "1. 如果問題是關於「票價」或「車站出口」，你【必須】使用提供的工具來回答。\n"
        "2. 如果問題是閒聊或與捷運工具無關，你可以直接用對話的方式回應。\n"
        "請用繁體中文回答。"
    )),
    ("placeholder", "{chat_history}"),
    ("user", "{input}"),
    ("placeholder", "{agent_scratchpad}"),
])

# 建立 Agent (大腦)
agent = create_tool_calling_agent(llm, all_tools, prompt_template)

# 建立 Agent 執行器 (大腦+工具的組合)
# genai.configure() 這一行現在可以不用了，因為我們已經直接把金鑰傳給了 LLM。
agent_executor = AgentExecutor(agent=agent, tools=all_tools, verbose=True, handle_parsing_errors=True)