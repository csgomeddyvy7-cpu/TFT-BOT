import discord
from discord.ext import commands, tasks
import asyncio
import sqlite3
from datetime import datetime
import aiohttp
import os
from dotenv import load_dotenv

# ================== CẤU HÌNH ==================
load_dotenv()

DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
CHANNEL_ID = int(os.getenv('DISCORD_CHANNEL_ID'))
RIOT_API_KEY = os.getenv('RIOT_API_KEY')
REGION = 'sea'  # Server Việt Nam
CHECK_INTERVAL = 60  # Giây

# ================== RIOT API CLASS ==================
class RiotAPI:
    def __init__(self):
        self.api_key = RIOT_API_KEY
        self.region = REGION
        self.headers = {"X-Riot-Token": self.api_key}

    async def get_puuid(self, game_name, tag_line):
        """Lấy PUUID từ Riot ID"""
        url = f"https://{self.region}.api.riotgames.com/riot/account/v1/accounts/by-riot-id/{game_name}/{tag_line}"
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(url, headers=self.headers) as response:
                    if response.status == 200:
                        data = await response.json()
                        return data['puuid']
                    else:
                        print(f"Lỗi lấy PUUID: {response.status}")
                        return None
            except Exception as e:
                print(f"Lỗi kết nối: {e}")
                return None

    async def get_summoner_info(self, puuid):
        """Lấy thông tin summoner"""
        url = f"https://{self.region}.api.riotgames.com/tft/summoner/v1/summoners/by-puuid/{puuid}"
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=self.headers) as response:
                if response.status == 200:
                    return await response.json()
                return None

    async def get_rank_info(self, summoner_id):
        """Lấy thông tin rank TFT"""
        url = f"https://{self.region}.api.riotgames.com/tft/league/v1/entries/by-summoner/{summoner_id}"
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=self.headers) as response:
                if response.status == 200:
                    data = await response.json()
                    for entry in data:
                        if entry.get('queueType') == 'RANKED_TFT':
                            return entry
                    return None
                return None

    async def get_match_history(self, puuid, count=5):
        """Lấy lịch sử trận đấu"""
        url = f"https://{self.region}.api.riotgames.com/tft/match/v1/matches/by-puuid/{puuid}/ids?count={count}"
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=self.headers) as response:
                if response.status == 200:
                    return await response.json()
                return []

    async def get_match_details(self, match_id):
        """Lấy chi tiết trận đấu"""
        url = f"https://{self.region}.api.riotgames.com/tft/match/v1/matches/{match_id}"
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=self.headers) as response:
                if response.status == 200:
                    return await response.json()
                return None

# ================== DATABASE ==================
def init_db():
    """Khởi tạo database"""
    conn = sqlite3.connect('tft_bot.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS tracked_players
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  game_name TEXT,
                  tag_line TEXT,
                  puuid TEXT,
                  summoner_id TEXT,
                  last_match_id TEXT,
                  last_check TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS notified_matches
                 (match_id TEXT PRIMARY KEY,
                  player_puuid TEXT,
                  notified_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    conn.commit()
    conn.close()

# ================== DISCORD BOT ==================
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)
riot_api = RiotAPI()

@bot.event
async def on_ready():
    print(f'✅ Bot đã đăng nhập: {bot.user}')
    init_db()
    check_new_matches.start()

# ================== LỆNH !track ==================
@bot.command()
async def track(ctx, *, player_info: str):
    """Thêm người chơi vào danh sách theo dõi"""
    try:
        if '#' not in player_info:
            await ctx.send("❌ Sai định dạng! Dùng: `!track Tên#Tag`")
            return
            
        game_name, tag_line = player_info.split('#', 1)
        
        # Kiểm tra đã tồn tại chưa
        conn = sqlite3.connect('tft_bot.db')
        c = conn.cursor()
        c.execute("SELECT * FROM tracked_players WHERE game_name=? AND tag_line=?", 
                  (game_name, tag_line))
        if c.fetchone():
            await ctx.send(f"✅ {player_info} đã có trong danh sách!")
            conn.close()
            return
        
        # Lấy PUUID từ Riot
        await ctx.send(f"🔄 Đang lấy thông tin {player_info}...")
        puuid = await riot_api.get_puuid(game_name, tag_line)
        
        if not puuid:
            await ctx.send(f"❌ Không tìm thấy người chơi. Kiểm tra Riot ID!")
            conn.close()
            return
        
        # Lấy summoner info
        summoner_info = await riot_api.get_summoner_info(puuid)
        if not summoner_info:
            await ctx.send(f"⚠️ Lấy được PUUID nhưng không lấy được summoner info")
            summoner_id = None
        else:
            summoner_id = summoner_info['id']
        
        # Lưu vào database
        c.execute('''INSERT INTO tracked_players 
                     (game_name, tag_line, puuid, summoner_id) 
                     VALUES (?, ?, ?, ?)''',
                  (game_name, tag_line, puuid, summoner_id))
        conn.commit()
        conn.close()
        
        await ctx.send(f"✅ Đã thêm **{player_info}** vào danh sách theo dõi!")
        
    except Exception as e:
        await ctx.send(f"❌ Lỗi: {str(e)}")

# ================== LỆNH !rank ==================
@bot.command()
async def rank(ctx, *, player_info: str = None):
    """Kiểm tra rank của người chơi"""
    try:
        if not player_info:
            # Nếu không ghi tên, kiểm tra người gửi lệnh
            player_info = f"{ctx.author.name}#1234"  # Tạm thời
            await ctx.send("📝 Hãy dùng: `!rank Tên#Tag`")
            return
            
        if '#' not in player_info:
            await ctx.send("❌ Sai định dạng! Dùng: `!rank Tên#Tag`")
            return
            
        game_name, tag_line = player_info.split('#', 1)
        
        await ctx.send(f"🔄 Đang lấy rank của **{player_info}**...")
        
        # 1. Lấy PUUID
        puuid = await riot_api.get_puuid(game_name, tag_line)
        if not puuid:
            await ctx.send(f"❌ Không tìm thấy người chơi!")
            return
            
        # 2. Lấy summoner info
        summoner_info = await riot_api.get_summoner_info(puuid)
        if not summoner_info:
            await ctx.send(f"❌ Không lấy được thông tin summoner")
            return
            
        # 3. Lấy rank info
        rank_info = await riot_api.get_rank_info(summoner_info['id'])
        
        # 4. Format kết quả
        if not rank_info:
            message = "🔹 **Chưa có rank trong mùa này**"
        else:
            tier = rank_info.get('tier', 'UNRANKED')
            rank = rank_info.get('rank', '')
            lp = rank_info.get('leaguePoints', 0)
            wins = rank_info.get('wins', 0)
            losses = rank_info.get('losses', 0)
            
            win_rate = (wins / (wins + losses) * 100) if (wins + losses) > 0 else 0
            
            message = f"""
🏆 **Rank TFT**: {tier} {rank}
📊 **Điểm LP**: {lp} LP
📈 **Tỉ lệ thắng**: {wins}W - {losses}L ({win_rate:.1f}%)
🔥 **Hot Streak**: {'✅' if rank_info.get('hotStreak', False) else '❌'}
💪 **Veteran**: {'✅' if rank_info.get('veteran', False) else '❌'}
"""
        
        await ctx.send(f"**Thông tin rank của {player_info}**:\n{message}")
        
    except Exception as e:
        await ctx.send(f"❌ Lỗi khi lấy rank: {str(e)}")

# ================== LỆNH !list ==================
@bot.command()
async def list(ctx):
    """Hiển thị danh sách người đang theo dõi"""
    try:
        conn = sqlite3.connect('tft_bot.db')
        c = conn.cursor()
        c.execute("SELECT game_name, tag_line, puuid FROM tracked_players")
        players = c.fetchall()
        conn.close()
        
        if not players:
            await ctx.send("📭 Danh sách theo dõi đang trống!")
            return
        
        message = "**📋 Danh sách người đang theo dõi:**\n"
        for i, (game_name, tag_line, puuid) in enumerate(players, 1):
            puuid_short = puuid[:8] + "..." if puuid else "Chưa có"
            message += f"{i}. `{game_name}#{tag_line}` - PUUID: `{puuid_short}`\n"
        
        await ctx.send(message)
        
    except Exception as e:
        await ctx.send(f"❌ Lỗi: {str(e)}")

# ================== TỰ ĐỘNG KIỂM TRA TRẬN MỚI ==================
@tasks.loop(seconds=CHECK_INTERVAL)
async def check_new_matches():
    """Kiểm tra trận đấu mới định kỳ"""
    try:
        channel = bot.get_channel(CHANNEL_ID)
        if not channel:
            print("❌ Không tìm thấy channel!")
            return
        
        # Lấy danh sách người theo dõi
        conn = sqlite3.connect('tft_bot.db')
        c = conn.cursor()
        c.execute("SELECT game_name, tag_line, puuid, last_match_id FROM tracked_players WHERE puuid IS NOT NULL")
        players = c.fetchall()
        
        for game_name, tag_line, puuid, last_match_id in players:
            try:
                # Lấy lịch sử match (5 match gần nhất)
                match_ids = await riot_api.get_match_history(puuid, count=5)
                if not match_ids:
                    continue
                
                # Match mới nhất
                latest_match = match_ids[0]
                
                # Kiểm tra nếu đã thông báo match này chưa
                c.execute("SELECT * FROM notified_matches WHERE match_id=?", (latest_match,))
                if c.fetchone():
                    continue  # Đã thông báo rồi
                
                # Nếu có last_match_id và match mới khác match cũ
                if last_match_id and latest_match != last_match_id:
                    # Lấy chi tiết match
                    match_data = await riot_api.get_match_details(latest_match)
                    if match_data:
                        # Tìm thông tin người chơi trong match
                        participants = match_data.get('info', {}).get('participants', [])
                        for p in participants:
                            if p.get('puuid') == puuid:
                                placement = p.get('placement', 0)
                                
                                # Tạo thông báo
                                embed = discord.Embed(
                                    title=f"🎮 Trận đấu mới của {game_name}#{tag_line}",
                                    color=0x00ff00 if placement <= 4 else 0xff0000,
                                    timestamp=datetime.now()
                                )
                                
                                embed.add_field(name="🏆 Thứ hạng", value=f"Top {placement}", inline=True)
                                embed.add_field(name="📊 Cấp độ", value=p.get('level', 0), inline=True)
                                embed.add_field(name="⚔️ Sát thương", value=p.get('total_damage_to_players', 0), inline=True)
                                
                                # Lấy traits
                                traits = [t['name'] for t in p.get('traits', []) if t['tier_current'] > 0]
                                if traits:
                                    embed.add_field(name="🎭 Đội hình", value=", ".join(traits[:3]), inline=False)
                                
                                await channel.send(embed=embed)
                                
                                # Lưu vào database
                                c.execute("UPDATE tracked_players SET last_match_id=? WHERE puuid=?", 
                                          (latest_match, puuid))
                                c.execute("INSERT INTO notified_matches (match_id, player_puuid) VALUES (?, ?)",
                                          (latest_match, puuid))
                                conn.commit()
                                break
                
            except Exception as e:
                print(f"Lỗi kiểm tra match cho {game_name}: {e}")
                continue
        
        conn.close()
        
    except Exception as e:
        print(f"Lỗi trong check_new_matches: {e}")

# ================== HEALTH CHECK (cho Render) ==================
from flask import Flask, jsonify
app = Flask(__name__)

@app.route('/health')
def health():
    return jsonify({"status": "healthy", "bot": str(bot.user), "time": datetime.now().isoformat()})

def run_flask():
    app.run(host='0.0.0.0', port=8080)

# ================== CHẠY BOT ==================
if __name__ == "__main__":
    # Chạy Flask trong thread riêng
    import threading
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    
    # Chạy Discord bot
    bot.run(DISCORD_TOKEN)