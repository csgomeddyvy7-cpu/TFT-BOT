import discord
from discord.ext import tasks, commands
import requests
import os
import asyncio
from keep_alive import keep_alive

# --- CẤU HÌNH ---

# 1. ID Kênh chat (BẠN NHỚ THAY SỐ NÀY BẰNG ID KÊNH CỦA BẠN NHÉ)
CHANNEL_ID = 1448163760480063519

# 2. DANH SÁCH NGƯỜI CHƠI (Đã điền theo yêu cầu)
PLAYERS = [
    {"name": "Zyud",            "tag": "6969", "puuid": None, "last_match": None, "last_rank": "Unranked"},
    {"name": "Trông Anh Ngược", "tag": "CiS",  "puuid": None, "last_match": None, "last_rank": "Unranked"},
]

# --- CẤU HÌNH SERVER ---
REGION_ROUTING = "asia"   # Lấy match/puuid
PLATFORM_ROUTING = "vn2"  # Lấy rank

# Lấy Key từ Render
RIOT_API_KEY = os.getenv('RIOT_API_KEY')
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')

intents = discord.Intents.default()
intents.message_content = True # Bắt buộc để đọc được lệnh !list
bot = commands.Bot(command_prefix='!', intents=intents)

# --- CÁC HÀM GỌI API ---
def get_headers():
    return {"X-Riot-Token": RIOT_API_KEY}

def get_puuid(game_name, tag_line):
    # Xử lý tên có khoảng trắng cho đúng chuẩn URL
    url = f"https://{REGION_ROUTING}.api.riotgames.com/riot/account/v1/accounts/by-riot-id/{game_name}/{tag_line}"
    resp = requests.get(url, headers=get_headers())
    if resp.status_code == 200:
        return resp.json().get("puuid")
    print(f"[LỖI] Không tìm thấy PUUID cho {game_name}#{tag_line}. Mã lỗi: {resp.status_code}")
    return None

def get_last_match_id(puuid):
    url = f"https://{REGION_ROUTING}.api.riotgames.com/tft/match/v1/matches/by-puuid/{puuid}/ids?start=0&count=1"
    resp = requests.get(url, headers=get_headers())
    if resp.status_code == 200 and len(resp.json()) > 0:
        return resp.json()[0]
    return None

def get_match_detail(match_id):
    url = f"https://{REGION_ROUTING}.api.riotgames.com/tft/match/v1/matches/{match_id}"
    resp = requests.get(url, headers=get_headers())
    if resp.status_code == 200:
        return resp.json()
    return None

def get_rank_info(puuid):
    if not puuid: return "Chưa có PUUID"
    
    # 1. Lấy Summoner ID
    summ_url = f"https://{PLATFORM_ROUTING}.api.riotgames.com/tft/summoner/v1/summoners/by-puuid/{puuid}"
    summ_resp = requests.get(summ_url, headers=get_headers())
    if summ_resp.status_code != 200: return "Lỗi SummonerID"
    
    summoner_id = summ_resp.json().get("id")
    
    # 2. Lấy Rank
    rank_url = f"https://{PLATFORM_ROUTING}.api.riotgames.com/tft/league/v1/entries/by-summoner/{summoner_id}"
    rank_resp = requests.get(rank_url, headers=get_headers())
    
    if rank_resp.status_code == 200:
        data = rank_resp.json()
        if not data: return "Unranked"
        
        for entry in data:
            if entry.get("queueType") == "RANKED_TFT":
                tier = entry.get('tier')
                rank = entry.get('rank')
                lp = entry.get('leaguePoints')
                return f"{tier} {rank} - {lp} LP"
        return "Chưa chơi xếp hạng"
    return "Lỗi lấy Rank"

# --- LỆNH !LIST ---
@bot.command(name='list')
async def list_players(ctx):
    await ctx.send("🔍 Đang kiểm tra dữ liệu từ Riot... đợi xíu nhé!")
    
    embed = discord.Embed(title="📊 Danh sách theo dõi TFT", color=0x3498db)
    
    for player in PLAYERS:
        # Nếu chưa có PUUID thì tranh thủ lấy luôn
        if not player["puuid"]:
            player["puuid"] = get_puuid(player["name"], player["tag"])
            
        # Lấy rank hiện tại
        current_rank = get_rank_info(player["puuid"])
        
        # Cập nhật vào bộ nhớ đệm
        player["last_rank"] = current_rank
        
        status_icon = "✅" if player["puuid"] else "❌ (Lỗi tên/Tag)"
        embed.add_field(
            name=f"{status_icon} {player['name']} #{player['tag']}", 
            value=f"Rank: **{current_rank}**", 
            inline=False
        )
        await asyncio.sleep(0.5) # Nghỉ xíu để tránh lỗi API
        
    await ctx.send(embed=embed)

# --- VÒNG LẶP TỰ ĐỘNG ---
@tasks.loop(minutes=2)
async def check_tft_matches():
    await bot.wait_until_ready()
    channel = bot.get_channel(CHANNEL_ID)
    if not channel: return

    for player in PLAYERS:
        if not player["puuid"]:
            player["puuid"] = get_puuid(player["name"], player["tag"])
            # Lần đầu load thì chỉ lưu, không báo
            if player["puuid"]:
                player["last_match"] = get_last_match_id(player["puuid"])
                player["last_rank"] = get_rank_info(player["puuid"])
                print(f"Đã load dữ liệu cho {player['name']}")
            await asyncio.sleep(1)
            continue

        current_latest_match = get_last_match_id(player["puuid"])
        
        if current_latest_match and current_latest_match != player["last_match"]:
            match_data = get_match_detail(current_latest_match)
            if match_data:
                info = match_data['info']
                participant = next((p for p in info['participants'] if p['puuid'] == player['puuid']), None)
                
                if participant:
                    placement = participant['placement']
                    new_rank = get_rank_info(player["puuid"])
                    
                    color = 0x00ff00 if placement <= 4 else 0xff0000
                    embed = discord.Embed(title=f"Kết quả TFT: {player['name']}", color=color)
                    embed.add_field(name="Top", value=f"#{placement}", inline=True)
                    embed.add_field(name="Rank", value=f"{player['last_rank']} ➝ {new_rank}", inline=True)
                    embed.set_footer(text=f"Match ID: {current_latest_match}")
                    
                    await channel.send(embed=embed)
                    
                    player["last_match"] = current_latest_match
                    player["last_rank"] = new_rank

        await asyncio.sleep(1)

@bot.event
async def on_ready():
    print(f'Bot {bot.user} online!')
    if not check_tft_matches.is_running():
        check_tft_matches.start()

keep_alive()
if DISCORD_TOKEN:
    bot.run(DISCORD_TOKEN)
