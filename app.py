import gradio as gr
from agent import get_agent_response

# Gradio 需要一個函式來處理輸入和輸出
# 我們需要稍微包裝一下我們的 agent 回應函式
def chat_interface_fn(user_input, history):
    # Gradio 的 history 格式是 [[user_msg, bot_msg], [user_msg, bot_msg], ...]
    # 我們需要將它轉換成 LangChain 需要的格式
    # 這部分可以根據 LangChain 的文檔進行更細緻的處理，但此處為求簡潔先傳入空列表
    chat_history_for_langchain = [] 
    
    # 呼叫我們的 Agent 來獲取回應
    response = get_agent_response(user_input, chat_history_for_langchain)
    return response

# 建立 Gradio Chat UI
iface = gr.ChatInterface(
    fn=chat_interface_fn,
    title="臺北捷運 AI Agent - 捷寶",
    description="你好！我是捷寶，你的臺北捷運專屬助理。你可以問我票價、路線、即時到站資訊等問題。",
    examples=[
        ["從市政府到台北101的票價是多少？"],
        ["市政府站現在有車嗎？"],
        ["我的水壺好像掉在捷運上了，該怎麼辦？"]
    ]
)

# 啟動應用程式
if __name__ == "__main__":
    iface.launch()