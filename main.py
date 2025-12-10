import discord
from discord.ext import commands, tasks
import aiohttp
import asyncio
import json
import os
from datetime import datetime, timedelta
import logging
import aiofiles
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from flask import Flask, jsonify
from typing import Dict, List, Optional

# Flask app for healthcheck
app = Flask(__name__)

@app.route('/')
def home():
    return jsonify({"status": "TFT Tracker Bot is running!", "timestamp": datetime.now().isoformat()}), 200

@app.route('/health')
def health_check():
    return jsonify({"status": "healthy", "timestamp": datetime.now().isoformat()}), 200

# Discord bot setup
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix='!', intents=intents)

# Configuration from environment variables
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
RIOT_API_KEY = os.getenv('RIOT_API_KEY')  # RGAPI-xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
DISCORD_CHANNEL_ID = int(os.getenv('DISCORD_CHANNEL_ID', '0'))

# File paths
TRACKED_PLAYERS_FILE = 'tracked_players.json'
PENDING_CONFIRMATIONS_FILE = 'pending_confirmations.json'

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Riot API configuration for Vietnam server (VNG)
RIOT_REGIONS = {
    'account': 'https://asia.api.riotgames.com',  # For Riot ID to PUUID
    'tft': 'https://vn2.api.riotgames.com',       # For TFT data (Vietnam server)
    'match': 'https://sea.api.riotgames.com'      # For match data (SEA region)
}

class RiotAPI:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.session = None
        self.headers = {
            'X-Riot-Token': api_key,
            'User-Agent': 'TFT-Discord-Bot/1.0'
        }
    
    async def get_session(self):
        if not self.session or self.session.closed:
            self.session = aiohttp.ClientSession(headers=self.headers)
        return self.session
    
    async def close(self):
        if self.session and not self.session.closed:
            await self.session.close()
    
    async def get_puuid_by_riot_id(self, game_name: str, tag_line: str) -> Optional[str]:
        """Convert Riot ID (name#tag) to PUUID"""
        try:
            session = await self.get_session()
            url = f"{RIOT_REGIONS['account']}/riot/account/v1/accounts/by-riot-id/{game_name}/{tag_line}"
            
            async with session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    return data.get('puuid')
                elif response.status == 404:
                    logger.warning(f"Riot ID not found: {game_name}#{tag_line}")
                    return None
                else:
                    logger.error(f"API Error getting PUUID: {response.status}")
                    return None
        except Exception as e:
            logger.error(f"Error getting PUUID: {str(e)}")
            return None
    
    async def get_summoner_by_puuid(self, puuid: str):
        """Get summoner info by PUUID"""
        try:
            session = await self.get_session()
            url = f"{RIOT_REGIONS['tft']}/tft/summoner/v1/summoners/by-puuid/{puuid}"
            
            async with session.get(url) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    logger.error(f"API Error getting summoner: {response.status}")
                    return None
        except Exception as e:
            logger.error(f"Error getting summoner: {str(e)}")
            return None
    
    async def get_tft_rank(self, summoner_id: str):
        """Get TFT rank info"""
        try:
            session = await self.get_session()
            url = f"{RIOT_REGIONS['tft']}/tft/league/v1/entries/by-summoner/{summoner_id}"
            
            async with session.get(url) as response:
                if response.status == 200:
                    ranks = await response.json()
                    # Find TFT ranked queue
                    for rank in ranks:
                        if rank.get('queueType') == 'RANKED_TFT':
                            return rank
                    return {}
                else:
                    logger.error(f"API Error getting rank: {response.status}")
                    return {}
        except Exception as e:
            logger.error(f"Error getting rank: {str(e)}")
            return {}
    
    async def get_match_history(self, puuid: str, count: int = 20):
        """Get match history (returns match IDs)"""
        try:
            session = await self.get_session()
            url = f"{RIOT_REGIONS['match']}/tft/match/v1/matches/by-puuid/{puuid}/ids"
            params = {'count': count}
            
            async with session.get(url, params=params) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    logger.error(f"API Error getting match history: {response.status}")
                    return []
        except Exception as e:
            logger.error(f"Error getting match history: {str(e)}")
            return []
    
    async def get_match_details(self, match_id: str):
        """Get detailed match information"""
        try:
            session = await self.get_session()
            url = f"{RIOT_REGIONS['match']}/tft/match/v1/matches/{match_id}"
            
            async with session.get(url) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    logger.error(f"API Error getting match details: {response.status}")
                    return None
        except Exception as e:
            logger.error(f"Error getting match details: {str(e)}")
            return None
    
    async def get_player_profile(self, game_name: str, tag_line: str):
        """Get complete player profile for verification"""
        try:
            # Get PUUID
            puuid = await self.get_puuid_by_riot_id(game_name, tag_line)
            if not puuid:
                return None
            
            # Get summoner info
            summoner = await self.get_summoner_by_puuid(puuid)
            if not summoner:
                return None
            
            # Get rank info
            rank_info = await self.get_tft_rank(summoner.get('id', ''))
            
            # Get last match
            matches = await self.get_match_history(puuid, 1)
            last_match = None
            if matches:
                match_data = await self.get_match_details(matches[0])
                if match_data:
                    # Find player in participants
                    for participant in match_data.get('info', {}).get('participants', []):
                        if participant.get('puuid') == puuid:
                            last_match = {
                                'placement': participant.get('placement'),
                                'game_datetime': match_data.get('info', {}).get('game_datetime'),
                                'match_id': matches[0]
                            }
                            break
            
            return {
                'puuid': puuid,
                'game_name': game_name,
                'tag_line': tag_line,
                'summoner_id': summoner.get('id'),
                'summoner_name': summoner.get('name'),
                'summoner_level': summoner.get('summonerLevel'),
                'profile_icon_id': summoner.get('profileIconId'),
                'rank_info': rank_info,
                'last_match': last_match,
                'verified_at': datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error getting player profile: {str(e)}")
            return None

class PlayerTracker:
    def __init__(self, riot_api: RiotAPI):
        self.riot_api = riot_api
        self.tracked_players = {}
        self.pending_confirmations = {}
        self.last_matches = {}  # Store last processed match ID for each player
        
    async def load_data(self):
        """Load tracked players and pending confirmations from files"""
        try:
            async with aiofiles.open(TRACKED_PLAYERS_FILE, 'r') as f:
                content = await f.read()
                self.tracked_players = json.loads(content)
                logger.info(f"Loaded {len(self.tracked_players)} tracked players")
        except FileNotFoundError:
            self.tracked_players = {}
            logger.info("No tracked players file found, starting fresh")
        except json.JSONDecodeError:
            self.tracked_players = {}
            logger.warning("Tracked players file corrupted, starting fresh")
        
        try:
            async with aiofiles.open(PENDING_CONFIRMATIONS_FILE, 'r') as f:
                content = await f.read()
                self.pending_confirmations = json.loads(content)
        except (FileNotFoundError, json.JSONDecodeError):
            self.pending_confirmations = {}
    
    async def save_data(self):
        """Save tracked players and pending confirmations to files"""
        try:
            async with aiofiles.open(TRACKED_PLAYERS_FILE, 'w') as f:
                await f.write(json.dumps(self.tracked_players, indent=2, default=str))
            
            async with aiofiles.open(PENDING_CONFIRMATIONS_FILE, 'w') as f:
                await f.write(json.dumps(self.pending_confirmations, indent=2, default=str))
        except Exception as e:
            logger.error(f"Error saving data: {str(e)}")
    
    async def add_pending_confirmation(self, user_id: int, player_data: dict):
        """Add player to pending confirmations"""
        key = f"{player_data['game_name']}#{player_data['tag_line']}".lower()
        self.pending_confirmations[key] = {
            'user_id': user_id,
            'player_data': player_data,
            'added_at': datetime.now().isoformat()
        }
        await self.save_data()
    
    async def confirm_tracking(self, user_id: int, riot_id: str) -> bool:
        """Confirm tracking for a player"""
        key = riot_id.lower()
        
        if key not in self.pending_confirmations:
            return False
        
        pending = self.pending_confirmations[key]
        if pending['user_id'] != user_id:
            return False
        
        # Move from pending to tracked
        player_data = pending['player_data']
        player_key = player_data['puuid']
        
        self.tracked_players[player_key] = {
            **player_data,
            'tracked_since': datetime.now().isoformat(),
            'last_checked': None,
            'last_match_id': None,
            'last_rank': player_data.get('rank_info', {})
        }
        
        # Remove from pending
        del self.pending_confirmations[key]
        
        await self.save_data()
        logger.info(f"Started tracking {riot_id}")
        return True
    
    async def remove_tracking(self, puuid: str):
        """Stop tracking a player"""
        if puuid in self.tracked_players:
            player_name = self.tracked_players[puuid]['game_name']
            del self.tracked_players[puuid]
            await self.save_data()
            logger.info(f"Stopped tracking {player_name}")
            return True
        return False
    
    async def check_player_update(self, puuid: str, player_data: dict):
        """Check for new matches and rank updates"""
        try:
            # Get recent matches
            matches = await self.riot_api.get_match_history(puuid, 5)
            if not matches:
                return None
            
            # Get last tracked match
            tracked_player = self.tracked_players.get(puuid, {})
            last_match_id = tracked_player.get('last_match_id')
            
            # Check if there's a new match
            new_matches = []
            if last_match_id:
                for match_id in matches:
                    if match_id == last_match_id:
                        break
                    new_matches.append(match_id)
            else:
                # First time checking, only consider the latest match
                new_matches = [matches[0]] if matches else []
            
            # Get rank info
            current_rank = player_data.get('rank_info', {})
            last_rank = tracked_player.get('last_rank', {})
            
            updates = {
                'new_matches': [],
                'rank_changed': False,
                'rank_up': False,
                'rank_down': False
            }
            
            # Process new matches
            for match_id in new_matches[:3]:  # Limit to 3 new matches per check
                match_data = await self.riot_api.get_match_details(match_id)
                if match_data:
                    # Find player in match
                    for participant in match_data.get('info', {}).get('participants', []):
                        if participant.get('puuid') == puuid:
                            match_info = {
                                'match_id': match_id,
                                'placement': participant.get('placement'),
                                'game_datetime': match_data.get('info', {}).get('game_datetime'),
                                'level': participant.get('level'),
                                'companion': participant.get('companion', {}).get('item_ID'),
                                'traits': participant.get('traits', []),
                                'units': participant.get('units', [])
                            }
                            updates['new_matches'].append(match_info)
                            break
            
            # Check rank changes
            if current_rank and last_rank:
                current_tier = current_rank.get('tier', 'UNRANKED')
                current_rank_num = current_rank.get('rank', 'IV')
                current_lp = current_rank.get('leaguePoints', 0)
                
                last_tier = last_rank.get('tier', 'UNRANKED')
                last_rank_num = last_rank.get('rank', 'IV')
                last_lp = last_rank.get('leaguePoints', 0)
                
                # Simple rank comparison
                tier_order = ['IRON', 'BRONZE', 'SILVER', 'GOLD', 'PLATINUM', 'DIAMOND', 'MASTER', 'GRANDMASTER', 'CHALLENGER']
                rank_order = ['IV', 'III', 'II', 'I']
                
                if current_tier != last_tier:
                    current_idx = tier_order.index(current_tier) if current_tier in tier_order else -1
                    last_idx = tier_order.index(last_tier) if last_tier in tier_order else -1
                    
                    if current_idx > last_idx:
                        updates['rank_changed'] = True
                        updates['rank_up'] = True
                    elif current_idx < last_idx:
                        updates['rank_changed'] = True
                        updates['rank_down'] = True
                elif current_rank_num != last_rank_num:
                    current_rank_idx = rank_order.index(current_rank_num) if current_rank_num in rank_order else -1
                    last_rank_idx = rank_order.index(last_rank_num) if last_rank_num in rank_order else -1
                    
                    if current_rank_idx > last_rank_idx:
                        updates['rank_changed'] = True
                        updates['rank_up'] = True
                    elif current_rank_idx < last_rank_idx:
                        updates['rank_changed'] = True
                        updates['rank_down'] = True
                elif abs(current_lp - last_lp) > 50:  # Significant LP change
                    updates['rank_changed'] = True
                    updates['rank_up'] = current_lp > last_lp
                    updates['rank_down'] = current_lp < last_lp
            
            # Update last match and rank
            if updates['new_matches']:
                self.tracked_players[puuid]['last_match_id'] = updates['new_matches'][0]['match_id']
            
            if current_rank:
                self.tracked_players[puuid]['last_rank'] = current_rank
            
            self.tracked_players[puuid]['last_checked'] = datetime.now().isoformat()
            await self.save_data()
            
            return updates if updates['new_matches'] or updates['rank_changed'] else None
            
        except Exception as e:
            logger.error(f"Error checking player update: {str(e)}")
            return None
    
    def get_tracked_players_list(self):
        """Get list of tracked players"""
        return list(self.tracked_players.values())
    
    def get_pending_confirmation(self, user_id: int, riot_id: str):
        """Get pending confirmation for a user"""
        key = riot_id.lower()
        pending = self.pending_confirmations.get(key)
        if pending and pending['user_id'] == user_id:
            return pending
        return None

# Initialize Riot API and Tracker
riot_api = RiotAPI(RIOT_API_KEY)
tracker = PlayerTracker(riot_api)

@bot.event
async def on_ready():
    logger.info(f'{bot.user} has connected to Discord!')
    logger.info(f'Channel ID: {DISCORD_CHANNEL_ID}')
    
    # Load tracked players
    await tracker.load_data()
    logger.info(f"Loaded {len(tracker.tracked_players)} tracked players")
    
    # Start the background task
    if not check_players_task.is_running():
        check_players_task.start()
    
    # Start APScheduler for periodic checks
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        check_players_task,
        trigger=IntervalTrigger(minutes=3),
        id='check_players',
        replace_existing=True
    )
    scheduler.start()
    
    # Change bot status
    await bot.change_presence(
        activity=discord.Activity(
            type=discord.ActivityType.watching,
            name=f"{len(tracker.tracked_players)} TFT players"
        )
    )

@tasks.loop(minutes=3)
async def check_players_task():
    """Check all tracked players for updates"""
    if DISCORD_CHANNEL_ID == 0:
        logger.error("DISCORD_CHANNEL_ID not set!")
        return
    
    channel = bot.get_channel(DISCORD_CHANNEL_ID)
    if not channel:
        logger.error(f"Channel {DISCORD_CHANNEL_ID} not found!")
        return
    
    if not tracker.tracked_players:
        return
    
    logger.info(f"Checking {len(tracker.tracked_players)} tracked players...")
    
    for puuid, player_data in list(tracker.tracked_players.items()):
        try:
            # Get current player profile
            current_profile = await riot_api.get_player_profile(
                player_data['game_name'],
                player_data['tag_line']
            )
            
            if not current_profile:
                logger.warning(f"Could not get profile for {player_data['game_name']}#{player_data['tag_line']}")
                continue
            
            # Check for updates
            updates = await tracker.check_player_update(puuid, current_profile)
            
            if updates:
                await send_update_notification(channel, player_data, current_profile, updates)
            
            # Rate limiting delay
            await asyncio.sleep(1)
            
        except Exception as e:
            logger.error(f"Error checking player {player_data.get('game_name', 'Unknown')}: {str(e)}")
    
    logger.info("Player check completed")

async def send_update_notification(channel, player_data, current_profile, updates):
    """Send notification about player updates"""
    try:
        player_name = f"{player_data['game_name']}#{player_data['tag_line']}"
        summoner_name = current_profile.get('summoner_name', player_name)
        
        # Create embed for new matches
        for match in updates['new_matches']:
            placement = match['placement']
            game_time = datetime.fromtimestamp(match['game_datetime'] / 1000)
            
            # Determine embed color based on placement
            if placement <= 4:
                color = discord.Color.green()
                emoji = "🎯"
            else:
                color = discord.Color.orange()
                emoji = "⚔️"
            
            embed = discord.Embed(
                title=f"{emoji} {summoner_name} vừa hoàn thành trận đấu TFT!",
                description=f"**Hạng:** #{placement}",
                color=color,
                timestamp=game_time
            )
            
            embed.set_thumbnail(url=f"http://ddragon.leagueoflegends.com/cdn/13.24.1/img/profileicon/{current_profile.get('profile_icon_id', 0)}.png")
            
            # Add rank info
            rank_info = current_profile.get('rank_info', {})
            if rank_info:
                tier = rank_info.get('tier', 'UNRANKED')
                division = rank_info.get('rank', '')
                lp = rank_info.get('leaguePoints', 0)
                wins = rank_info.get('wins', 0)
                losses = rank_info.get('losses', 0)
                
                rank_text = f"{tier.title()} {division}" if division else tier.title()
                embed.add_field(name="Rank hiện tại", value=f"{rank_text} ({lp} LP)", inline=True)
                
                if wins + losses > 0:
                    winrate = (wins / (wins + losses)) * 100
                    embed.add_field(name="Tỉ lệ thắng", value=f"{winrate:.1f}% ({wins}W/{losses}L)", inline=True)
            
            # Add match details
            embed.add_field(name="Thời gian", value=f"<t:{int(game_time.timestamp())}:R>", inline=False)
            
            # Add traits (top 3)
            traits = match.get('traits', [])
            active_traits = [t for t in traits if t.get('tier_current', 0) > 0]
            active_traits.sort(key=lambda x: (-x.get('tier_current', 0), -x.get('num_units', 0)))
            
            if active_traits:
                trait_text = ""
                for trait in active_traits[:3]:
                    name = trait.get('name', 'Unknown').replace('Set6_', '').replace('Set7_', '').title()
                    tier = trait.get('tier_current', 0)
                    trait_text += f"{name} (Tier {tier})\n"
                embed.add_field(name="Đội hình chính", value=trait_text, inline=True)
            
            # Add units (top 5)
            units = match.get('units', [])
            if units:
                unit_text = ""
                for unit in units[:5]:
                    name = unit.get('character_id', '').replace('TFT7_', '').replace('TFT6_', '').title()
                    tier = unit.get('tier', 1)
                    unit_text += f"{name} ⭐{tier}\n"
                embed.add_field(name="Tướng chính", value=unit_text, inline=True)
            
            await channel.send(embed=embed)
        
        # Send rank update notification
        if updates['rank_changed']:
            old_rank = player_data.get('last_rank', {})
            new_rank = current_profile.get('rank_info', {})
            
            old_tier = old_rank.get('tier', 'UNRANKED')
            old_division = old_rank.get('rank', '')
            old_lp = old_rank.get('leaguePoints', 0)
            
            new_tier = new_rank.get('tier', 'UNRANKED')
            new_division = new_rank.get('rank', '')
            new_lp = new_rank.get('leaguePoints', 0)
            
            old_rank_text = f"{old_tier.title()} {old_division}" if old_division else old_tier.title()
            new_rank_text = f"{new_tier.title()} {new_division}" if new_division else new_tier.title()
            
            if updates['rank_up']:
                embed = discord.Embed(
                    title=f"🎉 CHÚC MỪNG {summoner_name}! 🎉",
                    description=f"**ĐÃ LÊN HẠNG!**",
                    color=discord.Color.gold()
                )
                embed.add_field(name="Hạng cũ", value=f"{old_rank_text} ({old_lp} LP)", inline=True)
                embed.add_field(name="Hạng mới", value=f"{new_rank_text} ({new_lp} LP)", inline=True)
                embed.set_thumbnail(url="https://emojipedia-us.s3.dualstack.us-west-1.amazonaws.com/thumbs/120/twitter/322/party-popper_1f389.png")
            else:
                embed = discord.Embed(
                    title=f"💪 {summoner_name} ĐỪNG NẢN! 💪",
                    description=f"**CỐ LÊN! LẦN SAU SẼ TỐT HƠN!**",
                    color=discord.Color.blue()
                )
                embed.add_field(name="Hạng cũ", value=f"{old_rank_text} ({old_lp} LP)", inline=True)
                embed.add_field(name="Hạng hiện tại", value=f"{new_rank_text} ({new_lp} LP)", inline=True)
                embed.set_thumbnail(url="https://emojipedia-us.s3.dualstack.us-west-1.amazonaws.com/thumbs/120/twitter/322/flexed-biceps_1f4aa.png")
            
            await channel.send(embed=embed)
            
    except Exception as e:
        logger.error(f"Error sending notification: {str(e)}")

@bot.command(name='tracker')
async def tracker_command(ctx, *, riot_id: str):
    """Xác thực và hiển thị thông tin người chơi"""
    # Parse Riot ID (format: name#tag)
    if '#' not in riot_id:
        await ctx.send("❌ **Lỗi:** Vui lòng nhập đúng định dạng `Tên#Thẻ` (VD: `PlayerName#VN1`)")
        return
    
    game_name, tag_line = riot_id.split('#', 1)
    
    # Check if already tracked
    for player in tracker.tracked_players.values():
        if player['game_name'].lower() == game_name.lower() and player['tag_line'].lower() == tag_line.lower():
            await ctx.send(f"❌ **{riot_id}** đã được theo dõi rồi!")
            return
    
    # Check if pending confirmation exists
    pending = tracker.get_pending_confirmation(ctx.author.id, riot_id)
    if pending:
        await ctx.send(f"❌ **{riot_id}** đang chờ xác nhận! Sử dụng `!confirm {riot_id}` để xác nhận.")
        return
    
    await ctx.send(f"🔍 **Đang tìm kiếm thông tin cho {riot_id}...**")
    
    # Get player profile
    player_profile = await riot_api.get_player_profile(game_name, tag_line)
    
    if not player_profile:
        await ctx.send(f"❌ **Không tìm thấy người chơi {riot_id}**\nVui lòng kiểm tra lại tên và thẻ (tag).")
        return
    
    # Create verification embed
    embed = discord.Embed(
        title=f"✅ Tìm thấy người chơi: {riot_id}",
        color=discord.Color.green()
    )
    
    embed.set_thumbnail(url=f"http://ddragon.leagueoflegends.com/cdn/13.24.1/img/profileicon/{player_profile.get('profile_icon_id', 0)}.png")
    
    # Add summoner info
    embed.add_field(
        name="Thông tin Summoner",
        value=f"**Tên:** {player_profile.get('summoner_name', 'N/A')}\n"
              f"**Cấp độ:** {player_profile.get('summoner_level', 0)}",
        inline=False
    )
    
    # Add rank info
    rank_info = player_profile.get('rank_info', {})
    if rank_info:
        tier = rank_info.get('tier', 'UNRANKED')
        division = rank_info.get('rank', '')
        lp = rank_info.get('leaguePoints', 0)
        wins = rank_info.get('wins', 0)
        losses = rank_info.get('losses', 0)
        
        rank_text = f"{tier.title()} {division}" if division else tier.title()
        embed.add_field(
            name="Hạng TFT",
            value=f"**Rank:** {rank_text}\n"
                  f"**LP:** {lp}\n"
                  f"**Thắng/Thua:** {wins}/{losses}",
            inline=True
        )
        
        if wins + losses > 0:
            winrate = (wins / (wins + losses)) * 100
            embed.add_field(
                name="Tỉ lệ thắng",
                value=f"{winrate:.1f}%",
                inline=True
            )
    else:
        embed.add_field(
            name="Hạng TFT",
            value="Chưa xếp hạng",
            inline=True
        )
    
    # Add last match info
    last_match = player_profile.get('last_match')
    if last_match:
        placement = last_match.get('placement')
        game_time = datetime.fromtimestamp(last_match.get('game_datetime', 0) / 1000)
        
        embed.add_field(
            name="Trận đấu gần nhất",
            value=f"**Hạng:** #{placement}\n"
                  f"**Thời gian:** <t:{int(game_time.timestamp())}:R>",
            inline=False
        )
    
    embed.set_footer(text=f"Yêu cầu bởi {ctx.author.name}")
    
    await ctx.send(embed=embed)
    await ctx.send(f"📝 **Xác nhận theo dõi {riot_id}?**\nGõ `!confirm {riot_id}` để xác nhận.")
    
    # Add to pending confirmations
    await tracker.add_pending_confirmation(ctx.author.id, player_profile)

@bot.command(name='confirm')
async def confirm_command(ctx, *, riot_id: str):
    """Xác nhận theo dõi người chơi"""
    success = await tracker.confirm_tracking(ctx.author.id, riot_id)
    
    if success:
        await ctx.send(f"✅ **Đã bắt đầu theo dõi {riot_id}!**\nBot sẽ thông báo khi có trận đấu mới.")
        
        # Update bot status
        tracked_count = len(tracker.tracked_players)
        await bot.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.watching,
                name=f"{tracked_count} TFT players"
            )
        )
    else:
        await ctx.send(f"❌ **Không thể xác nhận {riot_id}**\nCó thể bạn chưa dùng lệnh `!tracker` trước đó, hoặc mã xác nhận đã hết hạn.")

@bot.command(name='unfollow')
async def unfollow_command(ctx, *, riot_id: str):
    """Dừng theo dõi người chơi"""
    # Find player by Riot ID
    target_puuid = None
    for puuid, player_data in tracker.tracked_players.items():
        player_riot_id = f"{player_data['game_name']}#{player_data['tag_line']}"
        if player_riot_id.lower() == riot_id.lower():
            target_puuid = puuid
            break
    
    if not target_puuid:
        await ctx.send(f"❌ **Không tìm thấy {riot_id} trong danh sách theo dõi**")
        return
    
    # Remove from tracking
    success = await tracker.remove_tracking(target_puuid)
    
    if success:
        await ctx.send(f"✅ **Đã dừng theo dõi {riot_id}**")
        
        # Update bot status
        tracked_count = len(tracker.tracked_players)
        await bot.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.watching,
                name=f"{tracked_count} TFT players"
            )
        )
    else:
        await ctx.send(f"❌ **Có lỗi xảy ra khi dừng theo dõi {riot_id}**")

@bot.command(name='list')
async def list_command(ctx):
    """Hiển thị danh sách người chơi đang được theo dõi"""
    players = tracker.get_tracked_players_list()
    
    if not players:
        await ctx.send("📭 **Danh sách theo dõi trống**\nSử dụng `!tracker Tên#Thẻ` để thêm người chơi.")
        return
    
    embed = discord.Embed(
        title=f"👥 Danh sách theo dõi ({len(players)}/8)",
        description="Người chơi đang được bot theo dõi",
        color=discord.Color.blue()
    )
    
    for i, player in enumerate(players, 1):
        riot_id = f"{player['game_name']}#{player['tag_line']}"
        rank_info = player.get('last_rank', {})
        
        if rank_info:
            tier = rank_info.get('tier', 'UNRANKED')
            division = rank_info.get('rank', '')
            lp = rank_info.get('leaguePoints', 0)
            rank_text = f"{tier.title()} {division} ({lp} LP)" if division else f"{tier.title()} ({lp} LP)"
        else:
            rank_text = "Chưa xếp hạng"
        
        tracked_since = datetime.fromisoformat(player['tracked_since'])
        
        embed.add_field(
            name=f"{i}. {riot_id}",
            value=f"**Rank:** {rank_text}\n"
                  f"**Theo dõi từ:** <t:{int(tracked_since.timestamp())}:R>",
            inline=False
        )
    
    embed.set_footer(text=f"Sử dụng !unfollow Tên#Thẻ để dừng theo dõi")
    
    await ctx.send(embed=embed)

@bot.command(name='forcecheck')
@commands.has_permissions(administrator=True)
async def force_check(ctx):
    """Kiểm tra ngay lập tức (Admin only)"""
    await ctx.send("🔍 **Đang kiểm tra ngay lập tức...**")
    await check_players_task()
    await ctx.send("✅ **Kiểm tra hoàn tất!**")

@bot.command(name='status')
async def status_command(ctx):
    """Hiển thị trạng thái của bot"""
    embed = discord.Embed(
        title="🤖 TFT Tracker Bot Status",
        color=discord.Color.green(),
        timestamp=datetime.now()
    )
    
    # Bot info
    embed.add_field(
        name="Bot Info",
        value=f"**Ping:** {round(bot.latency * 1000)}ms\n"
              f"**Uptime:** <t:{int(bot.start_time.timestamp())}:R>\n"
              f"**Server:** {len(bot.guilds)} server(s)",
        inline=True
    )
    
    # Tracking info
    players_count = len(tracker.tracked_players)
    pending_count = len(tracker.pending_confirmations)
    
    embed.add_field(
        name="Tracking",
        value=f"**Đang theo dõi:** {players_count}/8 players\n"
              f"**Chờ xác nhận:** {pending_count}\n"
              f"**Kênh thông báo:** <#{DISCORD_CHANNEL_ID}>",
        inline=True
    )
    
    # Last check
    last_check = None
    for player in tracker.tracked_players.values():
        if player.get('last_checked'):
            player_time = datetime.fromisoformat(player['last_checked'])
            if not last_check or player_time > last_check:
                last_check = player_time
    
    if last_check:
        embed.add_field(
            name="Hoạt động",
            value=f"**Lần check cuối:** <t:{int(last_check.timestamp())}:R>\n"
                  f"**Check mỗi:** 3 phút\n"
                  f"**Task đang chạy:** {check_players_task.is_running()}",
            inline=True
        )
    
    embed.set_footer(text=f"Yêu cầu bởi {ctx.author.name}")
    
    await ctx.send(embed=embed)

@bot.command(name='help')
async def help_command(ctx):
    """Hiển thị hướng dẫn sử dụng"""
    embed = discord.Embed(
        title="📚 Hướng dẫn sử dụng TFT Tracker Bot",
        description="Bot theo dõi trận đấu TFT tự động thông báo khi có trận mới",
        color=discord.Color.purple()
    )
    
    commands_list = [
        ("!tracker Tên#Thẻ", "Xác thực và xem thông tin người chơi"),
        ("!confirm Tên#Thẻ", "Xác nhận theo dõi người chơi"),
        ("!unfollow Tên#Thẻ", "Dừng theo dõi người chơi"),
        ("!list", "Xem danh sách người chơi đang theo dõi"),
        ("!status", "Xem trạng thái bot"),
        ("!forcecheck", "Kiểm tra ngay lập tức (Admin only)"),
        ("!help", "Hiển thị hướng dẫn này")
    ]
    
    for cmd, desc in commands_list:
        embed.add_field(name=cmd, value=desc, inline=False)
    
    embed.add_field(
        name="📝 Lưu ý",
        value="• Bot có thể theo dõi tối đa 8 người chơi\n"
              "• Kiểm tra tự động mỗi 3 phút\n"
              "• Thông báo khi có trận đấu mới hoặc thay đổi rank\n"
              "• Server Việt Nam (VNG) hỗ trợ Riot ID",
        inline=False
    )
    
    embed.set_footer(text="Bot được tạo bởi TFT Vietnam Community")
    
    await ctx.send(embed=embed)

@bot.event
async def on_command_error(ctx, error):
    """Handle command errors"""
    if isinstance(error, commands.CommandNotFound):
        await ctx.send(f"❌ **Lệnh không tồn tại!** Gõ `!help` để xem các lệnh có sẵn.")
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(f"❌ **Thiếu tham số!** Vui lòng kiểm tra lại cú pháp lệnh.")
    elif isinstance(error, commands.BadArgument):
        await ctx.send(f"❌ **Tham số không hợp lệ!** Vui lòng kiểm tra lại.")
    elif isinstance(error, commands.MissingPermissions):
        await ctx.send(f"❌ **Bạn không có quyền sử dụng lệnh này!**")
    else:
        logger.error(f"Command error: {str(error)}")
        await ctx.send(f"❌ **Đã xảy ra lỗi:** {str(error)[:100]}")

# Initialize bot start time
bot.start_time = datetime.now()

async def run_flask():
    """Run Flask in background"""
    port = int(os.getenv('PORT', 8080))
    app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)

async def main():
    """Main function"""
    # Create required files if they don't exist
    for file in [TRACKED_PLAYERS_FILE, PENDING_CONFIRMATIONS_FILE]:
        if not os.path.exists(file):
            async with aiofiles.open(file, 'w') as f:
                await f.write('{}')
    
    # Start the bot
    await bot.start(DISCORD_TOKEN)

if __name__ == "__main__":
    # Check required environment variables
    required_vars = ['DISCORD_TOKEN', 'RIOT_API_KEY', 'DISCORD_CHANNEL_ID']
    missing_vars = [var for var in required_vars if not os.getenv(var)]
    
    if missing_vars:
        logger.error(f"Missing environment variables: {', '.join(missing_vars)}")
        exit(1)
    
    # Import threading for Flask
    import threading
    
    # Start Flask in a separate thread
    flask_thread = threading.Thread(
        target=lambda: app.run(host='0.0.0.0', port=int(os.getenv('PORT', 8080)), debug=False, use_reloader=False),
        daemon=True
    )
    flask_thread.start()
    
    # Run the Discord bot
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot shutting down...")
    finally:
        # Cleanup
        asyncio.run(riot_api.close())
