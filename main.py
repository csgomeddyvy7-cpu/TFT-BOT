import discord
import os
from curl_cffi import requests as cffi_requests # Thư viện giả lập TLS (Vũ khí mới)
from discord.ext import commands
from bs4 import BeautifulSoup
from urllib.parse import quote
from keep_alive import keep_alive 

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)

# --- HÀM CÀO DỮ LIỆU SIÊU TỐC ---
def get_tft_stats(name, tag):
    # Tạo URL Tactics.tools
    encoded_name = quote(name)
    url = f"https://tactics.tools/player/vn/{encoded_name}/{tag}"
    
    try:
        # Dùng curl_cffi giả dạng Chrome 110
        # impersonate="chrome110" giúp vượt qua Cloudflare cực tốt
        response = cffi_requests.get(url, impersonate="chrome110", timeout=10)
        
        if response.status_code == 404:
            return None, "❌ Không tìm thấy tên người chơi."
            
        soup = BeautifulSoup(response.text, 'html.parser')

        # 1. Lấy mô tả (Rank, Winrate)
        meta_desc = soup.find('meta', attrs={'name': 'description'})
        
        # 2. Lấy link ảnh
        meta_image = soup.find('meta', property='og:image')
        
        if meta_desc:
            desc_content = meta_desc['content']
            
            # Kiểm tra xem có bị chuyển hướng về trang chủ không
            if "visualizations and statistics" in desc_content:
                 return None, "⚠️ Web đang chặn bot, vui lòng thử lại sau."

            image_url = meta_image['content'] if meta_image else None
            
            # Sửa link ảnh nếu có dấu cách
            if image_url:
                image_url = image_url.replace(" ", "%20")

            return {
                "url": url,
                "desc": desc_content,
                "image": image_url
            }, None
            
        return None, "Không đọc được dữ liệu."

    except Exception as e:
        return None, f"Lỗi: {str(e)}"

@bot.event
async def on_ready():
    print(f'Bot {bot.user} đã online (Mode: curl_cffi)')

@bot.command()
async def rank(ctx, *, full_name_tag):
    if '#' not in full_name_tag:
        await ctx.send("⚠️ Sai cú pháp! Ví dụ: `!rank Zyud#6969`")
        return

    parts = full_name_tag.split('#')
    tag = parts[-1].strip()
    name = "".join(parts[:-1]).strip()
    
    msg = await ctx.send(f"🔍 Đang soi **{name}#{tag}**...")
    
    data, error = get_tft_stats(name, tag)
    
    if data:
        embed = discord.Embed(
            title=f"Hồ sơ: {name}#{tag}",
            url=data['url'],
            description=f"📝 {data['desc']}",
            color=0xe67e22 # Màu cam
        )
        
        if data['image']:
            embed.set_image(url=data['image'])
        
        embed.set_footer(text="Dữ liệu từ Tactics.tools")
        await msg.edit(content="", embed=embed)
    else:
        await msg.edit(content=f"{error}")

keep_alive()
try:
    bot.run(os.environ.get('DISCORD_TOKEN'))
except Exception as e:
    print(f"Lỗi Token: {e}")
