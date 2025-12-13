import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    # Discord
    DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
    CHANNEL_ID = int(os.getenv('DISCORD_CHANNEL_ID'))
    
    # Riot API
    RIOT_API_KEY = os.getenv('RIOT_API_KEY')
    REGION = os.getenv('REGION', 'sea')
    
    # Bot Settings
    CHECK_INTERVAL = int(os.getenv('CHECK_INTERVAL', 60))
    
    # Parse tracked players
    tracked_players_str = os.getenv('TRACKED_PLAYERS', '')
    TRACKED_PLAYERS = [p.strip() for p in tracked_players_str.split(',')] if tracked_players_str else []