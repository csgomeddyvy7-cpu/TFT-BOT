import discord
from discord.ext import commands, tasks
import os
import aiohttp
import asyncio
from datetime import datetime, timedelta
import json
import google.generativeai as genai
from aiohttp import web
import threading

TOKEN = os.getenv('DISCORD_BOT_TOKEN')
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')
RIOT_API_KEY = os.getenv('RIOT_API_KEY', '')

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents, help_command=None)

class Database:
    def __init__(self):
        self.file_path = 'tft_data.json'
        self.data = self.load_data()
    
    def load_data(self):
        if os.path.exists(self.file_path):
            try:
                with open(self.file_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                return {'players': [], 'matches': {}}
        return {'players': [], 'matches': {}}
    
    def save_data(self):
        with open(self.file_path, 'w', encoding='utf-8') as f:
            json.dump(self.data, f, indent=2, ensure_ascii=False)
    
    def add_player(self, discord_id, discord_name, riot_id, region, channel_id):
        for player in self.data['players']:
            if player['riot_id'].lower() == riot_id.lower():
                return False
        
        self.data['players'].append({
            'discord_id': str(discord_id),
            'discord_name': discord_name,
            'riot_id': riot_id,
            'region': region,
            'channel_id': str(channel_id),
            'verified': True,
            'added_at': datetime.now().isoformat(),
            'last_match_id': None,
            'last_match_time': None,
            'settings': {
                'mention': True,
                'ai_analysis': True if GEMINI_API_KEY else False,
                'auto_notify': True
            }
        })
        self.save_data()
        return True
    
    def remove_player(self, discord_id, riot_id):
        initial_count = len(self.data['players'])
        self.data['players'] = [p for p in self.data['players'] 
                               if not (p['discord_id'] == str(discord_id) and p['riot_id'].lower() == riot_id.lower())]
        if len(self.data['players']) < initial_count:
            self.save_data()
            return True
        return False
    
    def get_player_by_riot_id(self, riot_id):
        for player in self.data['players']:
            if player['riot_id'].lower() == riot_id.lower():
                return player
        return None
    
    def get_players_by_discord_id(self, discord_id):
        return [p for p in self.data['players'] if p['discord_id'] == str(discord_id)]
    
    def get_all_players(self):
        return self.data['players']
    
    def update_last_match(self, riot_id, match_id, match_time):
        for player in self.data['players']:
            if player['riot_id'].lower() == riot_id.lower():
                player['last_match_id'] = match_id
                player['last_match_time'] = match_time
                player['last_checked'] = datetime.now().isoformat()
                break
        self.save_data()
    
    def update_setting(self, discord_id, riot_id, setting, value):
        for player in self.data['players']:
            if player['discord_id'] == str(discord_id) and player['riot_id'].lower() == riot_id.lower():
                player['settings'][setting] = value
                self.save_data()
                return True
        return False

db = Database()

class GeminiAI:
    def __init__(self):
        self.enabled = bool(GEMINI_API_KEY)
        if self.enabled:
            try:
                genai.configure(api_key=GEMINI_API_KEY)
                self.model = genai.GenerativeModel('gemini-1.5-flash')
            except:
                self.enabled = False
    
    async def analyze_match(self, match_data, riot_id):
        if not self.enabled:
            return None
        
        try:
            placement = match_data.get('placement', 8)
            level = match_data.get('level', 0)
            traits = match_data.get('traits', [])
            units = match_data.get('units', [])
            
            traits_text = "\n".join([f"- {t.get('name', 'Unknown')} (Tier {t.get('tier', 1)})" for t in traits[:5]])
            units_text = "\n".join([f"- {u.get('character_id', 'Unknown')} ⭐{u.get('tier', 1)}" for u in units[:5]])
            
            prompt = f"""Phân tích trận đấu TFT bằng tiếng Việt:

Thông tin:
- Người chơi: {riot_id}
- Hạng: #{placement}
- Level: {level}

Đội hình:
{traits_text}

Units:
{units_text}

Yêu cầu phân tích ngắn gọn (100-150 từ):
1. Đánh giá kết quả
2. Điểm mạnh/điểm yếu
3. Gợi ý cải thiện"""
            
            response = await asyncio.to_thread(self.model.generate_content, prompt)
            return response.text if response else None
        except:
            return None

gemini = GeminiAI()

async def get_tft_stats_tracker(riot_id, region='vn'):
    try:
        username, tag = riot_id.split('#')
        url = f"https://api.tracker.gg/api/v2/tft/standard/profile/riot/{username}%23{tag}"
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'application/json'
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, timeout=10) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    
                    if 'data' in data and 'segments' in data['data']:
                        for segment in data['data']['segments']:
                            if segment['type'] == 'overview':
                                stats = segment['stats']
                                
                                rank_info = stats.get('rank', {})
                                tier = rank_info.get('metadata', {}).get('tierName', 'Unranked')
                                division = rank_info.get('metadata', {}).get('divisionName', '')
                                lp = rank_info.get('value', 0)
                                
                                rank_text = f"{tier} {division}".strip()
                                if lp and lp > 0:
                                    rank_text += f" ({lp} LP)"
                                
                                return {
                                    'rank': rank_text if rank_text else 'Unranked',
                                    'wins': stats.get('wins', {}).get('value', 0),
                                    'losses': stats.get('losses', {}).get('value', 0),
                                    'total_games': stats.get('matches', {}).get('value', 0),
                                    'level': stats.get('level', {}).get('value', 0) if stats.get('level') else 0,
                                    'top4_rate': stats.get('top4Ratio', {}).get('value', 0)
                                }
    except:
        pass
    
    return None

async def get_match_history_tracker(riot_id, region='vn'):
    try:
        username, tag = riot_id.split('#')
        url = f"https://api.tracker.gg/api/v2/tft/standard/profile/riot/{username}%23{tag}/matches"
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'application/json'
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, timeout=10) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    matches = []
                    
                    if 'data' in data and 'matches' in data['data']:
                        for match in data['data']['matches']:
                            match_info = match.get('metadata', {})
                            stats = match.get('stats', {})
                            
                            traits = []
                            for i in range(1, 4):
                                trait_key = f'trait{i}'
                                if trait_key in stats:
                                    trait_name = stats[trait_key].get('metadata', {}).get('name', '')
                                    if trait_name:
                                        traits.append({
                                            'name': trait_name,
                                            'tier': stats[trait_key].get('value', 1)
                                        })
                            
                            units = []
                            for i in range(1, 9):
                                unit_key = f'unit{i}'
                                if unit_key in stats:
                                    unit_name = stats[unit_key].get('metadata', {}).get('name', '')
                                    if unit_name:
                                        units.append({
                                            'character_id': unit_name,
                                            'tier': stats[unit_key].get('value', 1)
                                        })
                            
                            matches.append({
                                'match_id': match_info.get('matchId', ''),
                                'placement': stats.get('placement', {}).get('value', 8),
                                'level': stats.get('level', {}).get('value', 0),
                                'traits': traits,
                                'units': units,
                                'timestamp': match_info.get('timestamp', datetime.now().isoformat()),
                                'game_duration': match_info.get('duration', 0)
                            })
                    
                    return matches[:3]
    except:
        pass
    
    return []

async def get_player_stats(riot_id, region='vn'):
    stats = await get_tft_stats_tracker(riot_id, region)
    if stats:
        return stats
    
    return {
        'rank': 'Chưa xác định',
        'wins': 0,
        'losses': 0,
        'total_games': 0,
        'level': 0,
        'top4_rate': 0
    }

@bot.event
async def on_ready():
    print(f'✅ Bot đã sẵn sàng: {bot.user.name}')
    print(f'📊 Đang theo dõi: {len(db.get_all_players())} người chơi')
    
    if not check_matches.is_running():
        check_matches.start()

@bot.command()
async def track(ctx, riot_id: str, region: str = 'vn'):
    if '#' not in riot_id:
        await ctx.send('❌ Sai định dạng! Dùng: Username#Tag (VD: TênNgườiChơi#VN2)')
        return
    
    if db.get_player_by_riot_id(riot_id):
        await ctx.send('❌ Đã theo dõi người chơi này rồi!')
        return
    
    await ctx.send(f'🔍 Đang xác thực {riot_id}...')
    
    stats = await get_player_stats(riot_id, region)
    
    embed = discord.Embed(
        title='✅ Tìm thấy tài khoản!',
        description=f'**Riot ID:** {riot_id}\n**Region:** {region.upper()}',
        color=0x00ff00
    )
    
    embed.add_field(name='📊 Rank TFT', value=stats['rank'], inline=True)
    embed.add_field(name='🎮 Level', value=stats['level'], inline=True)
    embed.add_field(name='📈 Thống kê', 
                   value=f"{stats['wins']}W - {stats['losses']}L\n"
                         f"Tổng: {stats['total_games']} trận\n"
                         f"Top 4: {stats['top4_rate']:.1f}%", 
                   inline=True)
    
    embed.add_field(name='🔐 Xác nhận', 
                   value=f'Gõ `!confirm {riot_id}` để bắt đầu theo dõi\n'
                         f'Hủy: `!cancel`', 
                   inline=False)
    
    await ctx.send(embed=embed)
    
    track_sessions[str(ctx.author.id)] = {
        'riot_id': riot_id,
        'region': region,
        'stats': stats,
        'time': datetime.now()
    }

@bot.command()
async def confirm(ctx, riot_id: str):
    user_id = str(ctx.author.id)
    
    if user_id not in track_sessions:
        await ctx.send('❌ Không tìm thấy session! Dùng `!track` trước.')
        return
    
    session = track_sessions[user_id]
    
    if session['riot_id'].lower() != riot_id.lower():
        await ctx.send(f'❌ Riot ID không khớp! Session: {session["riot_id"]}')
        return
    
    success = db.add_player(
        ctx.author.id,
        ctx.author.name,
        session['riot_id'],
        session['region'],
        ctx.channel.id
    )
    
    if success:
        del track_sessions[user_id]
        embed = discord.Embed(
            title='🎉 Đã bắt đầu theo dõi!',
            description=f'Bot sẽ thông báo khi {session["riot_id"]} hoàn thành trận TFT mới.',
            color=0x00ff00
        )
        embed.add_field(name='🔄 Tự động', value='Kiểm tra mỗi 3 phút', inline=True)
        embed.add_field(name='📢 Thông báo', value=f'Tại <#{ctx.channel.id}>', inline=True)
        embed.add_field(name='⚙️ Cài đặt', value='Dùng `!settings`', inline=True)
        await ctx.send(embed=embed)
    else:
        await ctx.send('❌ Lỗi khi lưu dữ liệu!')

@bot.command()
async def cancel(ctx):
    user_id = str(ctx.author.id)
    if user_id in track_sessions:
        del track_sessions[user_id]
        await ctx.send('✅ Đã hủy session!')

@bot.command()
async def untrack(ctx, riot_id: str = None):
    user_id = str(ctx.author.id)
    players = db.get_players_by_discord_id(user_id)
    
    if not players:
        await ctx.send('❌ Bạn chưa theo dõi ai!')
        return
    
    if not riot_id:
        embed = discord.Embed(title='📋 Chọn player để dừng theo dõi', color=0x7289DA)
        for i, p in enumerate(players, 1):
            embed.add_field(name=f'{i}. {p["riot_id"]}', 
                          value=f'Region: {p["region"].upper()}', 
                          inline=False)
        embed.set_footer(text='Gõ !untrack [số] hoặc !untrack [RiotID]')
        await ctx.send(embed=embed)
        return
    
    if riot_id.isdigit():
        idx = int(riot_id) - 1
        if 0 <= idx < len(players):
            riot_id = players[idx]['riot_id']
    
    if db.remove_player(user_id, riot_id):
        await ctx.send(f'✅ Đã dừng theo dõi {riot_id}')
    else:
        await ctx.send(f'❌ Không tìm thấy {riot_id}')

@bot.command()
async def myplayers(ctx):
    players = db.get_players_by_discord_id(str(ctx.author.id))
    
    if not players:
        await ctx.send('❌ Bạn chưa theo dõi ai! Dùng `!track Username#Tag`')
        return
    
    embed = discord.Embed(title=f'📋 Đang theo dõi {len(players)} player(s)', color=0x7289DA)
    
    for p in players:
        last_match = p.get('last_match_time', 'Chưa có')
        if last_match and len(last_match) > 10:
            last_match = last_match[:10]
        
        embed.add_field(
            name=f'🎮 {p["riot_id"]}',
            value=f'Region: {p["region"].upper()}\n'
                  f'Theo dõi từ: {p["added_at"][:10]}\n'
                  f'Match cuối: {last_match}',
            inline=True
        )
    
    await ctx.send(embed=embed)

@bot.command()
async def settings(ctx, setting: str = None, value: str = None):
    players = db.get_players_by_discord_id(str(ctx.author.id))
    
    if not players:
        await ctx.send('❌ Bạn chưa theo dõi ai!')
        return
    
    if not setting:
        embed = discord.Embed(title='⚙️ Cài đặt của bạn', color=0x7289DA)
        for p in players:
            s = p['settings']
            embed.add_field(
                name=f'🎮 {p["riot_id"]}',
                value=f'• Mention: {"✅" if s["mention"] else "❌"}\n'
                      f'• AI Phân tích: {"✅" if s["ai_analysis"] else "❌"}\n'
                      f'• Tự động: {"✅" if s["auto_notify"] else "❌"}',
                inline=True
            )
        embed.set_footer(text='Dùng !settings [mention/ai/auto] [on/off]')
        await ctx.send(embed=embed)
        return
    
    valid_settings = ['mention', 'ai', 'auto']
    if setting not in valid_settings:
        await ctx.send(f'❌ Setting không hợp lệ! Chọn: {", ".join(valid_settings)}')
        return
    
    if value not in ['on', 'off']:
        await ctx.send('❌ Giá trị phải là "on" hoặc "off"!')
        return
    
    bool_value = value == 'on'
    setting_map = {
        'mention': 'mention',
        'ai': 'ai_analysis',
        'auto': 'auto_notify'
    }
    
    updated = 0
    for p in players:
        if db.update_setting(str(ctx.author.id), p['riot_id'], setting_map[setting], bool_value):
            updated += 1
    
    await ctx.send(f'✅ Đã cập nhật {setting} thành {value} cho {updated} player(s)')

@bot.command()
async def forcecheck(ctx):
    players = db.get_players_by_discord_id(str(ctx.author.id))
    
    if not players:
        await ctx.send('❌ Bạn chưa theo dõi ai!')
        return
    
    await ctx.send(f'🔍 Đang kiểm tra {len(players)} player(s)...')
    
    for player in players:
        try:
            await check_single_player(player)
            await asyncio.sleep(1)
        except:
            pass
    
    await ctx.send('✅ Đã kiểm tra xong!')

@bot.command()
async def ping(ctx):
    latency = round(bot.latency * 1000)
    await ctx.send(f'🏓 Pong! {latency}ms | Đang theo dõi: {len(db.get_all_players())} players')

@bot.command()
async def help(ctx):
    embed = discord.Embed(
        title='🎮 TFT Auto Tracker - Hướng dẫn',
        description='Bot tự động thông báo khi bạn/bạn bè hoàn thành trận TFT!',
        color=0x7289DA
    )
    
    commands = [
        ('!track Username#Tag [region]', 'Theo dõi player (VD: !track Tên#VN2 vn)'),
        ('!confirm RiotID', 'Xác nhận theo dõi sau khi track'),
        ('!myplayers', 'Danh sách players bạn đang theo dõi'),
        ('!untrack [số/RiotID]', 'Dừng theo dõi'),
        ('!settings', 'Xem/cài đặt thông báo'),
        ('!forcecheck', 'Kiểm tra ngay lập tức'),
        ('!ping', 'Kiểm tra độ trễ'),
        ('!help', 'Hiển thị hướng dẫn này')
    ]
    
    for cmd, desc in commands:
        embed.add_field(name=f'`{cmd}`', value=desc, inline=False)
    
    embed.add_field(
        name='✨ Tính năng',
        value='• Tự động kiểm tra mỗi 3 phút\n• Thông báo real-time\n• Phân tích AI (nếu có key)\n• Xác thực Riot ID chính xác',
        inline=False
    )
    
    embed.add_field(
        name='📝 Ví dụ đầy đủ',
        value='```\n!track TênNgườiChơi#VN2 vn\n!confirm TênNgườiChơi#VN2\n```',
        inline=False
    )
    
    await ctx.send(embed=embed)

track_sessions = {}

async def check_single_player(player):
    try:
        matches = await get_match_history_tracker(player['riot_id'], player['region'])
        if not matches:
            return
        
        latest_match = matches[0]
        match_id = latest_match.get('match_id')
        
        if player['last_match_id'] != match_id:
            db.update_last_match(player['riot_id'], match_id, latest_match['timestamp'])
            
            channel = bot.get_channel(int(player['channel_id']))
            if not channel:
                return
            
            mention = f"<@{player['discord_id']}> " if player['settings']['mention'] else ""
            
            placement = latest_match['placement']
            color = 0xFFD700 if placement == 1 else 0xC0C0C0 if placement <= 4 else 0xCD7F32
            emoji = "👑" if placement == 1 else "🥈" if placement <= 4 else "📉"
            
            embed = discord.Embed(
                title=f'{emoji} {player["riot_id"]} vừa hoàn thành trận TFT!',
                description=f'**🏆 Hạng:** #{placement} | **📊 Level:** {latest_match["level"]}',
                color=color,
                timestamp=datetime.now()
            )
            
            if latest_match['traits']:
                traits_text = "\n".join([f"• {t['name']} (Tier {t['tier']})" for t in latest_match['traits'][:4]])
                embed.add_field(name='🏆 Đội hình', value=traits_text, inline=True)
            
            if latest_match['units']:
                units_text = "\n".join([f"• {u['character_id'].replace('TFT', '').replace('_', ' ')} ⭐{u['tier']}" 
                                       for u in latest_match['units'][:4]])
                embed.add_field(name='⚔️ Units', value=units_text, inline=True)
            
            if player['settings']['ai_analysis'] and gemini.enabled:
                analysis = await gemini.analyze_match(latest_match, player['riot_id'])
                if analysis and len(analysis) < 1000:
                    embed.add_field(name='🤖 Phân tích AI', value=analysis[:1000], inline=False)
            
            embed.set_footer(text='TFT Auto Tracker • Tự động thông báo')
            
            await channel.send(mention, embed=embed)
            
    except Exception as e:
        print(f"Lỗi check player {player['riot_id']}: {e}")

@tasks.loop(minutes=3)
async def check_matches():
    players = db.get_all_players()
    
    for player in players:
        try:
            await check_single_player(player)
            await asyncio.sleep(2)
        except:
            continue

async def health_check(request):
    return web.Response(text="Bot đang hoạt động!", status=200)

def run_web_server():
    app = web.Application()
    app.router.add_get('/', health_check)
    app.router.add_get('/health', health_check)
    
    port = int(os.environ.get('PORT', 8080))
    web.run_app(app, port=port)

if __name__ == '__main__':
    if not TOKEN:
        print("❌ Lỗi: Thiếu DISCORD_BOT_TOKEN!")
        exit(1)
    
    import threading
    web_thread = threading.Thread(target=run_web_server, daemon=True)
    web_thread.start()
    
    bot.run(TOKEN)