import aiohttp
import asyncio
from datetime import datetime
import re

class RiotVerifier:
    """Xác thực Riot ID và lấy thông tin account TFT"""
    
    def __init__(self, api_key=None):
        self.api_key = api_key
        self.has_api_key = bool(api_key)
        self.session = None
        self.base_urls = {
            'asia': 'https://asia.api.riotgames.com',
            'americas': 'https://americas.api.riotgames.com',
            'europe': 'https://europe.api.riotgames.com'
        }
        
        if not self.has_api_key:
            print("⚠️ CẢNH BÁO: Không có RIOT_API_KEY, không thể xác thực Riot ID!")
    
    async def get_session(self):
        """Lấy aiohttp session"""
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession()
        return self.session
    
    async def close_session(self):
        """Đóng session"""
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
    
    async def verify_riot_id(self, riot_id, region='vn'):
        """
        Xác thực Riot ID bằng Riot API chính thức (chỉ TFT)
        Returns: {
            'success': bool,
            'data': dict (thông tin account),
            'error': str (nếu có),
            'api_source': str (nguồn dữ liệu)
        }
        """
        # Kiểm tra format
        if '#' not in riot_id:
            return {
                'success': False,
                'error': 'Sai format! Dùng: Username#Tagline',
                'api_source': 'Format check'
            }
        
        # Tách username và tagline
        try:
            username, tagline = riot_id.split('#', 1)
        except ValueError:
            return {
                'success': False,
                'error': 'Sai format! Dùng: Username#Tagline',
                'api_source': 'Format check'
            }
        
        # Loại bỏ khoảng trắng
        username = username.strip()
        tagline = tagline.strip()
        
        if not username or not tagline:
            return {
                'success': False,
                'error': 'Username và Tagline không được để trống',
                'api_source': 'Format check'
            }
        
        # Kiểm tra độ dài
        if len(username) < 3 or len(username) > 16:
            return {
                'success': False,
                'error': 'Username phải từ 3-16 ký tự',
                'api_source': 'Format check'
            }
        
        if len(tagline) < 2 or len(tagline) > 5:
            return {
                'success': False,
                'error': 'Tagline phải từ 2-5 ký tự',
                'api_source': 'Format check'
            }
        
        # Nếu không có API key
        if not self.has_api_key:
            return {
                'success': False,
                'error': 'Không có Riot API Key. Vui lòng cung cấp API key để xác thực.',
                'api_source': 'No API Key'
            }
        
        # Xác thực bằng Riot API chính thức
        return await self._verify_with_riot_api(username, tagline, region)
    
    async def _verify_with_riot_api(self, username, tagline, region):
        """Xác thực bằng Riot API chính thức (chỉ TFT)"""
        try:
            endpoint = self.get_region_endpoint(region)
            url = f"{endpoint}/riot/account/v1/accounts/by-riot-id/{username}/{tagline}"
            
            session = await self.get_session()
            headers = {
                "X-Riot-Token": self.api_key,
                "User-Agent": "TFT-Tracker-Bot/1.0"
            }
            
            print(f"[API CALL] Đang xác thực Riot ID: {username}#{tagline} tại {url}")
            
            async with session.get(url, headers=headers, timeout=10) as response:
                response_text = await response.text()
                print(f"[API RESPONSE] Status: {response.status}, Data: {response_text[:100]}...")
                
                if response.status == 200:
                    data = await response.json()
                    
                    return {
                        'success': True,
                        'data': {
                            'puuid': data['puuid'],
                            'game_name': data['gameName'],
                            'tagline': data['tagLine'],
                            'verified': True,
                            'source': 'riot_api',
                            'verified_at': datetime.now().isoformat(),
                            'api_source': f'Riot API Account (Region: {region.upper()})'
                        },
                        'api_source': f'Riot API Account (Region: {region.upper()})'
                    }
                elif response.status == 404:
                    return {
                        'success': False,
                        'error': 'Không tìm thấy tài khoản với Riot ID này',
                        'api_source': f'Riot API (HTTP 404)'
                    }
                elif response.status == 403:
                    return {
                        'success': False,
                        'error': 'Riot API key không hợp lệ hoặc đã hết hạn',
                        'api_source': f'Riot API (HTTP 403)'
                    }
                elif response.status == 429:
                    return {
                        'success': False,
                        'error': 'Rate limit của Riot API đã đạt giới hạn, vui lòng thử lại sau',
                        'api_source': f'Riot API (HTTP 429)'
                    }
                elif response.status == 500 or response.status == 503:
                    return {
                        'success': False,
                        'error': 'Riot API đang gặp sự cố, vui lòng thử lại sau',
                        'api_source': f'Riot API (HTTP {response.status})'
                    }
                else:
                    try:
                        error_data = await response.json()
                        error_msg = error_data.get('status', {}).get('message', f'Lỗi API: {response.status}')
                    except:
                        error_msg = f'Lỗi API: {response.status}'
                    
                    return {
                        'success': False,
                        'error': error_msg,
                        'api_source': f'Riot API (HTTP {response.status})'
                    }
                    
        except asyncio.TimeoutError:
            print(f"❌ Timeout khi xác thực Riot ID")
            return {
                'success': False,
                'error': 'Timeout khi kết nối đến Riot API (quá 10 giây)',
                'api_source': 'Timeout'
            }
        except aiohttp.ClientError as e:
            print(f"❌ Lỗi kết nối Riot API: {e}")
            return {
                'success': False,
                'error': f'Lỗi kết nối đến Riot API: {str(e)}',
                'api_source': 'Connection Error'
            }
        except Exception as e:
            print(f"❌ Lỗi không xác định khi xác thực: {e}")
            return {
                'success': False,
                'error': f'Lỗi không xác định: {str(e)}',
                'api_source': 'Unknown Error'
            }
    
    async def get_tft_rank(self, puuid, region):
        """Lấy rank TFT hiện tại (cần Riot API key)"""
        if not self.has_api_key:
            print(f"❌ Không có API Key để lấy rank TFT")
            return None
        
        try:
            # Lấy summoner ID từ PUUID
            summoner_url = f"https://{region}.api.riotgames.com/tft/summoner/v1/summoners/by-puuid/{puuid}"
            
            session = await self.get_session()
            headers = {"X-Riot-Token": self.api_key}
            
            print(f"[API CALL] Đang lấy summoner info từ PUUID: {puuid[:8]}...")
            
            async with session.get(summoner_url, headers=headers, timeout=10) as response:
                if response.status != 200:
                    print(f"❌ Lỗi khi lấy summoner: {response.status}")
                    return None
                
                summoner_data = await response.json()
                summoner_id = summoner_data.get('id')
                
                if not summoner_id:
                    print(f"❌ Không tìm thấy summoner ID")
                    return None
            
            # Lấy rank TFT
            rank_url = f"https://{region}.api.riotgames.com/tft/league/v1/entries/by-summoner/{summoner_id}"
            print(f"[API CALL] Đang lấy rank TFT: {rank_url}")
            
            async with session.get(rank_url, headers=headers, timeout=10) as response:
                if response.status == 200:
                    entries = await response.json()
                    print(f"[API RESPONSE] Rank entries: {entries}")
                    
                    for entry in entries:
                        if entry.get('queueType') == 'RANKED_TFT':
                            return {
                                'tier': entry.get('tier', 'UNRANKED'),
                                'rank': entry.get('rank', ''),
                                'lp': entry.get('leaguePoints', 0),
                                'wins': entry.get('wins', 0),
                                'losses': entry.get('losses', 0),
                                'api_source': f'Riot API TFT Rank (Region: {region.upper()})'
                            }
                    
                    print(f"⚠️ Không tìm thấy rank TFT")
                    return None
                else:
                    print(f"❌ Lỗi khi lấy rank: {response.status}")
                    return None
                    
        except Exception as e:
            print(f"❌ Lỗi get_tft_rank: {e}")
            return None
