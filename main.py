import discord
from discord.ext import tasks, commands
import requests
import os
import asyncio
from keep_alive import keep_alive

# --- CẤU HÌNH ---
RIOT_API_KEY = os.getenv('RIOT_API_KEY')
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
CHANNEL_ID = 123456789012345678 # <-- NHỚ THAY ID KÊNH DISCORD CỦA BẠN VÀO ĐÂY

# Danh sách người chơi cần theo dõi
# Đã điền sẵn tên của bạn và Zyud
PLAYERS = [
    {"name": "Zyud", "tag": "6969", "puuid": None, "last_match": None, "last_rank": "Unranked"},
    {"name": "Trông Anh Ngược", "tag": "CiS", "puuid": None, "last_match": None, "last_rank": "Unranked"}
]

# API URLs
REGION_ROUTING = "asia" # Dùng cho Account & Match
PLATFORM_ROUTING = "vn2" # Dùng cho Rank & Summoner

intents = discord.Intents.default()
intents.message_content = True # Bắt buộc bật để đọc được lệnh !track
bot = commands.Bot(command_prefix='!', intents=intents)

# --- TỪ ĐIỂN EMOJI RANK (Dùng tạm icon tròn màu) ---
# Nếu bạn có custom emoji trong server, thay icon này bằng ID emoji (VD: <a:challenger:123456>)
RANK_EMOJIS = {
    "IRON": "⚫ Sắt",
    "BRONZE": "🟤 Đồng",
    "SILVER": "⚪ Bạc",
    "GOLD": "🟡 Vàng",
    "PLATINUM": "🔵 Bạch Kim",
    "EMERALD": "🟢 Lục Bảo",
    "DIAMOND": "💎 Kim Cương",
    "MASTER": "🟣 Cao Thủ",
    "GRANDMASTER": "🔴 Đại Cao Thủ",
    "CHALLENGER": "👑 Thách Đấu"
}

# --- HÀM GỌI RIOT API ---
def get_headers():
    return {"X-Riot-Token": RIOT_API_KEY}

def get_puuid(game_name, tag_line):
    # Xử lý tên có dấu cách cho đúng chuẩn URL
    url = f"https://{REGION_ROUTING}.api.riotgames.com/riot/account/v1/accounts/by-riot-id/{game_name}/{tag_line}"
    resp = requests.get(url, headers=get_headers())
    if resp.status_code == 200:
        return resp.json().get("puuid")
    print(f"Lỗi lấy PUUID ({resp.status_code}) cho {game_name}#{tag_line}")
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

def get_rank_data_raw(puuid):
    """Hàm lấy dữ liệu Rank thô để xử lý"""
    # 1. Lấy Summoner ID từ PUUID
    summ_url = f"https://{PLATFORM_ROUTING}.api.riotgames.com/tft/summoner/v1/summoners/by-puuid/{puuid}"
    summ_resp = requests.get(summ_url, headers=get_headers())
    
    if summ_resp.status_code != 200: return None
    summoner_id = summ_resp.json().get("id")
    
    # 2. Lấy Rank từ Summoner ID
    rank_url = f"https://{PLATFORM_ROUTING}.api.riotgames.com/tft/league/v1/entries/by-summoner/{summoner_id}"
    rank_resp = requests.get(rank_url, headers=get_headers())
    
    if rank_resp.status_code == 200:
        data = rank_resp.json()
        if not data: return {"tier": "UNRANKED", "rank": "", "lp": 0}
        # Lấy phần tử đầu tiên (thường là rank TFT)
        return {
            "tier": data[0].get('tier'),
            "rank": data[0].get('rank'),
            "lp": data[0].get('leaguePoints'),
            "wins": data[0].get('wins'),
            "losses": data[0].get('losses') # Có thể tính winrate nếu thích
        }
    return None

# --- LỆNH !TRACK (ĐỂ CHECK BOT) ---
@bot.command()
async def track(ctx, *, arg):
    """Lệnh check rank thủ công: !track Name#Tag"""
    if "#" not in arg:
        await ctx.send("⚠️ Sai cú pháp! Hãy nhập: `!track Tên#Tag` (Ví dụ: `!track Zyud#6969`)")
        return

    await ctx.send(f"🔍 Đang tìm dữ liệu cho **{arg}**...")
    
    try:
        name, tag = arg.split('#')
        puuid = get_puuid(name.strip(), tag.strip())
        
        if not puuid:
            await ctx.send("❌ Không tìm thấy người chơi này (hoặc API Key hết hạn).")
            return

        rank_data = get_rank_data_raw(puuid)
        
        if rank_data:
            tier = rank_data['tier']
            division = rank_data['rank']
            lp = rank_data['lp']
            
            # Lấy Emoji
            emoji = RANK_EMOJIS.get(tier, "❓")
            
            embed = discord.Embed(title=f"Thông tin TFT: {name}#{tag}", color=0x00ccff)
            embed.add_field(name="Xếp Hạng", value=f"{emoji} {division}", inline=True)
            embed.add_field(name="Điểm", value=f"{lp} LP", inline=True)
            embed.set_footer(text="Bot by Gemini")
            
            await ctx.send(embed=embed)
        else:
            await ctx.send("❌ Không lấy được thông tin Rank.")
            
    except Exception as e:
        await ctx.send(f"❌ Lỗi: {e}")

# --- VÒNG LẶP CHECK DATA TỰ ĐỘNG ---
@tasks.loop(minutes=2) 
async def check_tft_matches():
    channel = bot.get_channel(CHANNEL_ID)
    if not channel: 
        print("Chưa tìm thấy kênh chat, hãy kiểm tra lại CHANNEL_ID")
        return

    for player in PLAYERS:
        # 1. Cập nhật PUUID nếu chưa có
        if not player["puuid"]: 
            player["puuid"] = get_puuid(player["name"], player["tag"])
            if player["puuid"]:
                # Lần đầu chạy, lưu mốc hiện tại, không thông báo
                player["last_match"] = get_last_match_id(player["puuid"])
                r_data = get_rank_data_raw(player["puuid"])
                if r_data:
                    player["last_rank"] = f"{r_data['tier']} {r_data['rank']} ({r_data['lp']} LP)"
                print(f"Đã load data ban đầu cho: {player['name']}")
            await asyncio.sleep(1) 
            continue

        # 2. Kiểm tra trận mới
        latest_match = get_last_match_id(player["puuid"])
        
        if latest_match and latest_match != player["last_match"]:
            match_data = get_match_detail(latest_match)
            if match_data:
                info = match_data['info']
                # Tìm người chơi trong danh sách tham gia
                participant = next((p for p in info['participants'] if p['puuid'] == player['puuid']), None)
                
                if participant:
                    placement = participant['placement'] # Top mấy
                    
                    # Lấy Rank mới sau trận đấu
                    new_rank_data = get_rank_data_raw(player["puuid"])
                    new_rank_str = "Unranked"
                    emoji = ""
                    
                    if new_rank_data:
                        tier = new_rank_data['tier']
                        emoji = RANK_EMOJIS.get(tier, "")
                        new_rank_str = f"{tier} {new_rank_data['rank']} ({new_rank_data['lp']} LP)"

                    # Tạo thông báo đẹp
                    embed = discord.Embed(
                        title=f"Kết quả trận đấu: {player['name']}", 
                        description=f"Vừa xong một trận TFT!",
                        color=0xffd700 if placement == 1 else 0x00ff00
                    )
                    embed.add_field(name="Hạng", value=f"🏆 Top #{placement}" if placement == 1 else f"Top #{placement}", inline=True)
                    embed.add_field(name="Rank hiện tại", value=f"{emoji} {new_rank_str}", inline=False)
                    embed.set_footer(text=f"Match ID: {latest_match}")
                    
                    await channel.send(embed=embed)
                    
                    # Cập nhật lại bộ nhớ
                    player["last_match"] = latest_match
                    player["last_rank"] = new_rank_str

        await asyncio.sleep(1) 

@bot.event
async def on_ready():
    print(f'Bot {bot.user} đã online!')
    check_tft_matches.start() 

keep_alive()
bot.run(DISCORD_TOKEN)
