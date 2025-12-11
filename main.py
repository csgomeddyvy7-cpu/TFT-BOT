import discord
from discord.ext import commands, tasks
import os
import asyncio
from datetime import datetime, timedelta
import json

# Import các module riêng
from config import Config
from database import Database
from riot_verifier import RiotVerifier
from tft_service import TFTService
from gemini_analyzer import GeminiAnalyzer
from health_check import HealthCheckServer  # Thêm health check

# Load config
config = Config()

# Khởi tạo bot
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(
    command_prefix=config.PREFIX,
    intents=intents,
    help_command=None
)

# Khởi tạo các service
db = Database()
riot_verifier = RiotVerifier(config.RIOT_API_KEY)
tft_service = TFTService()
gemini_analyzer = GeminiAnalyzer(config.GEMINI_API_KEY)
health_server = HealthCheckServer()  # Khởi tạo health check server

# Biến tạm lưu trạng thái xác thực
verification_sessions = {}
# Dict để track match đã thông báo (tránh duplicate)
recent_matches = {}
# Dict để gộp thông báo cùng match
match_groups = {}

# ========== HEALTH CHECK SERVER ==========

async def start_health_server():
    """Khởi động health check server"""
    try:
        await health_server.start()
        return True
    except Exception as e:
        print(f"❌ Lỗi khởi động health server: {e}")
        return False

# ========== EVENTS ==========

@bot.event
async def on_ready():
    """Sự kiện khi bot sẵn sàng"""
    print(f'✅ TFT Tracker Bot đã sẵn sàng!')
    print(f'🤖 Bot: {bot.user.name}')
    print(f'🎮 Prefix: {config.PREFIX}')
    print(f'📊 Database: {len(db.get_all_players())} players')
    print(f'🔧 Gemini AI: {gemini_analyzer.status}')
    
    # Khởi động health check server
    health_status = await start_health_server()
    if health_status:
        print(f"🌐 Health check: http://0.0.0.0:{health_server.port}/health")
    
    # Khởi động task tự động
    if not auto_check_matches.is_running():
        auto_check_matches.start()
    
    # Clean up old matches data mỗi 30 phút
    if not cleanup_matches.is_running():
        cleanup_matches.start()
    
    # Set status
    await update_bot_status()

async def update_bot_status():
    """Cập nhật trạng thái bot"""
    player_count = len(db.get_all_players())
    await bot.change_presence(
        activity=discord.Activity(
            type=discord.ActivityType.watching,
            name=f"{player_count} TFT player{'s' if player_count != 1 else ''}"
        )
    )

@bot.event
async def on_command_error(ctx, error):
    """Xử lý lỗi command"""
    if isinstance(error, commands.CommandNotFound):
        return
    
    elif isinstance(error, commands.MissingRequiredArgument):
        embed = discord.Embed(
            title="❌ Thiếu tham số",
            description=f"Vui lòng kiểm tra lại cú pháp lệnh!",
            color=0xff0000
        )
        embed.add_field(
            name="ℹ️ Hướng dẫn",
            value=f"Dùng `{config.PREFIX}help` để xem hướng dẫn đầy đủ",
            inline=False
        )
        await ctx.send(embed=embed)
    
    elif isinstance(error, commands.BadArgument):
        await ctx.send(f"❌ Tham số không hợp lệ: {str(error)}")
    
    else:
        print(f"Lỗi không xác định: {error}")
        embed = discord.Embed(
            title="❌ Lỗi hệ thống",
            description=f"```{str(error)[:200]}```",
            color=0xff0000
        )
        await ctx.send(embed=embed)

# ========== VERIFICATION FLOW ==========

@bot.command(name='track')
async def track_player(ctx, riot_id: str, region: str = 'vn'):
    """
    Bắt đầu theo dõi player - Bước 1: Xác thực Riot ID
    Format: !track Username#Tagline [region]
    Example: !track DarkViPer#VN2 vn
    """
    
    # Kiểm tra format Riot ID
    if '#' not in riot_id:
        embed = discord.Embed(
            title="❌ Sai định dạng Riot ID",
            description="Vui lòng sử dụng đúng format: **Username#Tagline**",
            color=0xff0000
        )
        embed.add_field(
            name="📝 Ví dụ đúng:",
            value=f"`{config.PREFIX}track DarkViPer#VN2 vn`\n`{config.PREFIX}track TFTGod#KR1 kr`",
            inline=False
        )
        await ctx.send(embed=embed)
        return
    
    # Kiểm tra region hợp lệ
    if region.lower() not in config.SUPPORTED_REGIONS:
        regions_list = ', '.join(config.SUPPORTED_REGIONS.keys())
        embed = discord.Embed(
            title="❌ Region không hợp lệ",
            description=f"Region hỗ trợ: {regions_list}",
            color=0xff0000
        )
        await ctx.send(embed=embed)
        return
    
    # Kiểm tra xem đã theo dõi chưa
    existing = db.get_player_by_riot_id(riot_id)
    if existing:
        embed = discord.Embed(
            title="⚠️ Đã theo dõi",
            description=f"Riot ID `{riot_id}` đã được theo dõi!",
            color=0xff9900
        )
        await ctx.send(embed=embed)
        return
    
    # Gửi thông báo đang xác thực
    embed = discord.Embed(
        title="🔍 Đang xác thực Riot ID...",
        description=f"**Riot ID:** `{riot_id}`\n**Region:** `{region.upper()}`",
        color=0x7289DA,
        timestamp=datetime.now()
    )
    embed.set_footer(text="Vui lòng chờ trong giây lát...")
    msg = await ctx.send(embed=embed)
    
    # Xác thực Riot ID
    verification_result = await riot_verifier.verify_riot_id(riot_id, region)
    
    if not verification_result['success']:
        # Xác thực thất bại
        embed = discord.Embed(
            title="❌ Xác thực thất bại",
            description=f"Không thể xác thực Riot ID: `{riot_id}`",
            color=0xff0000
        )
        embed.add_field(
            name="📝 Lý do:",
            value=verification_result.get('error', 'Không rõ lý do'),
            inline=False
        )
        embed.add_field(
            name="💡 Gợi ý:",
            value="1. Kiểm tra lại chính tả\n2. Kiểm tra Region\n3. Đảm bảo tài khoản tồn tại",
            inline=False
        )
        await msg.edit(embed=embed)
        return
    
    # Xác thực thành công - hiển thị thông tin
    account_data = verification_result['data']
    
    embed = discord.Embed(
        title="✅ Đã tìm thấy tài khoản!",
        description=f"**Riot ID:** `{riot_id}`",
        color=0x00ff00,
        timestamp=datetime.now()
    )
    
    # Thêm thông tin cơ bản
    if account_data.get('game_name'):
        embed.add_field(
            name="👤 Game Name",
            value=account_data['game_name'],
            inline=True
        )
    
    if account_data.get('tagline'):
        embed.add_field(
            name="🏷️ Tagline",
            value=account_data['tagline'],
            inline=True
        )
    
    # Lấy thông tin TFT CHÍNH XÁC
    tft_info = await tft_service.get_player_overview(riot_id, region)
    
    if tft_info and tft_info.get('rank'):
        rank_text = f"**{tft_info['rank']}**"
        if tft_info.get('lp') is not None:
            rank_text += f" ({tft_info['lp']} LP)"
        
        embed.add_field(
            name="📊 Rank TFT",
            value=rank_text,
            inline=True
        )
    
    if tft_info and tft_info.get('level'):
        embed.add_field(
            name="🎮 Level",
            value=str(tft_info['level']),
            inline=True
        )
    
    if tft_info and tft_info.get('wins'):
        total_games = max(tft_info['total_games'], 1)
        win_rate = (tft_info['wins'] / total_games) * 100
        embed.add_field(
            name="📈 Thống kê",
            value=f"Tổng: {tft_info['total_games']} trận\nThắng: {tft_info['wins']} ({win_rate:.1f}%)",
            inline=True
        )
    
    if tft_info and tft_info.get('last_played'):
        try:
            last_played = datetime.fromisoformat(tft_info['last_played'].replace('Z', ''))
            time_diff = datetime.now() - last_played
            hours = int(time_diff.total_seconds() / 3600)
            
            if hours < 1:
                last_played_text = "Vừa xong"
            elif hours < 24:
                last_played_text = f"{hours} giờ trước"
            else:
                last_played_text = f"{hours//24} ngày trước"
            
            embed.add_field(
                name="🕐 Chơi lần cuối",
                value=last_played_text,
                inline=True
            )
        except:
            pass
    
    # Thêm hướng dẫn xác nhận
    embed.add_field(
        name="🔐 Bước 2: Xác nhận sở hữu",
        value=f"Để xác nhận đây là tài khoản của bạn, hãy gõ:\n"
              f"`{config.PREFIX}confirm {riot_id}`\n\n"
              f"Hoặc hủy với: `{config.PREFIX}cancel`",
        inline=False
    )
    
    # Lưu session xác thực tạm thời
    verification_sessions[ctx.author.id] = {
        'riot_id': riot_id,
        'region': region,
        'data': account_data,
        'tft_info': tft_info,
        'timestamp': datetime.now(),
        'message_id': msg.id,
        'channel_id': ctx.channel.id
    }
    
    await msg.edit(embed=embed)

# [Phần còn lại của các command giữ nguyên...]
# ...

# ========== MATCH CHECKING & NOTIFICATION ==========

@tasks.loop(minutes=5)
async def auto_check_matches():
    """Tự động kiểm tra trận đấu mới mỗi 5 phút"""
    print(f"[{datetime.now().strftime('%H:%M:%S')}] 🔄 Đang kiểm tra TFT matches...")
    
    players = db.get_all_players()
    
    if not players:
        return
    
    # Reset match groups
    match_groups.clear()
    
    for player in players:
        try:
            await check_player_matches(player)
            await asyncio.sleep(0.5)  # Delay để tránh rate limit
        except Exception as e:
            print(f"Lỗi khi kiểm tra {player['riot_id']}: {e}")
    
    # Gửi thông báo gộp cho các match có nhiều người chơi
    await send_grouped_notifications()

@tasks.loop(minutes=30)
async def cleanup_matches():
    """Dọn dẹp các match cũ trong bộ nhớ"""
    current_time = datetime.now()
    keys_to_remove = []
    
    for match_id, match_time in recent_matches.items():
        if (current_time - match_time).total_seconds() > 3600:  # 1 giờ
            keys_to_remove.append(match_id)
    
    for key in keys_to_remove:
        del recent_matches[key]
    
    if keys_to_remove:
        print(f"🧹 Đã dọn {len(keys_to_remove)} match cũ")

async def check_player_matches(player):
    """Kiểm tra và thông báo match mới cho một player"""
    try:
        riot_id = player['riot_id']
        region = player.get('region', 'vn')
        discord_id = player['discord_id']
        channel_id = int(player['channel_id'])
        
        # Lấy channel
        channel = bot.get_channel(channel_id)
        if not channel:
            print(f"Channel {channel_id} không tồn tại")
            return
        
        # Lấy match history
        matches = await tft_service.get_match_history(riot_id, region, limit=3)
        
        if not matches or len(matches) == 0:
            return
        
        # Kiểm tra từng match mới nhất trước
        for match_data in matches:
            match_id = match_data.get('match_id')
            match_time = match_data.get('timestamp')
            
            # Bỏ qua nếu match quá cũ (hơn 2 giờ)
            try:
                match_dt = datetime.fromisoformat(match_time.replace('Z', ''))
                if (datetime.now() - match_dt).total_seconds() > 7200:  # 2 giờ
                    continue
            except:
                pass
            
            # Kiểm tra xem đã thông báo match này chưa
            last_notified_match = player.get('last_match_id')
            
            if last_notified_match != match_id:
                # Match mới! Cập nhật database
                db.update_last_match(discord_id, riot_id, match_id, match_time)
                
                # Thêm vào nhóm thông báo gộp
                if match_id not in match_groups:
                    match_groups[match_id] = {
                        'match_data': match_data,
                        'players': [],
                        'channel_id': channel_id
                    }
                
                match_groups[match_id]['players'].append({
                    'player': player,
                    'match_data': match_data
                })
                
                # Đánh dấu đã xử lý match này
                recent_matches[match_id] = datetime.now()
                break  # Chỉ xử lý match mới nhất
        
    except Exception as e:
        print(f"Lỗi check_player_matches cho {player['riot_id']}: {e}")

async def send_grouped_notifications():
    """Gửi thông báo gộp cho các match"""
    for match_id, group in match_groups.items():
        try:
            if len(group['players']) == 1:
                # Chỉ một người chơi - gửi thông báo riêng
                player_data = group['players'][0]
                await send_match_notification(
                    bot.get_channel(group['channel_id']),
                    player_data['player'],
                    player_data['match_data']
                )
            else:
                # Nhiều người chơi - gửi thông báo gộp
                await send_grouped_match_notification(
                    bot.get_channel(group['channel_id']),
                    group['players'],
                    group['match_data']
                )
        except Exception as e:
            print(f"Lỗi gửi thông báo match {match_id}: {e}")

async def send_match_notification(channel, player, match_data):
    """Gửi thông báo trận đấu mới (riêng lẻ)"""
    try:
        riot_id = player['riot_id']
        settings = player.get('settings', {})
        
        # Tạo mention
        mention = ""
        if settings.get('mention_on_notify', True):
            try:
                discord_user = await bot.fetch_user(int(player['discord_id']))
                mention = f"{discord_user.mention} "
            except:
                pass
        
        # Tạo embed
        embed = await create_match_embed(player, match_data, is_grouped=False)
        
        # Thêm phân tích AI nếu được bật
        if settings.get('include_ai_analysis', True) and gemini_analyzer.is_enabled():
            ai_analysis = await gemini_analyzer.analyze_match(match_data, riot_id)
            if ai_analysis:
                if len(ai_analysis) > 1000:
                    ai_analysis = ai_analysis[:1000] + "..."
                
                embed.add_field(
                    name="🤖 AI Phân tích",
                    value=ai_analysis,
                    inline=False
                )
        
        # Gửi thông báo
        await channel.send(mention, embed=embed)
        print(f"✅ Đã thông báo match của {riot_id}")
        
    except Exception as e:
        print(f"Lỗi send_match_notification: {e}")

async def send_grouped_match_notification(channel, players_data, match_data):
    """Gửi thông báo gộp cho nhiều người cùng match"""
    try:
        embed = discord.Embed(
            title="👥 Đồng đội vừa chơi TFT cùng nhau!",
            description=f"**{len(players_data)} người chơi** trong cùng một trận",
            color=0x5865F2,
            timestamp=datetime.now()
        )
        
        # Thêm thông tin từng người chơi
        for i, data in enumerate(players_data):
            player = data['player']
            match = data['match_data']
            
            placement = match.get('placement', 8)
            level = match.get('level', 'N/A')
            
            # Emoji theo placement
            if placement == 1:
                emoji = "👑"
            elif placement <= 4:
                emoji = "🥈"
            else:
                emoji = "📉"
            
            embed.add_field(
                name=f"{emoji} {player['riot_id']}",
                value=f"**Hạng #{placement}** | Level {level}",
                inline=True
            )
        
        # Thêm thông tin match
        embed.add_field(
            name="📊 Thông tin trận đấu",
            value=f"Tổng cộng {len(players_data)} đồng đội",
            inline=False
        )
        
        # Thêm phân tích AI gộp
        if gemini_analyzer.is_enabled():
            # Tạo prompt phân tích nhóm
            prompt = f"""Phân tích nhóm {len(players_data)} người chơi TFT cùng một trận:
            
            Danh sách người chơi và hạng:
            """
            
            for data in players_data:
                player = data['player']
                match = data['match_data']
                prompt += f"- {player['riot_id']}: Hạng #{match.get('placement', 8)}\n"
            
            prompt += f"""
            Yêu cầu phân tích (tiếng Việt, 100-150 từ):
            1. Đánh giá hiệu suất chung của nhóm
            2. Ai là điểm mạnh/điểm yếu của nhóm?
            3. Gợi ý cải thiện cho lần chơi nhóm tiếp theo
            4. Đề xuất comp phối hợp tốt hơn
            
            Giọng văn: Thân thiện, xây dựng, tập trung vào teamwork.
            """
            
            try:
                ai_analysis = await gemini_analyzer.model.generate_content(prompt)
                if ai_analysis and ai_analysis.text:
                    analysis_text = ai_analysis.text.strip()
                    if len(analysis_text) > 1000:
                        analysis_text = analysis_text[:1000] + "..."
                    
                    embed.add_field(
                        name="🤖 AI Phân tích Nhóm",
                        value=analysis_text,
                        inline=False
                    )
            except:
                pass
        
        embed.set_footer(
            text="TFT Team Tracker • Thông báo nhóm",
            icon_url=bot.user.avatar.url if bot.user.avatar else None
        )
        
        # Tạo mentions
        mentions = []
        for data in players_data:
            player = data['player']
            if player.get('settings', {}).get('mention_on_notify', True):
                mentions.append(f"<@{player['discord_id']}>")
        
        mention_text = " ".join(mentions) if mentions else ""
        
        await channel.send(mention_text, embed=embed)
        print(f"✅ Đã thông báo nhóm {len(players_data)} players")
        
    except Exception as e:
        print(f"Lỗi send_grouped_match_notification: {e}")

async def create_match_embed(player, match_data, is_grouped=False):
    """Tạo embed cho thông báo match"""
    riot_id = player['riot_id']
    placement = match_data.get('placement', 8)
    level = match_data.get('level', 'N/A')
    
    # Màu theo placement
    if placement == 1:
        color = 0xFFD700  # Vàng
        emoji = "👑"
        title = f"{emoji} {riot_id} VÔ ĐỊCH!"
    elif placement <= 4:
        color = 0xC0C0C0  # Bạc
        emoji = "🥈"
        title = f"{emoji} {riot_id} Top {placement}"
    else:
        color = 0xCD7F32  # Đồng
        emoji = "📉"
        title = f"{emoji} {riot_id} hoàn thành trận đấu"
    
    embed = discord.Embed(
        title=title,
        description=f"**🏆 Hạng:** #{placement} | **📊 Level:** {level}",
        color=color,
        timestamp=datetime.now()
    )
    
    # Thêm thông tin chi tiết
    if match_data.get('traits'):
        traits_text = "\n".join([
            f"• {trait.get('name', 'Unknown')} (Tier {trait.get('tier', 1)})"
            for trait in match_data['traits'][:5]
        ])
        embed.add_field(
            name="🏆 Đội hình",
            value=traits_text[:1024],
            inline=True
        )
    
    if match_data.get('units'):
        units_text = "\n".join([
            f"• {unit.get('character_id', 'Unknown').replace('TFT', '').replace('_', ' ').title()}"
            for unit in match_data['units'][:5]
        ])
        embed.add_field(
            name="⚔️ Units chính",
            value=units_text[:1024],
            inline=True
        )
    
    # Thời gian game
    if match_data.get('game_duration'):
        minutes = match_data['game_duration'] // 60
        seconds = match_data['game_duration'] % 60
        embed.add_field(
            name="⏱️ Thời gian",
            value=f"{minutes}:{seconds:02d}",
            inline=True
        )
    
    if not is_grouped:
        embed.set_footer(
            text="TFT Auto Tracker • Tự động thông báo",
            icon_url=bot.user.avatar.url if bot.user.avatar else None
        )
    
    return embed

# [Phần còn lại của các command giữ nguyên...]
# ...

# ========== RUN BOT ==========

bot_start_time = datetime.now()

if __name__ == "__main__":
    if not config.DISCORD_TOKEN:
        print("❌ Lỗi: DISCORD_TOKEN không được tìm thấy!")
        print("ℹ️ Vui lòng đặt biến môi trường DISCORD_TOKEN")
        exit(1)
    
    print("🚀 Khởi động TFT Auto Tracker Bot...")
    print(f"📊 Database: {db.file_path}")
    print(f"🤖 Gemini AI: {gemini_analyzer.status}")
    print(f"🎮 Riot Verifier: {'✅ Ready' if riot_verifier.has_api_key else '⚠️ Limited'}")
    print(f"🌐 Health check port: 8080")
    
    try:
        bot.run(config.DISCORD_TOKEN)
    except KeyboardInterrupt:
        print("\n🛑 Đang dừng bot...")
    finally:
        # Cleanup
        asyncio.run(health_server.stop())