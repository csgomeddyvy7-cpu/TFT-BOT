import discord
import os
import requests
from discord.ext import commands
from bs4 import BeautifulSoup
from urllib.parse import quote
from fake_useragent import UserAgent 
from keep_alive import keep_alive 

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)

# --- HÀM CÀO DỮ LIỆU TỪ LEAGUEOFGRAPHS (ĐÃ SỬA LỖI RETURN) ---
def get_rank_info(name, tag):
    ua = UserAgent()
    headers = {
        "User-Agent": ua.random,
        "Accept-Language": "en-US,en;q=0.9"
    }

    encoded_name = quote(name).replace("%20", "+") 
    url = f"https://www.leagueofgraphs.com/tft/summoner/vn/{encoded_name}-{tag}"

    try:
        response = requests.get(url, headers=headers)
        
        if response.status_code == 404:
            return None, "❌ Không tìm thấy người chơi. Hãy thử viết không dấu hoặc kiểm tra lại Tag."
            
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Lấy Meta Description
        meta_desc = soup.find('meta', attrs={'name': 'description'})
        if meta_desc:
            content = meta_desc['content']
            
            # Xử lý chuỗi an toàn hơn
            if " / " in content:
                clean_info = content.split(" / ")[0]
                extra_info = content.split(" / ")[1]
            else:
                clean_info = content
                extra_info = "Không có thông tin thêm"
            
            # QUAN TRỌNG: Trả về 2 giá trị (Dictionary, None)
            return {
                "url": url,
                "rank": clean_info,
                "stats": extra_info,
                "full": content
            }, None 
        
        # Backup: Tìm thủ công
        rank_tier = soup.find(class_="league-tier-name")
        rank_lp = soup.find(class_="league-points")
        
        if rank_tier and rank_lp:
             # QUAN TRỌNG: Trả về 2 giá trị (Dictionary, None)
             return {
                "url": url,
                "rank": f"{rank_tier.text.strip()} - {rank_lp.text.strip()}",
                "stats": "Không lấy được tỷ lệ thắng",
                "full": "..."
            }, None

        return None, "Web đổi cấu trúc, không đọc được dữ liệu."

    except Exception as e:
        return None, f"Lỗi Bot: {str(e)}"

@bot.event
async def on_ready():
    print(f'Bot {bot.user} đã sẵn sàng soi rank!')

@bot.command()
async def rank(ctx, *, full_name_tag):
    if '#' not in full_name_tag:
        await ctx.send("⚠️ Sai cú pháp! Ví dụ: `!rank Zyud#6969`")
        return

    parts = full_name_tag.split('#')
    tag = parts[-1].strip()
    name = "".join(parts[:-1]).strip()
    
    await ctx.send(f"🔍 Đang truy cập LeagueOfGraphs để soi **{name}#{tag}**...")
    
    # Ở đây nhận về 2 giá trị nên sẽ không bị lỗi nữa
    data, error = get_rank_info(name, tag)
    
    if data:
        embed = discord.Embed(
            title=f"Hồ sơ TFT: {name}#{tag}",
            url=data['url'],
            description="Dưới đây là thông tin chi tiết:",
            color=0x3498db 
        )
        
        embed.add_field(name="🏆 Rank Hiện Tại", value=f"**{data.get('rank', 'N/A')}**", inline=False)
        
        if data.get('stats'):
             embed.add_field(name="📊 Chỉ Số", value=data['stats'], inline=False)
        
        embed.set_footer(text="Nguồn: LeagueOfGraphs (Cập nhật realtime)")
        
        await ctx.send(embed=embed)
    else:
        await ctx.send(f"{error}")

keep_alive()
try:
    bot.run(os.environ.get('DISCORD_TOKEN'))
except Exception as e:
    print(f"Lỗi Token: {e}")
