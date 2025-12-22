from flask import Flask
from threading import Thread
import os

app = Flask('')

@app.route('/')
def home():
    return "I am alive! Bot is running."

def run():
    # Render yêu cầu ứng dụng phải chạy trên Port 0.0.0.0
    # Và lấy cổng từ biến môi trường PORT (mặc định Render dùng 10000)
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 8080)))

def keep_alive():
    t = Thread(target=run)
    t.start()
