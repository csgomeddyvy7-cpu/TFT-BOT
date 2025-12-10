import discord
from discord.ext import commands, tasks
import aiohttp
import asyncio
import json
import os
from datetime import datetime, timedelta
import logging
import aiofiles
from bs4 import BeautifulSoup
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from flask import Flask, jsonify
from typing import Dict, List, Optional
import re

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
bot = commands.Bot(command_prefix='!', intents=intents, help_command=None)

# Configuration
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
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

class TrackerGGScraper:
    def __init__(self):
        self.session = None
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate',
            'DNT': '1',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
        }
    
    async def get_session(self):
        if not self.session or self.session.closed:
            self.session = aiohttp.ClientSession(headers=self.headers)
        return self.session
    
    async def close(self):
        if self.session and not self.session.closed:
            await self.session.close()
    
    async def get_player_profile(self, game_name: str, tag_line: str, region: str = 'vn'):
        """Get player profile from tracker.gg"""
        try:
            # Format URL for tracker.gg
            encoded_name = f"{game_name}%23{tag_line}"
            url = f"https://tracker.gg/tft/profile/riot/{region}/{encoded_name}/overview"
            
            logger.info(f"Fetching from tracker.gg: {url}")
            
            session = await self.get_session()
            async with session.get(url, timeout=15) as response:
                if response.status == 200:
                    html = await response.text()
                    return await self.parse_player_profile(html, game_name, tag_line, region)
                elif response.status == 404:
                    logger.warning(f"Player not found on tracker.gg: {game_name}#{tag_line}")
                    return None
                else:
                    logger.error(f"Tracker.gg error: {response.status} for {game_name}#{tag_line}")
                    return None
        except asyncio.TimeoutError:
            logger.error(f"Timeout fetching from tracker.gg for {game_name}#{tag_line}")
            return None
        except Exception as e:
            logger.error(f"Error fetching from tracker.gg: {str(e)}")
            return None
    
    async def parse_player_profile(self, html: str, game_name: str, tag_line: str, region: str):
        """Parse HTML from tracker.gg to extract player profile"""
        soup = BeautifulSoup(html, 'lxml')
        
        # Extract basic player info
        player_info = {
            'game_name': game_name,
            'tag_line': tag_line,
            'region': region,
            'verified_at': datetime.now().isoformat()
        }
        
        try:
            # Get summoner name
            name_elem = soup.select_one('.trn-profile-header__name')
            if name_elem:
                player_info['summoner_name'] = name_elem.text.strip()
            
            # Get rank info
            rank_div = soup.select_one('.rating-summary__rank')
            if rank_div:
                rank_text = rank_div.text.strip()
                player_info['rank'] = rank_text
            
            # Get rank details (tier, division, LP)
            tier_elem = soup.select_one('.rating-summary__tier')
            if tier_elem:
                player_info['tier'] = tier_elem.text.strip()
            
            division_elem = soup.select_one('.rating-summary__division')
            if division_elem:
                player_info['division'] = division_elem.text.strip()
            
            rating_elem = soup.select_one('.rating-summary__rating')
            if rating_elem:
                lp_text = rating_elem.text.strip()
                # Extract LP number
                lp_match = re.search(r'(\d+)\s*LP', lp_text)
                if lp_match:
                    player_info['lp'] = int(lp_match.group(1))
            
            # Get win/loss stats
            stat_labels = soup.select('.stat__label')
            stat_values = soup.select('.stat__value')
            
            stats = {}
            for label, value in zip(stat_labels, stat_values):
                label_text = label.text.strip().lower()
                value_text = value.text.strip()
                stats[label_text] = value_text
                
                if 'top 4' in label_text:
                    player_info['top_4'] = value_text
                elif 'games' in label_text:
                    player_info['total_games'] = value_text
                elif 'win' in label_text and 'rate' in label_text:
                    player_info['win_rate'] = value_text
            
            # Get recent matches
            recent_matches = []
            match_cards = soup.select('.match-history .match-card')[:5]  # Last 5 matches
            
            for match in match_cards:
                match_data = {}
                
                # Get placement
                placement_elem = match.select_one('.placement')
                if placement_elem:
                    placement_text = placement_elem.text.strip()
                    # Extract number from placement (e.g., "1st" -> 1)
                    placement_match = re.search(r'(\d+)', placement_text)
                    if placement_match:
                        match_data['placement'] = int(placement_match.group(1))
                
                # Get match time
                time_elem = match.select_one('.match-card__time')
                if time_elem:
                    match_data['time_text'] = time_elem.text.strip()
                
                # Get match length
                length_elem = match.select_one('.match-card__length')
                if length_elem:
                    match_data['length'] = length_elem.text.strip()
                
                # Get traits (augments/champions)
                traits = []
                trait_elems = match.select('.tft-augment, .tft-champion')
                for trait in trait_elems:
                    trait_name = trait.get('title') or trait.get('alt') or trait.text.strip()
                    if trait_name:
                        traits.append(trait_name)
                
                if traits:
                    match_data['traits'] = traits[:8]  # Limit to 8 traits
                
                # Get match ID from data attribute
                match_id = match.get('data-match-id')
                if match_id:
                    match_data['match_id'] = match_id
                
                if match_data:
                    recent_matches.append(match_data)
            
            player_info['recent_matches'] = recent_matches
            
            # If we have recent matches, get the latest one
            if recent_matches:
                player_info['last_match'] = recent_matches[0]
            
            # Get additional stats
            stats_elements = soup.select('.stat.align-center')
            for stat in stats_elements:
                label = stat.select_one('.label')
                value = stat.select_one('.value')
                if label and value:
                    label_text = label.text.strip().lower()
                    value_text = value.text.strip()
                    
                    if 'avg. placement' in label_text:
                        player_info['avg_placement'] = value_text
                    elif 'top 4 rate' in label_text:
                        player_info['top_4_rate'] = value_text
            
            logger.info(f"Successfully parsed data for {game_name}#{tag_line}")
            return player_info
            
        except Exception as e:
            logger.error(f"Error parsing tracker.gg HTML: {str(e)}")
            return player_info
    
    async def get_player_stats(self, game_name: str, tag_line: str, region: str = 'vn'):
        """Get detailed player stats"""
        try:
            encoded_name = f"{game_name}%23{tag_line}"
            url = f"https://tracker.gg/tft/profile/riot/{region}/{encoded_name}/competitive"
            
            session = await self.get_session()
            async with session.get(url, timeout=15) as response:
                if response.status == 200:
                    html = await response.text()
                    return await self.parse_player_stats(html)
                return None
        except Exception as e:
            logger.error(f"Error getting player stats: {str(e)}")
            return None
    
    async def parse_player_stats(self, html: str):
        """Parse detailed stats from competitive page"""
        soup = BeautifulSoup(html, 'lxml')
        stats = {}
        
        try:
            # Get ranked stats
            stats_table = soup.select('.trn-table__row')
            for row in stats_table:
                cells = row.select('.trn-table__cell')
                if len(cells) >= 2:
                    key = cells[0].text.strip()
                    value = cells[1].text.strip()
                    stats[key] = value
            
            return stats
        except Exception as e:
            logger.error(f"Error parsing stats: {str(e)}")
            return stats

class PlayerTracker:
    def __init__(self, scraper: TrackerGGScraper):
        self.scraper = scraper
        self.tracked_players = {}
        self.pending_confirmations = {}
        
    async def load_data(self):
        """Load tracked players and pending confirmations from files"""
        try:
            if os.path.exists(TRACKED_PLAYERS_FILE):
                async with aiofiles.open(TRACKED_PLAYERS_FILE, 'r') as f:
                    content = await f.read()
                    if content.strip():
                        self.tracked_players = json.loads(content)
                        logger.info(f"Loaded {len(self.tracked_players)} tracked players")
                    else:
                        self.tracked_players = {}
        except Exception as e:
            self.tracked_players = {}
            logger.warning(f"Error loading tracked players: {str(e)}")
        
        try:
            if os.path.exists(PENDING_CONFIRMATIONS_FILE):
                async with aiofiles.open(PENDING_CONFIRMATIONS_FILE, 'r') as f:
                    content = await f.read()
                    if content.strip():
                        self.pending_confirmations = json.loads(content)
                    else:
                        self.pending_confirmations = {}
        except Exception as e:
            self.pending_confirmations = {}
            logger.warning(f"Error loading pending confirmations: {str(e)}")
    
    async def save_data(self):
        """Save tracked players and pending confirmations to files"""
        try:
            async with aiofiles.open(TRACKED_PLAYERS_FILE, 'w') as f:
                await f.write(json.dumps(self.tracked_players, indent=2, ensure_ascii=False))
        except Exception as e:
            logger.error(f"Error saving tracked players: {str(e)}")
        
        try:
            async with aiofiles.open(PENDING_CONFIRMATIONS_FILE, 'w') as f:
                await f.write(json.dumps(self.pending_confirmations, indent=2, ensure_ascii=False))
        except Exception as e:
            logger.error(f"Error saving pending confirmations: {str(e)}")
    
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
        
        player_data = pending['player_data']
        player_key = f"{player_data['game_name']}#{player_data['tag_line']}".lower()
        
        # Get fresh data before tracking
        fresh_data = await self.scraper.get_player_profile(
            player_data['game_name'],
            player_data['tag_line'],
            player_data.get('region', 'vn')
        )
        
        if not fresh_data:
            return False
        
        self.tracked_players[player_key] = {
            **fresh_data,
            'tracked_since': datetime.now().isoformat(),
            'last_checked': datetime.now().isoformat(),
            'last_match_id': fresh_data.get('last_match', {}).get('match_id') if fresh_data.get('last_match') else None
        }
        
        del self.pending_confirmations[key]
        
        await self.save_data()
        logger.info(f"Started tracking {riot_id}")
        return True
    
    async def remove_tracking(self, riot_id: str):
        """Stop tracking a player"""
        key = riot_id.lower()
        
        if key in self.tracked_players:
            del self.tracked_players[key]
            await self.save_data()
            logger.info(f"Stopped tracking {riot_id}")
            return True
        return False
    
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
    
    async def update_player_data(self, player_key: str):
        """Update data for a specific player"""
        try:
            player_data = self.tracked_players.get(player_key)
            if not player_data:
                return None, None
            
            # Get fresh data from tracker.gg
            fresh_data = await self.scraper.get_player_profile(
                player_data['game_name'],
                player_data['tag_line'],
                player_data.get('region', 'vn')
            )
            
            if not fresh_data:
                return None, None
            
            # Check for new matches
            old_match_id = player_data.get('last_match_id')
            new_match = fresh_data.get('last_match', {})
            new_match_id = new_match.get('match_id')
            
            new_matches = []
            rank_update = None
            
            # If match ID has changed, there's a new match
            if new_match_id and old_match_id != new_match_id:
                new_matches.append(new_match)
            
            # Check for rank changes
            old_rank = player_data.get('rank', 'Unranked')
            new_rank = fresh_data.get('rank', 'Unranked')
            
            if old_rank != new_rank:
                rank_update = {
                    'old_rank': old_rank,
                    'new_rank': new_rank,
                    'old_tier': player_data.get('tier'),
                    'new_tier': fresh_data.get('tier'),
                    'old_lp': player_data.get('lp'),
                    'new_lp': fresh_data.get('lp')
                }
            
            # Update player data
            self.tracked_players[player_key].update({
                **fresh_data,
                'last_checked': datetime.now().isoformat(),
                'last_match_id': new_match_id
            })
            
            await self.save_data()
            
            return new_matches, rank_update
            
        except Exception as e:
            logger.error(f"Error updating player data: {str(e)}")
            return None, None

# Initialize scraper and tracker
scraper = TrackerGGScraper()
tracker = PlayerTracker(scraper)

@bot.event
async def on_ready():
    logger.info(f'{bot.user} has connected to Discord!')
    logger.info(f'Channel ID: {DISCORD_CHANNEL_ID}')
    
    await tracker.load_data()
    logger.info(f"Loaded {len(tracker.tracked_players)} tracked players")
    
    if not check_players_task.is_running():
        check_players_task.start()
    
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        check_players_task,
        trigger=IntervalTrigger(minutes=3),
        id='check_players',
        replace_existing=True
    )
    scheduler.start()
    
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
    
    for player_key in list(tracker.tracked_players.keys()):
        try:
            new_matches, rank_update = await tracker.update_player_data(player_key)
            
            if new_matches or rank_update:
                player_data = tracker.tracked_players[player_key]
                await send_update_notification(channel, player_data, new_matches, rank_update)
            
            # Delay to avoid rate limiting
            await asyncio.sleep(2)
            
        except Exception as e:
            logger.error(f"Error checking player {player_key}: {str(e)}")
    
    logger.info("Player check completed")

async def send_update_notification(channel, player_data: dict, new_matches: list, rank_update: dict):
    """Send update notifications to Discord"""
    try:
        player_name = f"{player_data['game_name']}#{player_data['tag_line']}"
        summoner_name = player_data.get('summoner_name', player_name)
        
        # Send match notifications
        for match in new_matches:
            placement = match.get('placement', 8)
            time_text = match.get('time_text', 'Vừa xong')
            
            color = discord.Color.green() if placement <= 4 else discord.Color.orange()
            emoji = "🎯" if placement <= 4 else "⚔️"
            
            embed = discord.Embed(
                title=f"{emoji} {summoner_name} vừa hoàn thành trận đấu TFT!",
                description=f"**Hạng:** #{placement}",
                color=color,
                timestamp=datetime.now()
            )
            
            # Add rank info
            rank = player_data.get('rank', 'Unranked')
            tier = player_data.get('tier', '')
            lp = player_data.get('lp', 0)
            
            if tier:
                rank_text = f"{tier} {player_data.get('division', '')}".strip()
                embed.add_field(name="Rank hiện tại", value=f"{rank_text} ({lp} LP)", inline=True)
            else:
                embed.add_field(name="Rank", value=rank, inline=True)
            
            # Add match info
            embed.add_field(name="Thời gian", value=time_text, inline=True)
            
            # Add traits if available
            traits = match.get('traits', [])
            if traits:
                trait_text = ""
                for trait in traits[:5]:
                    trait_text += f"• {trait}\n"
                embed.add_field(name="Đội hình/Augments", value=trait_text[:1000], inline=False)
            
            # Add stats if available
            if player_data.get('top_4'):
                embed.add_field(name="Top 4", value=player_data['top_4'], inline=True)
            if player_data.get('win_rate'):
                embed.add_field(name="Tỉ lệ thắng", value=player_data['win_rate'], inline=True)
            
            await channel.send(embed=embed)
        
        # Send rank update notification
        if rank_update:
            old_rank = rank_update.get('old_rank', 'Unranked')
            new_rank = rank_update.get('new_rank', 'Unranked')
            old_tier = rank_update.get('old_tier')
            new_tier = rank_update.get('new_tier')
            old_lp = rank_update.get('old_lp', 0)
            new_lp = rank_update.get('new_lp', 0)
            
            # Determine if rank went up
            is_up = False
            if old_tier and new_tier:
                # Simple tier comparison
                tier_order = ['Iron', 'Bronze', 'Silver', 'Gold', 'Platinum', 'Diamond', 'Master', 'Grandmaster', 'Challenger']
                old_idx = tier_order.index(old_tier) if old_tier in tier_order else -1
                new_idx = tier_order.index(new_tier) if new_tier in tier_order else -1
                is_up = new_idx > old_idx
            elif new_lp > old_lp + 20:  # Significant LP gain
                is_up = True
            
            if is_up:
                embed = discord.Embed(
                    title=f"🎉 CHÚC MỪNG {summoner_name}! 🎉",
                    description=f"**ĐÃ LÊN HẠNG!**",
                    color=discord.Color.gold()
                )
                embed.add_field(name="Hạng cũ", value=f"{old_rank} ({old_lp} LP)", inline=True)
                embed.add_field(name="Hạng mới", value=f"{new_rank} ({new_lp} LP)", inline=True)
                embed.set_thumbnail(url="https://emojipedia-us.s3.dualstack.us-west-1.amazonaws.com/thumbs/120/twitter/322/party-popper_1f389.png")
            else:
                embed = discord.Embed(
                    title=f"💪 {summoner_name} ĐỪNG NẢN! 💪",
                    description=f"**CỐ LÊN! LẦN SAU SẼ TỐT HƠN!**",
                    color=discord.Color.blue()
                )
                embed.add_field(name="Hạng cũ", value=f"{old_rank} ({old_lp} LP)", inline=True)
                embed.add_field(name="Hạng hiện tại", value=f"{new_rank} ({new_lp} LP)", inline=True)
                embed.set_thumbnail(url="https://emojipedia-us.s3.dualstack.us-west-1.amazonaws.com/thumbs/120/twitter/322/flexed-biceps_1f4aa.png")
            
            await channel.send(embed=embed)
            
    except Exception as e:
        logger.error(f"Error sending notification: {str(e)}")

@bot.command(name='tracker')
async def tracker_command(ctx, *, riot_id: str):
    """Xác thực và hiển thị thông tin người chơi"""
    if '#' not in riot_id:
        await ctx.send("❌ **Lỗi:** Vui lòng nhập đúng định dạng `Tên#Thẻ` (VD: `PlayerName#VN1`)")
        return
    
    game_name, tag_line = riot_id.split('#', 1)
    
    # Check if already tracked
    for player in tracker.tracked_players.values():
        if player['game_name'].lower() == game_name.lower() and player['tag_line'].lower() == tag_line.lower():
            await ctx.send(f"❌ **{riot_id}** đã được theo dõi rồi!")
            return
    
    # Check if pending
    pending = tracker.get_pending_confirmation(ctx.author.id, riot_id)
    if pending:
        await ctx.send(f"❌ **{riot_id}** đang chờ xác nhận! Sử dụng `!confirm {riot_id}` để xác nhận.")
        return
    
    await ctx.send(f"🔍 **Đang tìm kiếm thông tin cho {riot_id} trên tracker.gg...**")
    
    # Get player data from tracker.gg
    player_data = await scraper.get_player_profile(game_name, tag_line, 'vn')
    
    if not player_data:
        # Try other common regions
        for region in ['na', 'eu', 'kr', 'apac']:
            player_data = await scraper.get_player_profile(game_name, tag_line, region)
            if player_data:
                player_data['region'] = region
                break
        
        if not player_data:
            await ctx.send(f"❌ **Không tìm thấy người chơi {riot_id} trên tracker.gg**\nVui lòng kiểm tra lại tên, thẻ và đảm bảo tài khoản đã public.")
            return
    
    # Create verification embed
    embed = discord.Embed(
        title=f"✅ Tìm thấy người chơi trên tracker.gg: {riot_id}",
        color=discord.Color.green()
    )
    
    # Add player info
    summoner_name = player_data.get('summoner_name', riot_id)
    embed.add_field(
        name="Thông tin người chơi",
        value=f"**Tên:** {summoner_name}\n**Region:** {player_data.get('region', 'vn').upper()}",
        inline=False
    )
    
    # Add rank info
    rank = player_data.get('rank', 'Chưa xếp hạng')
    tier = player_data.get('tier', '')
    lp = player_data.get('lp', 0)
    
    if tier:
        rank_text = f"{tier} {player_data.get('division', '')}".strip()
        embed.add_field(
            name="Hạng TFT",
            value=f"**Rank:** {rank_text}\n**LP:** {lp}",
            inline=True
        )
    else:
        embed.add_field(
            name="Hạng TFT",
            value=rank,
            inline=True
        )
    
    # Add stats
    stats_fields = []
    if player_data.get('total_games'):
        stats_fields.append(f"**Tổng trận:** {player_data['total_games']}")
    if player_data.get('top_4'):
        stats_fields.append(f"**Top 4:** {player_data['top_4']}")
    if player_data.get('win_rate'):
        stats_fields.append(f"**Tỉ lệ thắng:** {player_data['win_rate']}")
    if player_data.get('avg_placement'):
        stats_fields.append(f"**Hạng trung bình:** {player_data['avg_placement']}")
    
    if stats_fields:
        embed.add_field(
            name="Thống kê",
            value="\n".join(stats_fields),
            inline=True
        )
    
    # Add last match info
    last_match = player_data.get('last_match')
    if last_match:
        placement = last_match.get('placement', 'N/A')
        time_text = last_match.get('time_text', 'Gần đây')
        
        embed.add_field(
            name="Trận đấu gần nhất",
            value=f"**Hạng:** #{placement}\n**Thời gian:** {time_text}",
            inline=False
        )
    
    embed.set_footer(text=f"Yêu cầu bởi {ctx.author.name}")
    
    await ctx.send(embed=embed)
    await ctx.send(f"📝 **Xác nhận theo dõi {riot_id}?**\nGõ `!confirm {riot_id}` để xác nhận.")
    
    # Add to pending confirmations
    await tracker.add_pending_confirmation(ctx.author.id, player_data)

@bot.command(name='confirm')
async def confirm_command(ctx, *, riot_id: str):
    """Xác nhận theo dõi người chơi"""
    success = await tracker.confirm_tracking(ctx.author.id, riot_id)
    
    if success:
        await ctx.send(f"✅ **Đã bắt đầu theo dõi {riot_id}!**\nBot sẽ thông báo khi có trận đấu mới (kiểm tra mỗi 3 phút).")
        
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
    success = await tracker.remove_tracking(riot_id)
    
    if success:
        await ctx.send(f"✅ **Đã dừng theo dõi {riot_id}**")
        
        tracked_count = len(tracker.tracked_players)
        await bot.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.watching,
                name=f"{tracked_count} TFT players"
            )
        )
    else:
        await ctx.send(f"❌ **Không tìm thấy {riot_id} trong danh sách theo dõi**")

@bot.command(name='list')
async def list_command(ctx):
    """Hiển thị danh sách người chơi đang được theo dõi"""
    players = tracker.get_tracked_players_list()
    
    if not players:
        await ctx.send("📭 **Danh sách theo dõi trống**\nSử dụng `!tracker Tên#Thẻ` để thêm người chơi.")
        return
    
    embed = discord.Embed(
        title=f"👥 Danh sách theo dõi ({len(players)}/8)",
        description="Người chơi đang được bot theo dõi từ tracker.gg",
        color=discord.Color.blue()
    )
    
    for i, player in enumerate(players, 1):
        riot_id = f"{player['game_name']}#{player['tag_line']}"
        rank = player.get('rank', 'Unranked')
        tier = player.get('tier', '')
        lp = player.get('lp', 0)
        
        if tier:
            rank_text = f"{tier} {player.get('division', '')}".strip()
            rank_info = f"{rank_text} ({lp} LP)"
        else:
            rank_info = rank
        
        tracked_since = datetime.fromisoformat(player['tracked_since'])
        last_checked = player.get('last_checked')
        
        value_text = f"**Rank:** {rank_info}\n"
        value_text += f"**Theo dõi từ:** <t:{int(tracked_since.timestamp())}:R>\n"
        
        if last_checked:
            last_time = datetime.fromisoformat(last_checked)
            value_text += f"**Kiểm tra lần cuối:** <t:{int(last_time.timestamp())}:R>"
        
        embed.add_field(
            name=f"{i}. {riot_id}",
            value=value_text,
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
              f"**Uptime:** Online\n"
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
    
    # Source info
    embed.add_field(
        name="Nguồn dữ liệu",
        value="**Tracker.gg**\n"
              "**Kiểm tra mỗi:** 3 phút\n"
              "**Dữ liệu:** Real-time",
        inline=True
    )
    
    await ctx.send(embed=embed)

@bot.command(name='bothelp')
async def bothelp_command(ctx):
    """Hiển thị hướng dẫn sử dụng"""
    embed = discord.Embed(
        title="📚 Hướng dẫn sử dụng TFT Tracker Bot",
        description="Bot theo dõi trận đấu TFT tự động thông báo khi có trận mới (sử dụng tracker.gg)",
        color=discord.Color.purple()
    )
    
    commands_list = [
        ("!tracker Tên#Thẻ", "Xác thực và xem thông tin người chơi trên tracker.gg"),
        ("!confirm Tên#Thẻ", "Xác nhận theo dõi người chơi"),
        ("!unfollow Tên#Thẻ", "Dừng theo dõi người chơi"),
        ("!list", "Xem danh sách người chơi đang theo dõi"),
        ("!status", "Xem trạng thái bot"),
        ("!forcecheck", "Kiểm tra ngay lập tức (Admin only)"),
        ("!bothelp", "Hiển thị hướng dẫn này")
    ]
    
    for cmd, desc in commands_list:
        embed.add_field(name=cmd, value=desc, inline=False)
    
    embed.add_field(
        name="📝 Lưu ý quan trọng",
        value="• Bot có thể theo dõi tối đa 8 người chơi\n"
              "• Kiểm tra tự động mỗi 3 phút\n"
              "• Dữ liệu được lấy từ tracker.gg\n"
              "• Tài khoản cần public trên tracker.gg\n"
              "• Region mặc định: VN (có thể tự động detect)",
        inline=False
    )
    
    embed.set_footer(text="Bot sử dụng tracker.gg - Không cần Riot API Key")
    
    await ctx.send(embed=embed)

@bot.event
async def on_command_error(ctx, error):
    """Handle command errors"""
    if isinstance(error, commands.CommandNotFound):
        await ctx.send(f"❌ **Lệnh không tồn tại!** Gõ `!bothelp` để xem các lệnh có sẵn.")
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(f"❌ **Thiếu tham số!** Vui lòng kiểm tra lại cú pháp lệnh.")
    elif isinstance(error, commands.BadArgument):
        await ctx.send(f"❌ **Tham số không hợp lệ!** Vui lòng kiểm tra lại.")
    elif isinstance(error, commands.MissingPermissions):
        await ctx.send(f"❌ **Bạn không có quyền sử dụng lệnh này!**")
    else:
        logger.error(f"Command error: {str(error)}")
        await ctx.send(f"❌ **Đã xảy ra lỗi:** {str(error)[:100]}")

async def init_files():
    """Initialize required files if they don't exist"""
    for file in [TRACKED_PLAYERS_FILE, PENDING_CONFIRMATIONS_FILE]:
        if not os.path.exists(file):
            async with aiofiles.open(file, 'w') as f:
                await f.write('{}')

def run_bot():
    """Run the Discord bot"""
    # Initialize files
    asyncio.run(init_files())
    
    # Run the bot
    bot.run(DISCORD_TOKEN)

if __name__ == "__main__":
    # Check required environment variables
    if not DISCORD_TOKEN:
        logger.error("Missing DISCORD_TOKEN environment variable!")
        exit(1)
    
    if DISCORD_CHANNEL_ID == 0:
        logger.error("Missing DISCORD_CHANNEL_ID environment variable!")
        exit(1)
    
    # Import threading for Flask
    import threading
    
    # Start Flask in a separate thread for health checks
    port = int(os.getenv('PORT', 8080))
    flask_thread = threading.Thread(
        target=lambda: app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False),
        daemon=True
    )
    flask_thread.start()
    
    # Run the Discord bot
    try:
        run_bot()
    except KeyboardInterrupt:
        logger.info("Bot shutting down...")
    finally:
        # Cleanup
        asyncio.run(scraper.close())
