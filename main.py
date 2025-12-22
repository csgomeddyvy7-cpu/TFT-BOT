import discord
import os
from discord.ext import commands
from keep_alive import keep_alive # Import file vừa tạo

# Cấu hình Bot
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)

@bot.event
async def on_ready():
    print(f'Logged in as {bot.user}')

@bot.command()
async def ping(ctx):
    await ctx.send('Pong!')

# --- KHU VỰC CHẠY BOT ---

# 1. Kích hoạt Web Server ảo
keep_alive()

# 2. Lấy Token từ biến môi trường (Bảo mật)
# Trên Render, bạn sẽ cài đặt biến này trong phần "Environment Variables"
my_secret = os.environ.get('DISCORD_TOKEN')

if my_secret:
    bot.run(my_secret)
else:
    print("Lỗi: Chưa tìm thấy DISCORD_TOKEN trong biến môi trường!")
