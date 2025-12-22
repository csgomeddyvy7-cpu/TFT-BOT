import discord
import os
import requests
from discord.ext import commands
from bs4 import BeautifulSoup
from urllib.parse import quote # Thư viện để mã hóa tên có dấu cách
from keep_alive import keep_alive 

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)

# --- HÀM CÀO DỮ LIỆU MỚI (DAK.GG) ---
def scrape_tft_stats(name, tag):
    # Xử lý tên để đưa vào URL (Ví dụ: Trông Anh Ngược -> Trông%20Anh%20Ngược)
    encoded_name = quote(name)
    
    # Dak.gg dùng định dạng: tên-tag (dấu gạch ngang)
    # URL: https://dak.gg/tft/profile/vn/Trông%20Anh%20Ngược-CiS
    url = f"https://dak.gg/tft/profile/vn/{encoded_name}-{tag}"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
        "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7"
    }
    
    try:
        response = requests.get(url, headers=headers)
        
        if response.status_code == 404:
            return None, "Không tìm thấy người chơi này trên Dak.gg."
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # --- LẤY DỮ LIỆU TỪ THẺ META (Dak.gg làm cái này rất kỹ) ---
        # Thẻ này chứa: "Trông Anh Ngược #CiS - Emerald IV 45LP. Win Rate 15.2%..."
        meta_desc = soup.find('meta', property='og:description')
        
        if meta_desc:
            content = meta_desc['content']
            # Format lại chuỗi cho đẹp
            # Dữ liệu gốc thường là: "Name #Tag - Rank LP. Win Rate..."
            # Chúng ta sẽ tách ra để hiển thị từng dòng
            
            return url, content
        else:
            return url, "Không lấy được chi tiết (Web đổi cấu trúc)."

    except Exception as e:
        return None, f"Lỗi code: {str(e)}"

@bot.event
async def on_ready():
    print(f'Bot đã online: {bot.user}')

@bot.command()
async def rank(ctx, *, full_name_tag):
    if '#' not in full_name_tag:
        await ctx.send("⚠️ Sai cú pháp! Nhập: `!rank Tên#Tag` (VD: `!rank Trông Anh Ngược#CiS`)")
        return

    # Tách tên và tag
    parts = full_name_tag.split('#')
    tag = parts[-1].strip()
    name = "".join(parts[:-1]).strip()
    
    await ctx.send(f"🔍 Đang check {name}#{tag} trên Dak.gg...")
    
    url, result = scrape_tft_stats(name, tag)
    
    if url and result:
        # Tạo khung hiển thị đẹp (Embed)
        embed = discord.Embed(
            title=f"Kết quả: {name}#{tag}",
            url=url,
            description=result, # Nội dung Rank, LP nằm ở đây
            color=0x00ff00 # Màu xanh lá
        )
        embed.set_footer(text="Dữ liệu từ Dak.gg")
        await ctx.send(embed=embed)
    else:
        await ctx.send(f"❌ Lỗi: {result}")

keep_alive()
try:
    bot.run(os.environ.get('DISCORD_TOKEN'))
except Exception as e:
    print(f"Lỗi Token: {e}")
