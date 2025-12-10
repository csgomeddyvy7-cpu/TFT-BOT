import os
import asyncio
import discord
from discord.ext import commands, tasks
from riotwatcher import TftWatcher, RiotWatcher, ApiError
from aiohttp import web
from dotenv import load_dotenv

# --- CẤU HÌNH ---
load_dotenv()
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
RIOT_API_KEY = os.getenv('RIOT_API_KEY')
# Lấy ID kênh thông báo từ biến môi trường và chuyển sang dạng số nguyên
try:
    NOTIFY_CHANNEL_ID = int(os.getenv('CHANNEL_ID'))
except (TypeError, ValueError):
    print("LỖI: Chưa set CHANNEL_ID hoặc CHANNEL_ID không phải số.")
    NOTIFY_CHANNEL_ID = None

# Region Configuration
REGION_ACCOUNT = 'asia'  # Dùng để lấy PUUID
REGION_TFT = 'vn2'       # Dùng để lấy data TFT VN

# Khởi tạo API
riot_watcher = RiotWatcher(RIOT_API_KEY)
tft_watcher = TftWatcher(RIOT_API_KEY)

# Khởi tạo Bot
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)

# Danh sách người chơi đang theo dõi (Lưu trên RAM)
# Format: { 'puuid': { 'name': 'ABC#VN2', 'last_match': 'VN2_123456' } }
watched_players = {}

# --- PHẦN 1: HEALTH CHECK (Để Render không kill bot) ---
async def handle(request):
    return web.Response(text="Bot TFT is running!")

async def start_web_server():
    app = web.Application()
    app.add_routes([web.get('/', handle)])
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get("PORT", 8080))
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    print(f"Web server started on port {port}")

# --- PHẦN 2: CÁC HÀM HỖ TRỢ RIOT API ---

def get_puuid_by_riot_id(name, tag):
    try:
        # Xử lý tên có khoảng trắng
        user = riot_watcher.account.by_riot_id(REGION_ACCOUNT, name, tag)
        return user['puuid']
    except ApiError as e:
        print(f"Lỗi tìm PUUID: {e}")
        return None

def get_rank_info(puuid):
    """Lấy thông tin Rank và Winrate từ PUUID (Đã fix lỗi Unknown)"""
    try:
        # 1. Từ PUUID lấy Summoner ID
        summoner = tft_watcher.summoner.by_puuid(REGION_TFT, puuid)
        summoner_id = summoner['id']
        
        # 2. Từ Summoner ID lấy thông tin Rank
        league_entries = tft_watcher.league.by_summoner(REGION_TFT, summoner_id)
        
        if not league_entries:
            return "Unranked", 0, 0, 0 
            
        # --- FIX LỖI Ở ĐÂY ---
        # Tìm đúng entry của chế độ RANK ĐƠN (RANKED_TFT)
        # Bỏ qua Double Up (RANKED_TFT_DOUBLE_UP) hoặc Hyper Roll vì cấu trúc dữ liệu khác nhau
        entry = next((e for e in league_entries if e['queueType'] == 'RANKED_TFT'), None)
        
        if not entry:
            # Nếu có dữ liệu nhưng không phải Rank đơn (VD: Chỉ chơi Double Up)
            return "Chưa chơi Rank Đơn", 0, 0, 0

        tier = entry.get('tier', 'Unknown')
        rank = entry.get('rank', '')
        lp = entry.get('leaguePoints', 0)
        wins = entry.get('wins', 0)
        losses = entry.get('losses', 0)
        
        total_games = wins + losses
        winrate = round((wins / total_games) * 100, 1) if total_games > 0 else 0
        
        rank_str = f"{tier} {rank} - {lp} LP"
        return rank_str, wins, losses, winrate
        
    except ApiError as e:
        print(f"Lỗi API Riot: {e}") # Check log trên Render để biết lỗi gì (404, 403...)
        return "Lỗi kết nối Riot", 0, 0, 0
    except Exception as e:
        print(f"Lỗi xử lý dữ liệu: {e}") # Check log xem lỗi code chỗ nào
        return "Lỗi dữ liệu", 0, 0, 0

# --- PHẦN 3: COMMANDS & EVENTS ---

@bot.event
async def on_ready():
    print(f'Logged in as {bot.user}')
    await start_web_server()
    if not check_match_history.is_running():
        check_match_history.start()
    print("Bot đã sẵn sàng và đang chạy loop check lịch sử.")

@bot.command()
async def check(ctx, name: str, tag: str):
    """Check info trước khi add: !check Ten Tag"""
    await ctx.send(f"🔎 Đang soi info của **{name}#{tag}**...")
    
    puuid = get_puuid_by_riot_id(name, tag)
    
    if not puuid:
        await ctx.send(f"❌ Không tìm thấy người chơi {name}#{tag}.")
        return

    rank_str, wins, losses, winrate = get_rank_info(puuid)
    
    # Tạo bảng Embed đẹp
    embed = discord.Embed(title=f"Thông tin: {name}#{tag}", color=0x3498db)
    embed.add_field(name="Xếp hạng", value=rank_str, inline=False)
    embed.add_field(name="Thắng", value=str(wins), inline=True)
    embed.add_field(name="Thua (Top 5-8)", value=str(losses), inline=True)
    embed.add_field(name="Tỉ lệ vào Top 4", value=f"{winrate}%", inline=True) # Lưu ý: Riot tính win là top 1-4
    embed.set_footer(text="Dùng lệnh !add để thêm người này vào list theo dõi.")
    
    await ctx.send(embed=embed)

@bot.command()
async def add(ctx, name: str, tag: str):
    """Thêm người vào danh sách theo dõi: !add Ten Tag"""
    full_name = f"{name}#{tag}"
    
    if len(watched_players) >= 8:
        await ctx.send("⚠️ Đã đạt giới hạn theo dõi 8 người.")
        return

    puuid = get_puuid_by_riot_id(name, tag)
    if not puuid:
        await ctx.send("❌ Tên không hợp lệ.")
        return
        
    if puuid in watched_players:
        await ctx.send(f"⚠️ Đã đang theo dõi **{full_name}** rồi.")
        return

    # Lấy trận mới nhất để làm mốc, tránh thông báo lại trận cũ
    matches = tft_watcher.match.by_puuid(REGION_TFT, puuid, count=1)
    last_match = matches[0] if matches else None

    watched_players[puuid] = {
        'name': full_name,
        'last_match': last_match
    }
    
    await ctx.send(f"✅ Đã thêm **{full_name}** vào danh sách theo dõi.")

@bot.command()
async def remove(ctx, name: str, tag: str):
    """Xóa người khỏi danh sách: !remove Ten Tag"""
    puuid = get_puuid_by_riot_id(name, tag)
    if puuid and puuid in watched_players:
        del watched_players[puuid]
        await ctx.send(f"🗑️ Đã xóa **{name}#{tag}** khỏi danh sách.")
    else:
        await ctx.send("❌ Người này không có trong danh sách.")

@bot.command()
async def list(ctx):
    """Xem danh sách đang theo dõi"""
    if not watched_players:
        await ctx.send("📭 Danh sách trống.")
        return
    
    msg = "**Danh sách đang theo dõi:**\n"
    for puuid, data in watched_players.items():
        msg += f"- {data['name']}\n"
    await ctx.send(msg)

# --- PHẦN 4: VÒNG LẶP KIỂM TRA (LOOP) ---

@tasks.loop(minutes=2)
async def check_match_history():
    if not watched_players or not NOTIFY_CHANNEL_ID:
        return

    channel = bot.get_channel(NOTIFY_CHANNEL_ID)
    if not channel:
        print("Không tìm thấy kênh thông báo (Check lại CHANNEL_ID).")
        return

    for puuid, data in list(watched_players.items()):
        try:
            # Lấy 1 trận mới nhất
            matches = tft_watcher.match.by_puuid(REGION_TFT, puuid, count=1)
            
            if not matches:
                continue
                
            current_match_id = matches[0]
            
            # Kiểm tra xem có trận mới không
            if data['last_match'] and current_match_id != data['last_match']:
                # Update ID trận mới ngay lập tức
                watched_players[puuid]['last_match'] = current_match_id
                
                # Lấy chi tiết trận đấu
                match_detail = tft_watcher.match.by_id(REGION_TFT, current_match_id)
                info = match_detail['info']
                
                # Tìm chỉ số người chơi
                me = next((p for p in info['participants'] if p['puuid'] == puuid), None)
                
                if me:
                    placement = me['placement']
                    # Lấy Tộc/Hệ (Traits)
                    traits_list = [t['name'].replace('TFT13_', '') for t in me['traits'] if t['tier_current'] > 0]
                    traits_str = ", ".join(traits_list) if traits_list else "Không kích hệ"
                    
                    # Xác định màu và emoji
                    if placement == 1:
                        color = 0xf1c40f # Gold
                        title = f"👑 {data['name']} ĐẠT TOP 1!"
                    elif placement <= 4:
                        color = 0x2ecc71 # Green
                        title = f"✅ {data['name']} VÀO TOP {placement}"
                    else:
                        color = 0xe74c3c # Red
                        title = f"💀 {data['name']} OUT TOP {placement}"

                    embed = discord.Embed(title=title, description=f"Đội hình: **{traits_str}**", color=color)
                    await channel.send(embed=embed)
            
            # Nếu lúc đầu chưa có trận nào (None) thì gán trận vừa lấy làm mốc
            elif data['last_match'] is None:
                watched_players[puuid]['last_match'] = current_match_id

        except Exception as e:
            print(f"Lỗi check {data['name']}: {e}")
            # Nếu lỗi Rate Limit (429) thì tự thư viện riotwatcher đã xử lý wait, ta không cần lo

bot.run(DISCORD_TOKEN)
