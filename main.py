import discord
import os
import requests
from discord.ext import commands
from bs4 import BeautifulSoup
from urllib.parse import quote
from fake_useragent import UserAgent # Tạo danh tính giả ngẫu nhiên
from keep_alive import keep_alive 

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)

# --- HÀM CÀO DỮ LIỆU TỪ LEAGUEOFGRAPHS ---
def get_rank_info(name, tag):
    # Tạo danh tính giả để không bị chặn
    ua = UserAgent()
    headers = {
        "User-Agent": ua.random,
        "Accept-Language": "en-US,en;q=0.9"
    }

    # Xử lý URL: LeagueOfGraphs dùng định dạng Tên-Tag (dấu cách thay bằng +)
    # Ví dụ: Trông Anh Ngược -> Trong+Anh+Nguoc (web này tự xử lý dấu tiếng việt khá tốt)
    # Nhưng an toàn nhất là để nguyên dấu và encode
    
    encoded_name = quote(name).replace("%20", "+") # Thay khoảng trắng bằng dấu +
    url = f"https://www.leagueofgraphs.com/tft/summoner/vn/{encoded_name}-{tag}"

    try:
        response = requests.get(url, headers=headers)
        
        if response.status_code == 404:
            return None, "❌ Không tìm thấy người chơi. Hãy thử viết không dấu hoặc kiểm tra lại Tag."
            
        soup = BeautifulSoup(response.text, 'html.parser')

        # --- BẮT ĐẦU ĐỌC DỮ LIỆU HTML ---
        
        # 1. Tìm thẻ chứa Rank (Thường nằm trong div class="league-tier-name")
        rank_tier = soup.find(class_="league-tier-name")
        rank_lp = soup.find(class_="league-points")
        
        # 2. Tìm thẻ chứa Winrate (Thường nằm trong chart)
        # Web này cấu trúc hơi phức tạp, mẹo nhanh nhất là lấy từ Meta Description
        # Vì LeagueOfGraphs viết thông tin rất đầy đủ vào thẻ Meta
        
        meta_desc = soup.find('meta', attrs={'name': 'description'})
        if meta_desc:
            content = meta_desc['content']
            # Nội dung gốc: "Trông Anh Ngược (TFT) - Emerald IV, 23 LP / 15W 20L Win Ratio 42%..."
            # Chúng ta sẽ làm sạch chuỗi này
            clean_info = content.split(" / ")[0] # Lấy phần Rank
            extra_info = content.split(" / ")[1] if " / " in content else "" # Lấy phần Winrate
            
            return {
                "url": url,
                "rank": clean_info,
                "stats": extra_info,
                "full": content
            }
        
        # Nếu không lấy được meta, thử lấy thủ công (dự phòng)
        if rank_tier and rank_lp:
             return {
                "url": url,
                "rank": f"{rank_tier.text.strip()} - {rank_lp.text.strip()}",
                "stats": "Không lấy được tỷ lệ thắng",
                "full": "..."
            }

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

    # Tách tên và tag
    parts = full_name_tag.split('#')
    tag = parts[-1].strip()
    name = "".join(parts[:-1]).strip()
    
    await ctx.send(f"🔍 Đang truy cập LeagueOfGraphs để soi **{name}#{tag}**...")
    
    data, error = get_rank_info(name, tag)
    
    if data:
        # TẠO BẢNG THÔNG TIN (EMBED)
        embed = discord.Embed(
            title=f"Hồ sơ TFT: {name}#{tag}",
            url=data['url'],
            description="Dưới đây là thông tin chi tiết:",
            color=0x3498db # Màu xanh dương
        )
        
        # Thêm các dòng thông tin
        # Rank: Emerald IV, 23 LP
        embed.add_field(name="🏆 Rank Hiện Tại", value=f"**{data.get('rank', 'N/A')}**", inline=False)
        
        # Chỉ số: 15W 20L...
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
