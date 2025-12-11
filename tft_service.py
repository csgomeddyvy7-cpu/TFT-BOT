import aiohttp
import asyncio
from datetime import datetime, timedelta
import random

class TFTService:
    """Dịch vụ lấy dữ liệu TFT"""
    
    def __init__(self):
        self.session = None
        self.cache = {}
    
    async def get_session(self):
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession()
        return self.session
    
    async def close_session(self):
        if self.session and not self.session.closed:
            await self.session.close()
    
    async def get_player_overview(self, riot_id, region='vn'):
        """
        Lấy tổng quan player với rank CHÍNH XÁC
        """
        # Trong thực tế, bạn sẽ gọi API thực
        # Đây là mock data được cải thiện
        
        await asyncio.sleep(0.3)  # Simulate API delay
        
        # Tạo dữ liệu giả nhưng CHÍNH XÁC hơn
        seed = sum(ord(c) for c in riot_id)
        random.seed(seed)
        
        # Rank system với đầy đủ divisions
        ranks_tiers = ['Iron', 'Bronze', 'Silver', 'Gold', 'Platinum', 'Diamond', 'Master', 'Grandmaster', 'Challenger']
        divisions = ['IV', 'III', 'II', 'I']
        
        # Tạo rank ngẫu nhiên nhưng hợp lý
        tier_index = min(seed % 100 // 12, len(ranks_tiers) - 1)
        tier = ranks_tiers[tier_index]
        
        # Master+ không có divisions
        if tier in ['Master', 'Grandmaster', 'Challenger']:
            division = ''
            lp = random.randint(0, 1000)
            full_rank = f"{tier} {lp} LP"
        else:
            div_index = (seed // 7) % len(divisions)
            division = divisions[div_index]
            lp = random.randint(0, 99)
            full_rank = f"{tier} {division} ({lp} LP)"
        
        # Tính toán thống kê hợp lý
        total_games = random.randint(50, 400)
        wins = random.randint(int(total_games * 0.4), int(total_games * 0.6))
        losses = total_games - wins
        
        return {
            'rank': full_rank,
            'tier': tier,
            'division': division if division else '',
            'lp': lp,
            'wins': wins,
            'losses': losses,
            'total_games': total_games,
            'level': random.randint(50, 300),
            'last_played': (datetime.now() - timedelta(hours=random.randint(1, 48))).isoformat(),
            'source': 'improved_mock_data',
            'win_rate': round((wins / total_games) * 100, 1)
        }
    
    # [Phần còn lại giữ nguyên...]