import discord
from discord.ext import commands, tasks
import asyncio
from config import Config
import aiohttp
from datetime import datetime
import sqlite3
import json

# Bot setup
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)

# Database setup
def init_db():
    conn = sqlite3.connect('tft_bot.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS tracked_players
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  game_name TEXT,
                  tag_line TEXT,
                  puuid TEXT,
                  last_match_id TEXT)''')
    conn.commit()
    conn.close()

@bot.event
async def on_ready():
    print(f'✅ Bot đã đăng nhập với tên: {bot.user}')
    init_db()
    check_matches.start()

@bot.command()
async def track(ctx, *, player_info: str):
    """Thêm người chơi vào danh sách theo dõi"""
    try:
        if '#' not in player_info:
            await ctx.send("❌ Sai định dạng! Hãy dùng: `!track TênNgườiChơi#Tag`")
            return
            
        game_name, tag_line = player_info.split('#', 1)
        
        # Lưu vào database
        conn = sqlite3.connect('tft_bot.db')
        c = conn.cursor()
        c.execute("INSERT OR IGNORE INTO tracked_players (game_name, tag_line) VALUES (?, ?)", 
                  (game_name, tag_line))
        conn.commit()
        conn.close()
        
        await ctx.send(f"✅ Đã thêm {player_info} vào danh sách theo dõi!")
        
    except Exception as e:
        await ctx.send(f"❌ Lỗi: {str(e)}")

@tasks.loop(seconds=Config.CHECK_INTERVAL)
async def check_matches():
    """Kiểm tra trận đấu mới định kỳ"""
    try:
        channel = bot.get_channel(Config.CHANNEL_ID)
        if not channel:
            return
            
        # TODO: Thêm logic kiểm tra trận đấu ở đây
        # Sẽ cần implement API calls đến Riot
        
    except Exception as e:
        print(f"Lỗi khi check matches: {e}")

@bot.command()
async def health(ctx):
    """Kiểm tra tình trạng bot"""
    await ctx.send("🤖 Bot đang hoạt động bình thường!")

# Health endpoint cho Render
from flask import Flask
app = Flask(__name__)

@app.route('/health')
def health_check():
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}

def run_flask():
    app.run(host='0.0.0.0', port=8080)

# Chạy cả Discord bot và Flask server
import threading
flask_thread = threading.Thread(target=run_flask, daemon=True)
flask_thread.start()

# Chạy Discord bot
bot.run(Config.DISCORD_TOKEN)