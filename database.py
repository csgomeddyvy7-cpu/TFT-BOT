import sqlite3
from riot_api import RiotAPI

def init_database():
    """Khởi tạo database với cấu trúc đầy đủ"""
    conn = sqlite3.connect('tft_bot.db')
    c = conn.cursor()
    
    # Bảng người chơi theo dõi
    c.execute('''CREATE TABLE IF NOT EXISTS tracked_players
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  game_name TEXT,
                  tag_line TEXT,
                  puuid TEXT UNIQUE,
                  summoner_id TEXT,
                  last_match_id TEXT,
                  last_check TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    
    # Bảng lịch sử thông báo (tránh thông báo trùng)
    c.execute('''CREATE TABLE IF NOT EXISTS notified_matches
                 (match_id TEXT PRIMARY KEY,
                  player_puuid TEXT,
                  notified_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    
    conn.commit()
    conn.close()

async def update_player_puuid(game_name, tag_line):
    """Cập nhật PUUID cho người chơi"""
    riot_api = RiotAPI()
    puuid = await riot_api.get_puuid(game_name, tag_line)
    
    if puuid:
        conn = sqlite3.connect('tft_bot.db')
        c = conn.cursor()
        c.execute('''UPDATE tracked_players 
                     SET puuid = ?
                     WHERE game_name = ? AND tag_line = ?''',
                  (puuid, game_name, tag_line))
        conn.commit()
        conn.close()
        return puuid
    return None