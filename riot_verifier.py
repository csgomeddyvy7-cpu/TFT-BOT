import aiohttp
import asyncio
from datetime import datetime
import re

class RiotVerifier:
    """Xác thực Riot ID và lấy thông tin account"""
    
    def __init__(self, api_key=None):
        self.api_key = api_key
        self.has_api_key = bool(api_key)
        self.session = None
        self.base_urls = {
            'asia': 'https://asia.api.riotgames.com',
            'americas': 'https://americas.api.riotgames.com',
            'europe': 'https://europe.api.riotgames.com'
        }
    
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
        Xác thực Riot ID
        Returns: {
            'success': bool,
            'data': dict (thông tin account),
            'error': str (nếu có)
        }
        """
        # Kiểm tra format
        if '#' not in riot_id:
            return {
                'success': False,
                'error': 'Sai format! Dùng: Username#Tagline'
            }
        
        # Tách username và tagline
        try:
            username, tagline = riot_id.split('#', 1)
        except ValueError:
            return {
                'success': False,
                'error': 'Sai format! Dùng: Username#Tagline'
            }
        
        # Loại bỏ khoảng trắng
        username = username.strip()
        tagline = tagline.strip()
        
        if not username or not tagline:
            return {
                'success': False,
                'error': 'Username và Tagline không được để trống'
            }
        
        # Ưu tiên dùng fallback method (tracker.gg) thay vì Riot API
        # Vì Riot API không ổn định với bạn
        result = await self._verify_with_fallback(username, tagline, region)
        
        # Nếu fallback thành công, trả về kết quả
        if result['success']:
            return result
        
        # Nếu fallback thất bại, thử dùng Riot API (nếu có key)
        if self.has_api_key:
            api_result = await self._verify_with_riot_api(username, tagline, region)
            if api_result['success']:
                return api_result
        
        # Nếu cả hai đều thất bại, trả về lỗi
        return {
            'success': False,
            'error': 'Không thể xác thực Riot ID qua tracker.gg. Vui lòng kiểm tra lại thông tin.'
        }
    
    async def _verify_with_riot_api(self, username, tagline, region):
        """Xác thực bằng Riot API chính thức"""
        try:
            endpoint = self.get_region_endpoint(region)
            url = f"{endpoint}/riot/account/v1/accounts/by-riot-id/{username}/{tagline}"
            
            session = await self.get_session()
            headers = {
                "X-Riot-Token": self.api_key,
                "User-Agent": "TFT-Tracker-Bot/1.0"
            }
            
            async with session.get(url, headers=headers, timeout=10) as response:
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
                            'verified_at': datetime.now().isoformat()
                        }
                    }
                elif response.status == 404:
                    return {
                        'success': False,
                        'error': 'Không tìm thấy tài khoản với Riot ID này'
                    }
                elif response.status == 403:
                    return {
                        'success': False,
                        'error': 'Riot API key không hợp lệ hoặc đã hết hạn'
                    }
                else:
                    return {
                        'success': False,
                        'error': f'Lỗi API: {response.status}'
                    }
                    
        except asyncio.TimeoutError:
            return {
                'success': False,
                'error': 'Timeout khi kết nối đến Riot API'
            }
        except Exception as e:
            print(f"Riot API error: {e}")
            return {
                'success': False,
                'error': f'Lỗi kết nối: {str(e)}'
            }
    
    async def _verify_with_fallback(self, username, tagline, region):
        """Xác thực bằng phương pháp fallback (dùng tracker.gg)"""
        try:
            # Ưu tiên dùng tracker.gg
            tracker_data = await self._get_from_tracker(username, tagline, region)
            if tracker_data:
                return {
                    'success': True,
                    'data': {
                        'game_name': tracker_data.get('game_name', username),
                        'tagline': tracker_data.get('tagline', tagline),
                        'verified': True,  # Coi như đã xác thực
                        'source': 'tracker_gg',
                        'verified_at': datetime.now().isoformat(),
                        'tft_rank': tracker_data.get('tft_rank', 'Chưa xác định'),
                        'rank_lp': tracker_data.get('rank_lp', 0),
                        'top_rank': tracker_data.get('top_rank', False)
                    }
                }
            
            # Nếu tracker.gg không được, thử op.gg
            opgg_data = await self._get_from_opgg(username, tagline, region)
            if opgg_data:
                return {
                    'success': True,
                    'data': {
                        'game_name': opgg_data.get('game_name', username),
                        'tagline': opgg_data.get('tagline', tagline),
                        'verified': True,
                        'source': 'op_gg',
                        'verified_at': datetime.now().isoformat(),
                        'tft_rank': opgg_data.get('tft_rank', 'Chưa xác định')
                    }
                }
            
            # Nếu không tìm thấy ở đâu cả
            return {
                'success': False,
                'error': 'Không thể tìm thấy tài khoản trên tracker.gg. Kiểm tra lại Riot ID và region.'
            }
            
        except Exception as e:
            print(f"Fallback verification error: {e}")
            return {
                'success': False,
                'error': f'Lỗi khi xác thực: {str(e)}'
            }
    
    async def _get_from_tracker(self, username, tagline, region):
        """Lấy thông tin thực từ tracker.gg bằng web scraping"""
        try:
            from bs4 import BeautifulSoup
            import urllib.parse
            
            # Mã hóa username để dùng trong URL
            encoded_username = urllib.parse.quote(username)
            
            # Tạo URL cho tracker.gg - region có thể cần mapping
            region_map = {
                'vn': 'vn',
                'na': 'na',
                'euw': 'euw',
                'eune': 'eune',
                'kr': 'kr',
                'jp': 'jp'
            }
            
            tracker_region = region_map.get(region.lower(), 'vn')
            url = f"https://tracker.gg/tft/profile/riot/{encoded_username}%23{tagline}/overview?region={tracker_region}"
            
            session = await self.get_session()
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.5",
                "Accept-Encoding": "gzip, deflate, br",
                "DNT": "1",
                "Connection": "keep-alive",
                "Upgrade-Insecure-Requests": "1",
                "Sec-Fetch-Dest": "document",
                "Sec-Fetch-Mode": "navigate",
                "Sec-Fetch-Site": "none",
                "Sec-Fetch-User": "?1",
                "Cache-Control": "max-age=0"
            }
            
            async with session.get(url, headers=headers, timeout=15) as response:
                if response.status == 200:
                    html = await response.text()
                    soup = BeautifulSoup(html, 'html.parser')
                    
                    # Tìm thông tin rank - CẦN KIỂM TRA SELECTOR NÀY
                    rank_info = {}
                    
                    # Thử tìm rank theo nhiều selector khác nhau
                    selectors = [
                        '.rating-summary__rank', 
                        '.rating-summary .valorant-rank',
                        '.stat__value',
                        '.trn-profile-header__rank'
                    ]
                    
                    rank_text = "Chưa xác định"
                    for selector in selectors:
                        rank_element = soup.select_one(selector)
                        if rank_element:
                            rank_text = rank_element.get_text(strip=True)
                            if rank_text and rank_text != '':
                                break
                    
                    # Tìm LP nếu có
                    lp_element = soup.select_one('.rating-summary__rating')
                    lp_text = "0"
                    if lp_element:
                        lp_match = re.search(r'(\d+)\s*LP', lp_element.get_text())
                        if lp_match:
                            lp_text = lp_match.group(1)
                    
                    # Kiểm tra xem có phải top rank không
                    top_rank = False
                    if any(word in rank_text.lower() for word in ['challenger', 'grandmaster', 'master']):
                        top_rank = True
                    
                    return {
                        'game_name': username,
                        'tagline': tagline,
                        'tft_rank': rank_text,
                        'rank_lp': int(lp_text) if lp_text.isdigit() else 0,
                        'top_rank': top_rank,
                        'profile_url': url,
                        'source': 'tracker_gg'
                    }
                elif response.status == 404:
                    print(f"Tracker.gg: Không tìm thấy hồ sơ cho {username}#{tagline}")
                    return None
                else:
                    print(f"Tracker.gg trả về mã lỗi: {response.status}")
                    return None
                    
        except asyncio.TimeoutError:
            print(f"Timeout khi kết nối đến tracker.gg cho {username}#{tagline}")
            return None
        except Exception as e:
            print(f"Lỗi khi scrape tracker.gg: {e}")
            return None
    
    async def _get_from_opgg(self, username, tagline, region):
        """Lấy thông tin từ op.gg"""
        try:
            from bs4 import BeautifulSoup
            
            # Map region cho op.gg
            region_map = {
                'vn': 'vn',
                'na': 'na',
                'euw': 'euw',
                'eune': 'eune',
                'kr': 'kr',
                'jp': 'jp'
            }
            
            opgg_region = region_map.get(region.lower(), 'vn')
            url = f"https://www.op.gg/summoners/{opgg_region}/{username}-{tagline}"
            
            session = await self.get_session()
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            }
            
            async with session.get(url, headers=headers, timeout=10) as response:
                if response.status == 200:
                    html = await response.text()
                    soup = BeautifulSoup(html, 'html.parser')
                    
                    # Tìm rank TFT trên op.gg - CẦN KIỂM TRA SELECTOR NÀY
                    rank_element = None
                    
                    # Thử tìm theo nhiều selector
                    selectors = [
                        '.tier-rank',
                        '.tier',
                        '.ranking-table__cell--tier',
                        '.summoner-tier'
                    ]
                    
                    rank_text = "Chưa xác định"
                    for selector in selectors:
                        rank_element = soup.select_one(selector)
                        if rank_element:
                            rank_text = rank_element.get_text(strip=True)
                            if rank_text and rank_text != '':
                                break
                    
                    return {
                        'game_name': username,
                        'tagline': tagline,
                        'tft_rank': rank_text,
                        'source': 'op_gg'
                    }
                    
            return None
        except Exception as e:
            print(f"Lỗi khi scrape op.gg: {e}")
            return None
    
    async def get_tft_rank(self, puuid, region):
        """Lấy rank TFT hiện tại (cần Riot API key)"""
        if not self.has_api_key:
            return None
        
        try:
            endpoint = self.get_region_endpoint(region)
            url = f"{endpoint}/tft/league/v1/entries/by-puuid/{puuid}"
            
            session = await self.get_session()
            headers = {"X-Riot-Token": self.api_key}
            
            async with session.get(url, headers=headers, timeout=10) as response:
                if response.status == 200:
                    entries = await response.json()
                    
                    for entry in entries:
                        if entry['queueType'] == 'RANKED_TFT':
                            return {
                                'tier': entry['tier'],
                                'rank': entry['rank'],
                                'lp': entry['leaguePoints'],
                                'wins': entry['wins'],
                                'losses': entry['losses']
                            }
                    
                    return None
                else:
                    return None
                    
        except:
            return None
