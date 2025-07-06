# agent.py

# 導入 Gemini 模型和新的 Agent 建立工具
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain.agents import create_tool_calling_agent, AgentExecutor

# 從我們的檔案中導入所需元件
import config
from function_tools import all_tools

# 1. 初始化 LLM 模型 (已更換為 Gemini)
#    使用 gemini-1.5-flash 模型，它速度快且支援工具呼叫
llm = ChatGoogleGenerativeAI(
    model="gemini-1.5-flash",
    google_api_key=config.GEMINI_API_KEY,
    temperature=0,
    convert_system_message_to_human=True # 為了相容性，將 system message 轉換
)

# 2. 設計 Prompt (提示) - 維持不變
prompt_template = ChatPromptTemplate.from_messages(
    [
        ("system", "你是一個名為「捷米」的台北捷運 AI 助理。你友善、樂於助人且專業。你會根據使用者的問題，決定是否需要使用工具來查詢資訊。如果使用者只是閒聊，就用輕鬆的語氣回應。"),
        ("user", "{input}"),
        MessagesPlaceholder(variable_name="agent_scratchpad"),
    ]
)

# 3. 建立 Agent (使用新的 create_tool_calling_agent)
#    這個函式更通用，能良好地與 Gemini 配合
agent = create_tool_calling_agent(llm, all_tools, prompt_template)

# 4. 建立 Agent 執行器 (Executor) - 維持不變
agent_executor = AgentExecutor(agent=agent, tools=all_tools, verbose=True)

def get_agent_response(user_input, chat_history):
    """
    接收使用者輸入和對話歷史，並回傳 Agent 的回應。
    """
    response = agent_executor.invoke({
        "input": user_input,
        "chat_history": chat_history
    })
    return response["output"]