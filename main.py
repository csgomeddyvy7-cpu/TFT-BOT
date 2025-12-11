import discord
from discord.ext import tasks, commands
import requests
import os
import asyncio
from urllib.parse import quote
from keep_alive import keep_alive

# --- CẤU HÌNH ---
# THAY ID KÊNH DISCORD CỦA BẠN VÀO DƯỚI ĐÂY
CHANNEL_ID = 123456789012345678 

# Danh sách người chơi (Đã điền sẵn)
PLAYERS = [
    {"name": "Zyud",            "tag": "6969", "puuid": None, "last_match": None},
    {"name": "Trông Anh Ngược", "tag": "CiS",  "puuid": None, "last_match": None},
]

# --- SERVER VN/ASIA ---
REGION_ROUTING = "asia" # Quan trọng: Việt Nam thuộc Asia Routing

# Lấy Key từ Environment
RIOT_API_KEY = os.getenv('RIOT_API_KEY')
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')

intents = discord.Intents.default()
bot = commands.Bot(command_prefix='!', intents=intents)

def get_headers():
    return {"X-Riot-Token": RIOT_API_KEY}

def get_puuid(game_name, tag_line):
    try:
        # Xử lý tên có dấu cách và tiếng Việt
        safe_name = quote(game_name)
        url = f"https://{REGION_ROUTING}.api.riotgames.com/riot/account/v1/accounts/by-riot-id/{safe_name}/{tag_line}"
        resp = requests.get(url, headers=get_headers())
        if resp.status_code == 200:
            return resp.json().get("puuid")
        else:
            print(f"[LỖI PUUID] {game_name}: {resp.status_code}")
    except Exception as e:
        print(f"[LỖI KẾT NỐI] {e}")
    return None

def get_last_match_id(puuid):
    try:
        url = f"https://{REGION_ROUTING}.api.riotgames.com/tft/match/v1/matches/by-puuid/{puuid}/ids?start=0&count=1"
        resp = requests.get(url, headers=get_headers())
        if resp.status_code == 200 and len(resp.json()) > 0:
            return resp.json()[0]
    except:
        pass
    return None

def get_match_detail(match_id):
    try:
        url = f"https://{REGION_ROUTING}.api.riotgames.com/tft/match/v1/matches/{match_id}"
        resp = requests.get(url, headers=get_headers())
        if resp.status_code == 200:
            return resp.json()
    except:
        pass
    return None

# Vòng lặp kiểm tra mỗi 2 phút
@tasks.loop(minutes=2)
async def check_tft_matches():
    await bot.wait_until_ready()
    channel = bot.get_channel(CHANNEL_ID)
    
    if not channel:
        print("Chưa tìm thấy kênh Discord! Kiểm tra lại CHANNEL_ID")
        return

    for p in PLAYERS:
        # 1. Nếu chưa có PUUID thì đi lấy
        if not p["puuid"]:
            p["puuid"] = get_puuid(p["name"], p["tag"])
            # Lần đầu chạy chỉ lưu lại mốc trận đấu cuối, KHÔNG thông báo để tránh spam
            if p["puuid"]:
                p["last_match"] = get_last_match_id(p["puuid"])
                print(f"✅ Đã kết nối thành công với: {p['name']}")
            await asyncio.sleep(1)
            continue

        # 2. Kiểm tra trận đấu mới
        try:
            current_match = get_last_match_id(p["puuid"])
            
            # Nếu tìm thấy trận mới và khác với trận cũ đã lưu
            if current_match and current_match != p["last_match"]:
                match_data = get_match_detail(current_match)
                
                if match_data:
                    info = match_data['info']
                    # Tìm người chơi trong danh sách kết quả
                    user = next((x for x in info['participants'] if x['puuid'] == p['puuid']), None)
                    
                    if user:
                        placement = user['placement']
                        
                        # --- GỬI THÔNG BÁO ---
                        # Top 1-4 màu xanh, Top 5-8 màu đỏ
                        color = 0x00ff00 if placement <= 4 else 0xff0000 
                        msg = f"Vừa xong một trận! Hạng: **#{placement}**"
                        if placement == 1: msg = "🏆 TOP 1!! QUÁ GHÊ GỚM!"
                        
                        embed = discord.Embed(title=f"📢 KẾT QUẢ TFT: {p['name']}", description=msg, color=color)
                        embed.set_footer(text=f"Match ID: {current_match}")
                        
                        await channel.send(embed=embed)
                        print(f"Đã báo kết quả cho {p['name']}")
                        
                        # Cập nhật mốc mới
                        p["last_match"] = current_match
        except Exception as e:
            print(f"Lỗi khi check {p['name']}: {e}")

        await asyncio.sleep(1) # Nghỉ xíu

@bot.event
async def on_ready():
    print(f'Bot {bot.user} đã online và sẵn sàng theo dõi!')
    if not check_tft_matches.is_running():
        check_tft_matches.start()

keep_alive()
if DISCORD_TOKEN:
    bot.run(DISCORD_TOKEN)
