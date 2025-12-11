import aiohttp
import asyncio
from datetime import datetime, timedelta
import random
import json

class TFTService:
    """Dịch vụ lấy dữ liệu TFT"""
    
    def __init__(self, api_key=None):
        self.api_key = api_key
        self.has_api_key = bool(api_key)
        self.session = None
        self.cache = {}
        self.base_urls = {
            'asia': 'https://asia.api.riotgames.com',
            'americas': 'https://americas.api.riotgames.com',
            'europe': 'https://europe.api.riotgames.com'
        }
    
    async def get_session(self):
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession()
        return self.session
    
    async def close_session(self):
        if self.session and not self.session.closed:
            await self.session.close()
    
    def get_region_endpoint(self, region):
        """Lấy endpoint theo region"""
        region_map = {
            'vn': 'asia',
            'kr': 'asia',
            'jp': 'asia',
            'na': 'americas',
            'br': 'americas',
            'lan': 'americas',
            'las': 'americas',
            'oce': 'americas',
            'euw': 'europe',
            'eune': 'europe',
            'tr': 'europe',
            'ru': 'europe'
        }
        return self.base_urls.get(region_map.get(region.lower(), 'asia'))
    
    async def get_puuid(self, riot_id, region='vn'):
        """Lấy PUUID từ Riot ID"""
        if not self.has_api_key:
            return None
            
        try:
            username, tagline = riot_id.split('#', 1)
            endpoint = self.get_region_endpoint(region)
            url = f"{endpoint}/riot/account/v1/accounts/by-riot-id/{username}/{tagline}"
            
            session = await self.get_session()
            headers = {"X-Riot-Token": self.api_key}
            
            async with session.get(url, headers=headers, timeout=10) as response:
                if response.status == 200:
                    data = await response.json()
                    return data['puuid']
                return None
        except:
            return None
    
    async def get_player_overview(self, riot_id, region='vn'):
        """
        Lấy tổng quan player từ Riot API
        """
        if not self.has_api_key:
            # Fallback: mock data cải tiến
            return await self._get_mock_overview(riot_id)
        
        try:
            puuid = await self.get_puuid(riot_id, region)
            if not puuid:
                return await self._get_mock_overview(riot_id)
            
            # Lấy summoner ID
            summoner_url = f"https://{region}.api.riotgames.com/tft/summoner/v1/summoners/by-puuid/{puuid}"
            session = await self.get_session()
            headers = {"X-Riot-Token": self.api_key}
            
            async with session.get(summoner_url, headers=headers, timeout=10) as response:
                if response.status != 200:
                    return await self._get_mock_overview(riot_id)
                summoner_data = await response.json()
            
            # Lấy rank
            rank_url = f"https://{region}.api.riotgames.com/tft/league/v1/entries/by-summoner/{summoner_data['id']}"
            async with session.get(rank_url, headers=headers, timeout=10) as response:
                if response.status == 200:
                    entries = await response.json()
                    for entry in entries:
                        if entry['queueType'] == 'RANKED_TFT':
                            tier = entry['tier']
                            rank = entry['rank']
                            lp = entry['leaguePoints']
                            wins = entry['wins']
                            losses = entry['losses']
                            
                            return {
                                'rank': f"{tier} {rank}",
                                'lp': lp,
                                'wins': wins,
                                'losses': losses,
                                'total_games': wins + losses,
                                'level': summoner_data.get('summonerLevel', 0),
                                'last_played': datetime.now().isoformat(),
                                'source': 'riot_api',
                                'tier': tier,
                                'rank_num': rank,
                                'full_rank': f"{tier} {rank} {lp} LP"
                            }
            
            # Nếu không có rank
            return {
                'rank': 'Unranked',
                'lp': 0,
                'wins': 0,
                'losses': 0,
                'total_games': 0,
                'level': summoner_data.get('summonerLevel', 0),
                'last_played': datetime.now().isoformat(),
                'source': 'riot_api',
                'tier': 'Unranked',
                'full_rank': 'Unranked'
            }
                
        except Exception as e:
            print(f"❌ Lỗi Riot API: {e}")
            return await self._get_mock_overview(riot_id)
    
    async def _get_mock_overview(self, riot_id):
        """Mock data cải tiến với rank ổn định"""
        await asyncio.sleep(0.5)
        
        # Tạo rank ổn định dựa trên riot_id
        seed = sum(ord(c) for c in riot_id.replace('#', ''))
        random.seed(seed)
        
        tiers = ['Iron', 'Bronze', 'Silver', 'Gold', 'Platinum', 'Diamond', 'Master', 'Grandmaster', 'Challenger']
        divisions = ['IV', 'III', 'II', 'I']
        
        # Tạo rank ổn định, không bị tụt
        tier_idx = min(seed % len(tiers), len(tiers) - 1)
        div_idx = min((seed // 10) % len(divisions), len(divisions) - 1)
        
        tier = tiers[tier_idx]
        division = divisions[div_idx]
        lp = random.randint(0, 99)
        
        # Tính toán win/loss
        base_games = random.randint(50, 200)
        win_rate = 0.4 + (tier_idx * 0.05) + random.random() * 0.2
        win_rate = min(max(win_rate, 0.3), 0.7)
        
        wins = int(base_games * win_rate)
        losses = base_games - wins
        
        return {
            'rank': f"{tier} {division}",
            'lp': lp,
            'wins': wins,
            'losses': losses,
            'total_games': base_games,
            'level': random.randint(30, 500),
            'last_played': (datetime.now() - timedelta(hours=random.randint(1, 72))).isoformat(),
            'source': 'mock_data',
            'tier': tier,
            'rank_num': division,
            'full_rank': f"{tier} {division} {lp} LP"
        }
    
    async def get_match_history(self, riot_id, region='vn', limit=5):
        """
        Lấy lịch sử match từ Riot API
        """
        if not self.has_api_key:
            return await self._get_mock_matches(riot_id, limit)
        
        try:
            puuid = await self.get_puuid(riot_id, region)
            if not puuid:
                return await self._get_mock_matches(riot_id, limit)
            
            # Lấy match IDs
            endpoint = self.get_region_endpoint(region)
            matches_url = f"{endpoint}/tft/match/v1/matches/by-puuid/{puuid}/ids?count={limit}"
            
            session = await self.get_session()
            headers = {"X-Riot-Token": self.api_key}
            
            async with session.get(matches_url, headers=headers, timeout=10) as response:
                if response.status != 200:
                    return await self._get_mock_matches(riot_id, limit)
                match_ids = await response.json()
            
            # Lấy chi tiết từng match
            matches = []
            for match_id in match_ids:
                try:
                    match_url = f"{endpoint}/tft/match/v1/matches/{match_id}"
                    async with session.get(match_url, headers=headers, timeout=5) as match_resp:
                        if match_resp.status == 200:
                            match_data = await match_resp.json()
                            
                            # Tìm participant của player
                            for participant in match_data['info']['participants']:
                                if participant['puuid'] == puuid:
                                    match_info = {
                                        'match_id': match_id,
                                        'placement': participant['placement'],
                                        'level': participant['level'],
                                        'traits': participant.get('traits', []),
                                        'units': participant.get('units', []),
                                        'timestamp': datetime.fromtimestamp(match_data['info']['game_datetime']/1000).isoformat(),
                                        'game_duration': match_data['info']['game_length'],
                                        'players_remaining': 8,
                                        'source': 'riot_api'
                                    }
                                    matches.append(match_info)
                                    break
                except Exception as e:
                    print(f"❌ Lỗi lấy match {match_id}: {e}")
                    continue
            
            return matches if matches else await self._get_mock_matches(riot_id, limit)
                
        except Exception as e:
            print(f"❌ Lỗi lấy match history: {e}")
            return await self._get_mock_matches(riot_id, limit)
    
    async def _get_mock_matches(self, riot_id, limit):
        """Mock data cho matches"""
        await asyncio.sleep(0.3)
        
        matches = []
        seed = sum(ord(c) for c in riot_id.replace('#', ''))
        random.seed(seed)
        
        for i in range(limit):
            placement = random.randint(1, 8)
            level = random.randint(7, 10)
            
            # Tạo traits ngẫu nhiên
            all_traits = ['Darkin', 'Challenger', 'Juggernaut', 'Shurima', 
                         'Ionia', 'Noxus', 'Sorcerer', 'Multicaster',
                         'Demacia', 'Freljord', 'Piltover', 'Zaun',
                         'Void', 'Yordle', 'Strategist', 'Gunner']
            
            num_traits = random.randint(3, 6)
            selected_traits = random.sample(all_traits, num_traits)
            
            traits = []
            for trait in selected_traits:
                traits.append({
                    'name': trait,
                    'tier': random.randint(1, 3),
                    'num_units': random.randint(2, 8)
                })
            
            # Tạo units ngẫu nhiên
            all_units = ['Aatrox', 'Kaisa', 'Warwick', 'JarvanIV', 'Nasus',
                        'Azir', 'Katarina', 'Darius', 'Swain', 'Jayce',
                        'Heimerdinger', 'Zeri', 'Jinx', 'Vi', 'Ekko']
            
            num_units = random.randint(8, 12)
            selected_units = random.sample(all_units, min(num_units, len(all_units)))
            
            units = []
            for unit in selected_units:
                units.append({
                    'character_id': unit,
                    'tier': random.randint(1, 3),
                    'items': random.sample(['BF Sword', 'Recurve Bow', 'Chain Vest'], 
                                          random.randint(0, 3))
                })
            
            matches.append({
                'match_id': f"{riot_id.replace('#', '_')}_{int(datetime.now().timestamp()) - i}",
                'placement': placement,
                'level': level,
                'traits': traits,
                'units': units,
                'timestamp': (datetime.now() - timedelta(hours=i*3)).isoformat(),
                'game_duration': random.randint(1200, 1800),
                'players_remaining': 8 if i == 0 else random.randint(1, 8),
                'source': 'mock_data'
            })
        
        return matches
    
    async def get_match_details(self, match_id, region='vn'):
        """Lấy chi tiết match"""
        if not self.has_api_key:
            return await self._get_mock_match_details(match_id)
        
        try:
            endpoint = self.get_region_endpoint(region)
            url = f"{endpoint}/tft/match/v1/matches/{match_id}"
            
            session = await self.get_session()
            headers = {"X-Riot-Token": self.api_key}
            
            async with session.get(url, headers=headers, timeout=10) as response:
                if response.status == 200:
                    return await response.json()
                return None
        except:
            return None
    
    async def _get_mock_match_details(self, match_id):
        """Mock chi tiết match"""
        await asyncio.sleep(0.2)
        
        return {
            'match_id': match_id,
            'info': {
                'game_datetime': datetime.now().timestamp() * 1000,
                'game_length': random.randint(1200, 1800),
                'queue_id': 1100,
                'tft_set_number': 9,
                'game_version': '13.19.123.4567'
            },
            'participants': []
        }
    
    async def get_live_rank(self, riot_id, region='vn'):
        """Lấy rank hiện tại"""
        overview = await self.get_player_overview(riot_id, region)
        return overview.get('full_rank', 'Unknown')