from flask import Flask
from threading import Thread
import os

app = Flask('')

@app.route('/')
def home():
    return "Bot is alive!"

def run():
    # Tự động lấy port từ Render, nếu không có thì dùng 8080
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

def keep_alive():
    t = Thread(target=run)
    t.start()
