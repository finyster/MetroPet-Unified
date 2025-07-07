# terminal_chat.py

import requests  # 專門用來發送網路請求的函式庫
import json

# 您的 FastAPI 伺服器運行的位址。/chat 是我們在 main.py 中定義的端點。
API_URL = "http://127.0.0.1:8000/chat"

def main():
    """
    一個簡單、好用的終端機聊天客戶端。
    """
    print("--- 捷米 AI 助理終端機 ---")
    print("您現在可以直接與捷米對話。")
    print("輸入 '掰掰' 或 'exit' 即可結束對話。")
    print("-" * 30)
    
    # 建立一個列表，用來存放每一輪的對話歷史紀錄
    chat_history = []

    while True:
        try:
            # 獲取使用者在終端機的輸入
            user_input = input("\n你：")

            # 如果輸入 '掰掰' 或 'exit'，就結束程式
            if user_input.lower() in ["掰掰", "exit"]:
                print("捷米：很高興為您服務，下次見！")
                break

            # 準備要發送給 API 伺服器的 JSON 資料
            # 這就是我們在 /docs 頁面 Request body 中看到的格式
            payload = {
                "message": user_input,
                "chat_history": chat_history
            }

            # 發送 POST 請求到您的 FastAPI 伺服器
            # `json=payload` 會自動將我們的 Python 字典轉換成 JSON 格式
            response = requests.post(API_URL, json=payload)
            
            # 這行很重要！如果伺服器回傳錯誤 (例如 500 Internal Server Error)，
            # 它會在這裡直接拋出異常，讓我們知道出錯了。
            response.raise_for_status()

            # 解析 API 回傳的 JSON 結果
            data = response.json()
            ai_answer = data.get("answer", "抱歉，我好像有點問題，沒有得到回應。")
            
            # 將 AI 的回答印出來
            print(f"捷米：{ai_answer}")

            # 將這一輪的問與答，完整地存入歷史紀錄中，以便 AI 參考上下文
            chat_history.append({"role": "user", "content": user_input})
            chat_history.append({"role": "assistant", "content": ai_answer})

        except requests.exceptions.ConnectionError:
            print("\n錯誤：無法連接到您的本地伺服器 (http://127.0.0.1:8000)。")
            print("請確認您的 uvicorn 伺服器正在另一個終端機中運行。")
            break
        except Exception as e:
            print(f"\n發生了未預期的錯誤: {e}")
            break

if __name__ == "__main__":
    main()