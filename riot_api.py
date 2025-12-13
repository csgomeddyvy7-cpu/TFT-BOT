import aiohttp
import asyncio
from config import Config

class RiotAPI:
    def __init__(self):
        self.api_key = Config.RIOT_API_KEY
        self.region = Config.REGION
        self.headers = {"X-Riot-Token": self.api_key}

    async def get_puuid(self, game_name, tag_line):
        """Lấy PUUID từ Riot ID (Tên#Tag)"""
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
        """Lấy thông tin summoner từ PUUID"""
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
                    # Tìm queue type RANKED_TFT
                    for entry in data:
                        if entry.get('queueType') == 'RANKED_TFT':
                            return entry
                    return None
                return None

    async get_match_history(self, puuid, count=20):
        """Lấy lịch sử trận đấu gần nhất"""
        url = f"https://{self.region}.api.riotgames.com/tft/match/v1/matches/by-puuid/{puuid}/ids?count={count}"
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=self.headers) as response:
                if response.status == 200:
                    return await response.json()
                return []

    async def get_match_details(self, match_id):
        """Lấy chi tiết một trận đấu cụ thể"""
        url = f"https://{self.region}.api.riotgames.com/tft/match/v1/matches/{match_id}"
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=self.headers) as response:
                if response.status == 200:
                    return await response.json()
                return None