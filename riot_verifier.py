import aiohttp
import asyncio
from datetime import datetime
import re
from bs4 import BeautifulSoup  # Thêm thư viện để phân tích HTML

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
        
        # ƯU TIÊN SỬ DỤNG FALLBACK METHOD (TRACKER.GG)
        # Bỏ qua Riot API vì bạn không muốn dùng
        result = await self._verify_with_fallback(username, tagline, region)
        
        return result
    
    async def _verify_with_riot_api(self, username, tagline, region):
        """Xác thực bằng Riot API chính thức (GIỮ LẠI NHƯNG KHÔNG DÙNG)"""
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
        """Xác thực bằng phương pháp fallback (TRACKER.GG) - PHƯƠNG PHÁP CHÍNH"""
        try:
            # Thử lấy từ tracker.gg (PHƯƠNG PHÁP CHÍNH)
            tracker_data = await self._get_from_tracker(username, tagline, region)
            if tracker_data:
                return {
                    'success': True,
                    'data': {
                        'game_name': tracker_data.get('game_name', username),
                        'tagline': tracker_data.get('tagline', tagline),
                        'verified': False,  # Chưa xác thực hoàn toàn
                        'source': 'tracker_gg',
                        'verified_at': datetime.now().isoformat(),
                        'tft_rank': tracker_data.get('tft_rank', 'Rank đang tìm...'),
                        'profile_url': tracker_data.get('profile_url', '')
                    }
                }
            
            # Nếu không tìm thấy ở đâu cả
            return {
                'success': False,
                'error': 'Không thể tìm thấy tài khoản. Kiểm tra lại Riot ID và region.'
            }
            
        except Exception as e:
            print(f"Fallback verification error: {e}")
            return {
                'success': False,
                'error': f'Lỗi khi xác thực: {str(e)}'
            }
    
    async def _get_from_tracker(self, username, tagline, region):
        """Lấy thông tin từ tracker.gg bằng nhiều phương pháp tìm kiếm linh hoạt"""
        try:
            import urllib.parse
            
            encoded_username = urllib.parse.quote(username)
            url = f"https://tracker.gg/tft/profile/riot/{encoded_username}%23{tagline}/overview?region={region}"
            
            session = await self.get_session()
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            }
            
            async with session.get(url, headers=headers, timeout=15) as response:
                if response.status == 200:
                    html = await response.text()
                    
                    # DANH SÁCH CÁC PHƯƠNG PHÁP TÌM RANK (THEO THỨ TỰ ƯU TIÊN)
                    found_rank = None
                    lp_info = ""
                    
                    # Phương pháp 1: Tìm trong toàn bộ HTML bằng biểu thức chính quy
                    rank_pattern = r'\b(Iron|Bronze|Silver|Gold|Platinum|Diamond|Master|Grandmaster|Challenger)\s+(I{1,3}|IV)\b'
                    matches = re.findall(rank_pattern, html, re.IGNORECASE)
                    if matches:
                        # Lấy kết quả đầu tiên, chuyển đổi định dạng
                        tier, division = matches[0]
                        found_rank = f"{tier.capitalize()} {division}"
                    
                    # Phương pháp 2: Sử dụng BeautifulSoup để phân tích cấu trúc
                    if not found_rank:
                        soup = BeautifulSoup(html, 'html.parser')
                        
                        # Tìm trong thuộc tính alt của ảnh (thường chứa rank)
                        rank_images = soup.find_all('img', alt=True)
                        for img in rank_images:
                            alt_text = img['alt']
                            # Tìm rank trong alt text
                            rank_match = self._extract_rank_from_text(alt_text)
                            if rank_match:
                                found_rank = rank_match
                                break
                    
                    # Phương pháp 3: Tìm các thẻ có chứa từ khóa rank
                    if not found_rank:
                        rank_keywords = ['Iron', 'Bronze', 'Silver', 'Gold', 'Platinum', 
                                        'Diamond', 'Master', 'Grandmaster', 'Challenger']
                        
                        soup = BeautifulSoup(html, 'html.parser')
                        all_text = soup.get_text()
                        
                        for keyword in rank_keywords:
                            # Tìm từ khóa kết hợp với số La Mã gần đó
                            pattern = rf'{keyword}\s+(I{{1,3}}|IV)'
                            match = re.search(pattern, all_text, re.IGNORECASE)
                            if match:
                                found_rank = match.group(0)
                                break
                    
                    # Tìm thông tin LP (League Points)
                    lp_pattern = r'(\d+)\s*<span[^>]*>\s*LP\s*</span>'
                    lp_matches = re.findall(lp_pattern, html)
                    if not lp_matches:
                        # Thử pattern khác cho LP
                        lp_pattern2 = r'(\d+)\s*LP'
                        lp_matches = re.findall(lp_pattern2, html)
                    
                    if lp_matches:
                        lp_info = f" ({lp_matches[0]} LP)"
                    
                    # Chuẩn bị kết quả
                    if found_rank:
                        return {
                            'game_name': username,
                            'tagline': tagline,
                            'tft_rank': f"{found_rank}{lp_info}",
                            'source': 'tracker_gg',
                            'profile_url': url
                        }
                    else:
                        # Vẫn trả về thông tin cơ bản ngay cả khi không tìm thấy rank
                        return {
                            'game_name': username,
                            'tagline': tagline,
                            'tft_rank': 'Rank đang tìm...',
                            'source': 'tracker_gg',
                            'profile_url': url
                        }
                        
                elif response.status == 404:
                    print(f"Không tìm thấy trang cho {username}#{tagline}")
                    return None
                else:
                    print(f"Lỗi HTTP {response.status} khi truy cập tracker.gg")
                    return None
                    
        except asyncio.TimeoutError:
            print(f"Timeout khi truy cập tracker.gg cho {username}#{tagline}")
            return None
        except Exception as e:
            print(f"Lỗi khi scrape tracker.gg: {e}")
            return None
    
    def _extract_rank_from_text(self, text):
        """Trích xuất thông tin rank từ chuỗi văn bản"""
        # Pattern cho rank TFT (ví dụ: Platinum III, Gold IV, etc.)
        rank_pattern = r'\b(Iron|Bronze|Silver|Gold|Platinum|Diamond|Master|Grandmaster|Challenger)\s+(I{1,3}|IV)\b'
        match = re.search(rank_pattern, text, re.IGNORECASE)
        
        if match:
            tier, division = match.groups()
            return f"{tier.capitalize()} {division}"
        
        # Pattern cho rank không có division (Master+)
        high_rank_pattern = r'\b(Master|Grandmaster|Challenger)\b'
        match = re.search(high_rank_pattern, text, re.IGNORECASE)
        if match:
            return match.group(0).capitalize()
        
        return None
    
    async def _get_from_opgg(self, username, tagline, region):
        """Lấy thông tin từ op.gg (GIỮ LẠI NHƯNG CÓ THỂ KHÔNG DÙNG)"""
        try:
            # URL cho TFT trên OP.GG
            url = f"https://www.op.gg/summoners/{region}/{username}-{tagline}"
            
            session = await self.get_session()
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            }
            
            async with session.get(url, headers=headers, timeout=10) as response:
                if response.status == 200:
                    # Parse HTML để lấy rank
                    # Đây là mock data - có thể cải thiện sau
                    return {
                        'game_name': username,
                        'tagline': tagline,
                        'tft_rank': 'Silver I',  # Mock
                        'source': 'op_gg'
                    }
                    
            return None
        except:
            return None
    
    async def get_tft_rank(self, puuid, region):
        """Lấy rank TFT hiện tại (cần Riot API key) - KHÔNG DÙNG"""
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
