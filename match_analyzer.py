def analyze_match(match_data, target_puuid):
    """Phân tích trận đấu và trích xuất thông tin cho người chơi cụ thể"""
    try:
        # Tìm thông tin người chơi trong trận
        participants = match_data.get('info', {}).get('participants', [])
        for player in participants:
            if player.get('puuid') == target_puuid:
                # Trích xuất thông tin quan trọng
                result = {
                    'placement': player.get('placement', 0),  # Thứ hạng (1-8)
                    'level': player.get('level', 0),          # Cấp độ
                    'total_damage': player.get('total_damage_to_players', 0),
                    'traits': [t['name'] for t in player.get('traits', []) if t['tier_current'] > 0],
                    'units': [u['character_id'] for u in player.get('units', [])],
                    'game_datetime': match_data['info']['game_datetime']
                }
                return result
        return None
    except Exception as e:
        print(f"Lỗi phân tích match: {e}")
        return None

def format_rank_message(rank_info):
    """Định dạng thông báo rank đẹp mắt"""
    if not rank_info:
        return "Chưa có rank trong mùa này"
    
    tier = rank_info.get('tier', 'UNRANKED')
    rank = rank_info.get('rank', '')
    lp = rank_info.get('leaguePoints', 0)
    wins = rank_info.get('wins', 0)
    losses = rank_info.get('losses', 0)
    
    win_rate = (wins / (wins + losses) * 100) if (wins + losses) > 0 else 0
    
    return f"""
🏆 **Rank TFT**: {tier} {rank}
📊 **Điểm LP**: {lp} LP
📈 **Tỉ lệ thắng**: {wins} thắng / {losses} thua ({win_rate:.1f}%)
🔥 **Hot Streak**: {'✅' if rank_info.get('hotStreak', False) else '❌'}
"""