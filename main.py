import discord
from discord.ext import tasks, commands
import requests
import os
import asyncio
from keep_alive import keep_alive # Import server ảo

# --- CẤU HÌNH ---
RIOT_API_KEY = os.getenv('RIOT_API_KEY')
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
CHANNEL_ID = 123456789012345678 # THAY ID KÊNH DISCORD MUỐN THÔNG BÁO VÀO ĐÂY

# Danh sách người chơi cần theo dõi (Riot ID: Name + Tag)
PLAYERS = [
    {"name": "TênIngame1", "tag": "VN2", "puuid": None, "last_match": None, "last_rank": "Unranked"},
    {"name": "TênIngame2", "tag": "VN2", "puuid": None, "last_match": None, "last_rank": "Unranked"}
]

# API URLs (Server Việt Nam thuộc khu vực SEA/VN2 nhưng Routing là 'vietnam' hoặc 'asia' tùy endpoint)
# Account/Match dùng 'asia', Rank/Summoner dùng 'vn2'
REGION_ROUTING = "asia"
PLATFORM_ROUTING = "vn2"

intents = discord.Intents.default()
bot = commands.Bot(command_prefix='!', intents=intents)

# --- HÀM GỌI RIOT API ---
def get_headers():
    return {"X-Riot-Token": RIOT_API_KEY}

def get_puuid(game_name, tag_line):
    url = f"https://{REGION_ROUTING}.api.riotgames.com/riot/account/v1/accounts/by-riot-id/{game_name}/{tag_line}"
    resp = requests.get(url, headers=get_headers())
    if resp.status_code == 200:
        return resp.json().get("puuid")
    print(f"Lỗi lấy PUUID cho {game_name}: {resp.status_code}")
    return None

def get_last_match_id(puuid):
    # Lấy 1 trận đấu gần nhất
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
    # Cần lấy SummonerID từ PUUID trước
    summ_url = f"https://{PLATFORM_ROUTING}.api.riotgames.com/tft/summoner/v1/summoners/by-puuid/{puuid}"
    summ_resp = requests.get(summ_url, headers=get_headers())
    if summ_resp.status_code != 200: return "Unknown"
    
    summoner_id = summ_resp.json().get("id")
    
    # Lấy Rank
    rank_url = f"https://{PLATFORM_ROUTING}.api.riotgames.com/tft/league/v1/entries/by-summoner/{summoner_id}"
    rank_resp = requests.get(rank_url, headers=get_headers())
    if rank_resp.status_code == 200:
        data = rank_resp.json()
        if not data: return "Unranked"
        # TFT thường trả về list, lấy phần tử đầu tiên là rank TFT
        tier = data[0].get('tier')
        rank = data[0].get('rank')
        lp = data[0].get('leaguePoints')
        return f"{tier} {rank} - {lp} LP"
    return "Unknown"

# --- VÒNG LẶP CHECK DATA ---
@tasks.loop(minutes=2) # Check mỗi 2 phút
async def check_tft_matches():
    channel = bot.get_channel(CHANNEL_ID)
    if not channel: return

    for player in PLAYERS:
        if not player["puuid"]: # Nếu chưa có PUUID thì lấy lần đầu
            player["puuid"] = get_puuid(player["name"], player["tag"])
            # Lấy trận gần nhất để làm mốc, không thông báo trận cũ
            if player["puuid"]:
                player["last_match"] = get_last_match_id(player["puuid"])
                player["last_rank"] = get_rank_info(player["puuid"])
            await asyncio.sleep(1) # Nghỉ 1s tránh rate limit
            continue

        # Check trận mới
        current_latest_match = get_last_match_id(player["puuid"])
        
        if current_latest_match and current_latest_match != player["last_match"]:
            # Có trận mới!
            match_data = get_match_detail(current_latest_match)
            if match_data:
                # Tìm info của người chơi trong trận
                info = match_data['info']
                participant = next((p for p in info['participants'] if p['puuid'] == player['puuid']), None)
                
                if participant:
                    placement = participant['placement']
                    
                    # Check Rank mới
                    new_rank = get_rank_info(player["puuid"])
                    rank_msg = f"Rank: {player['last_rank']} -> {new_rank}"
                    
                    # Gửi thông báo
                    embed = discord.Embed(title=f"New TFT Match: {player['name']}", color=0x00ff00)
                    embed.add_field(name="Top", value=f"#{placement}", inline=True)
                    embed.add_field(name="Thay đổi Rank", value=rank_msg, inline=False)
                    embed.set_footer(text=f"Match ID: {current_latest_match}")
                    
                    await channel.send(embed=embed)
                    
                    # Cập nhật dữ liệu vào bộ nhớ
                    player["last_match"] = current_latest_match
                    player["last_rank"] = new_rank

        await asyncio.sleep(1) # Nghỉ tránh spam API

@bot.event
async def on_ready():
    print(f'Bot {bot.user} đã online!')
    check_tft_matches.start() # Bắt đầu vòng lặp

# Chạy server ảo và chạy bot
keep_alive()
bot.run(DISCORD_TOKEN)