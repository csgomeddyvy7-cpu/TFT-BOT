import aiohttp
import asyncio
from datetime import datetime, timedelta
import json

class TFTService:
    """Dịch vụ lấy dữ liệu TFT từ Riot API chính thức"""
    
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
        
        if not self.has_api_key:
            print("⚠️ CẢNH BÁO: Không có RIOT_API_KEY, không thể lấy dữ liệu TFT!")
    
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
            print(f"❌ Không có API Key để lấy PUUID của {riot_id}")
            return None
            
        try:
            username, tagline = riot_id.split('#', 1)
            endpoint = self.get_region_endpoint(region)
            url = f"{endpoint}/riot/account/v1/accounts/by-riot-id/{username}/{tagline}"
            
            session = await self.get_session()
            headers = {"X-Riot-Token": self.api_key}
            
            print(f"[API CALL] Đang lấy PUUID: {url}")
            
            async with session.get(url, headers=headers, timeout=10) as response:
                data = await response.json()
                print(f"[API RESPONSE] PUUID response: {response.status}")
                
                if response.status == 200:
                    puuid = data.get('puuid')
                    print(f"✅ Đã lấy PUUID của {riot_id}: {puuid[:8]}...")
                    return puuid
                else:
                    print(f"❌ Lỗi API khi lấy PUUID: {response.status} - {data}")
                    return None
        except aiohttp.ClientError as e:
            print(f"❌ Lỗi kết nối khi lấy PUUID: {e}")
            return None
        except Exception as e:
            print(f"❌ Lỗi không xác định khi lấy PUUID: {e}")
            return None
    
    async def get_player_overview(self, riot_id, region='vn'):
        """
        Lấy tổng quan player TFT từ Riot API
        Returns: dict với thông tin hoặc None nếu lỗi
        """
        if not self.has_api_key:
            print(f"❌ Không thể lấy thông tin {riot_id}: Không có RIOT_API_KEY")
            return {
                'error': 'Không có RIOT_API_KEY',
                'message': 'Vui lòng cung cấp Riot API Key để lấy thông tin TFT'
            }
        
        try:
            # Bước 1: Lấy PUUID
            puuid = await self.get_puuid(riot_id, region)
            if not puuid:
                return {
                    'error': 'Không tìm thấy tài khoản',
                    'message': f'Không thể lấy PUUID của {riot_id}. Kiểm tra Riot ID và region.'
                }
            
            # Bước 2: Lấy Summoner ID từ PUUID (TFT)
            summoner_url = f"https://{region}.api.riotgames.com/tft/summoner/v1/summoners/by-puuid/{puuid}"
            session = await self.get_session()
            headers = {"X-Riot-Token": self.api_key}
            
            print(f"[API CALL] Đang lấy Summoner info: {summoner_url}")
            
            async with session.get(summoner_url, headers=headers, timeout=10) as response:
                if response.status != 200:
                    error_data = await response.text()
                    print(f"❌ Lỗi khi lấy Summoner info: {response.status} - {error_data}")
                    return {
                        'error': f'API Error {response.status}',
                        'message': 'Không thể lấy thông tin summoner từ Riot API'
                    }
                
                summoner_data = await response.json()
                print(f"✅ Đã lấy summoner info: Level {summoner_data.get('summonerLevel', 'N/A')}")
            
            # Bước 3: Lấy rank TFT
            rank_url = f"https://{region}.api.riotgames.com/tft/league/v1/entries/by-summoner/{summoner_data['id']}"
            print(f"[API CALL] Đang lấy rank TFT: {rank_url}")
            
            async with session.get(rank_url, headers=headers, timeout=10) as response:
                if response.status != 200:
                    error_data = await response.text()
                    print(f"❌ Lỗi khi lấy rank TFT: {response.status} - {error_data}")
                    # Trả về thông tin summoner nhưng không có rank
                    return {
                        'summonerLevel': summoner_data.get('summonerLevel', 0),
                        'profileIconId': summoner_data.get('profileIconId', 0),
                        'name': summoner_data.get('name', ''),
                        'puuid': puuid,
                        'rank': 'Unranked',
                        'tier': 'UNRANKED',
                        'lp': 0,
                        'wins': 0,
                        'losses': 0,
                        'total_games': 0,
                        'last_played': datetime.now().isoformat(),
                        'source': 'riot_api_tft',
                        'full_rank': 'Unranked',
                        'error': f'Không có rank TFT (HTTP {response.status})'
                    }
                
                entries = await response.json()
                print(f"[API RESPONSE] Rank entries: {entries}")
                
                # Tìm entry cho RANKED_TFT
                for entry in entries:
                    if entry.get('queueType') == 'RANKED_TFT':
                        tier = entry.get('tier', 'UNRANKED')
                        rank = entry.get('rank', '')
                        lp = entry.get('leaguePoints', 0)
                        wins = entry.get('wins', 0)
                        losses = entry.get('losses', 0)
                        
                        # Chuyển đổi tier sang tiếng Việt (tùy chọn)
                        tier_vn = {
                            'IRON': 'Sắt', 'BRONZE': 'Đồng', 'SILVER': 'Bạc',
                            'GOLD': 'Vàng', 'PLATINUM': 'Bạch Kim', 'DIAMOND': 'Kim Cương',
                            'MASTER': 'Cao Thủ', 'GRANDMASTER': 'Đại Cao Thủ', 'CHALLENGER': 'Thách Đấu'
                        }.get(tier, tier)
                        
                        rank_display = f"{tier_vn} {rank}" if rank else tier_vn
                        full_rank = f"{tier_vn} {rank} {lp} LP" if rank else f"{tier_vn} {lp} LP"
                        
                        result = {
                            'summonerLevel': summoner_data.get('summonerLevel', 0),
                            'profileIconId': summoner_data.get('profileIconId', 0),
                            'name': summoner_data.get('name', ''),
                            'puuid': puuid,
                            'rank': rank_display,
                            'tier': tier,
                            'rank_num': rank,
                            'lp': lp,
                            'wins': wins,
                            'losses': losses,
                            'total_games': wins + losses,
                            'last_played': datetime.fromtimestamp(entry.get('lastPlayed', 0)/1000).isoformat() if entry.get('lastPlayed') else datetime.now().isoformat(),
                            'source': 'riot_api_tft',
                            'full_rank': full_rank,
                            'api_source': f'Riot API TFT (Region: {region.upper()})'
                        }
                        
                        print(f"✅ Đã lấy rank TFT: {full_rank}")
                        return result
            
            # Nếu không tìm thấy entry RANKED_TFT
            print(f"⚠️ {riot_id} không có rank TFT (Unranked)")
            return {
                'summonerLevel': summoner_data.get('summonerLevel', 0),
                'profileIconId': summoner_data.get('profileIconId', 0),
                'name': summoner_data.get('name', ''),
                'puuid': puuid,
                'rank': 'Unranked',
                'tier': 'UNRANKED',
                'lp': 0,
                'wins': 0,
                'losses': 0,
                'total_games': 0,
                'last_played': datetime.now().isoformat(),
                'source': 'riot_api_tft',
                'full_rank': 'Unranked',
                'api_source': f'Riot API TFT (Region: {region.upper()})',
                'note': 'Không có rank TFT'
            }
                
        except aiohttp.ClientError as e:
            print(f"❌ Lỗi kết nối Riot API: {e}")
            return {
                'error': 'Connection Error',
                'message': f'Không thể kết nối đến Riot API: {str(e)}'
            }
        except asyncio.TimeoutError:
            print(f"❌ Timeout khi gọi Riot API")
            return {
                'error': 'Timeout',
                'message': 'Riot API không phản hồi (timeout)'
            }
        except Exception as e:
            print(f"❌ Lỗi không xác định trong get_player_overview: {e}")
            return {
                'error': 'Unknown Error',
                'message': f'Lỗi không xác định: {str(e)}'
            }
    
    async def get_match_history(self, riot_id, region='vn', limit=5):
        """
        Lấy lịch sử match TFT từ Riot API
        """
        if not self.has_api_key:
            print(f"❌ Không thể lấy match history: Không có RIOT_API_KEY")
            return []
        
        try:
            puuid = await self.get_puuid(riot_id, region)
            if not puuid:
                print(f"❌ Không tìm thấy PUUID của {riot_id}")
                return []
            
            # Lấy match IDs
            endpoint = self.get_region_endpoint(region)
            matches_url = f"{endpoint}/tft/match/v1/matches/by-puuid/{puuid}/ids?count={limit}"
            
            session = await self.get_session()
            headers = {"X-Riot-Token": self.api_key}
            
            print(f"[API CALL] Đang lấy match history: {matches_url}")
            
            async with session.get(matches_url, headers=headers, timeout=10) as response:
                if response.status != 200:
                    error_data = await response.text()
                    print(f"❌ Lỗi khi lấy match IDs: {response.status} - {error_data}")
                    return []
                
                match_ids = await response.json()
                print(f"✅ Đã lấy được {len(match_ids)} match IDs")
            
            # Lấy chi tiết từng match
            matches = []
            for match_id in match_ids:
                try:
                    match_url = f"{endpoint}/tft/match/v1/matches/{match_id}"
                    print(f"[API CALL] Đang lấy match {match_id}")
                    
                    async with session.get(match_url, headers=headers, timeout=5) as match_resp:
                        if match_resp.status != 200:
                            print(f"❌ Lỗi match {match_id}: {match_resp.status}")
                            continue
                        
                        match_data = await match_resp.json()
                        
                        # Tìm participant của player
                        for participant in match_data['info']['participants']:
                            if participant['puuid'] == puuid:
                                # Format traits
                                traits = []
                                for trait in participant.get('traits', []):
                                    if trait.get('tier_current', 0) > 0:
                                        traits.append({
                                            'name': trait.get('name', '').replace('Set9_', '').replace('_', ' '),
                                            'tier': trait.get('tier_current', 0),
                                            'num_units': trait.get('num_units', 0)
                                        })
                                
                                # Format units
                                units = []
                                for unit in participant.get('units', []):
                                    units.append({
                                        'character_id': unit.get('character_id', '').replace('TFT9_', ''),
                                        'tier': unit.get('tier', 0),
                                        'items': unit.get('itemNames', [])
                                    })
                                
                                match_info = {
                                    'match_id': match_id,
                                    'placement': participant['placement'],
                                    'level': participant['level'],
                                    'traits': traits,
                                    'units': units,
                                    'timestamp': datetime.fromtimestamp(match_data['info']['game_datetime']/1000).isoformat(),
                                    'game_duration': match_data['info']['game_length'],
                                    'players_remaining': len(match_data['info']['participants']),
                                    'queue_id': match_data['info']['queue_id'],
                                    'tft_set': match_data['info']['tft_set_number'],
                                    'game_version': match_data['info']['game_version'],
                                    'source': 'riot_api_tft',
                                    'api_source': f'Riot API TFT Match (Region: {region.upper()})'
                                }
                                matches.append(match_info)
                                print(f"✅ Đã xử lý match {match_id}, placement: {participant['placement']}")
                                break
                            
                except Exception as e:
                    print(f"❌ Lỗi xử lý match {match_id}: {e}")
                    continue
            
            return matches
                
        except Exception as e:
            print(f"❌ Lỗi lấy match history: {e}")
            return []
    
    async def get_match_details(self, match_id, region='vn'):
        """Lấy chi tiết match TFT"""
        if not self.has_api_key:
            print(f"❌ Không thể lấy match details: Không có RIOT_API_KEY")
            return None
        
        try:
            endpoint = self.get_region_endpoint(region)
            url = f"{endpoint}/tft/match/v1/matches/{match_id}"
            
            session = await self.get_session()
            headers = {"X-Riot-Token": self.api_key}
            
            print(f"[API CALL] Đang lấy match details: {url}")
            
            async with session.get(url, headers=headers, timeout=10) as response:
                if response.status == 200:
                    data = await response.json()
                    print(f"✅ Đã lấy match details {match_id}")
                    return data
                else:
                    print(f"❌ Lỗi match details {match_id}: {response.status}")
                    return None
        except Exception as e:
            print(f"❌ Lỗi get_match_details: {e}")
            return None
    
    async def get_live_rank(self, riot_id, region='vn'):
        """Lấy rank TFT hiện tại"""
        overview = await self.get_player_overview(riot_id, region)
        if overview and 'error' not in overview:
            return overview.get('full_rank', 'Unknown')
        else:
            error_msg = overview.get('message', 'Lỗi không xác định') if overview else 'Không có dữ liệu'
            return f"Error: {error_msg}"
