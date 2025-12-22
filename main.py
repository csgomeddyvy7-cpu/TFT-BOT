import discord
import os
import cloudscraper # Thư viện vượt tường lửa Cloudflare
from discord.ext import commands
from bs4 import BeautifulSoup
from urllib.parse import quote
from keep_alive import keep_alive 

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)

# --- HÀM CÀO DỮ LIỆU BẰNG CLOUDSCRAPER ---
def get_tft_stats(name, tag):
    # Tạo một trình duyệt giả lập mạnh mẽ
    scraper = cloudscraper.create_scraper(
        browser={
            'browser': 'chrome',
            'platform': 'windows',
            'desktop': True
        }
    )
    
    # URL Tactics.tools (Hỗ trợ tiếng Việt và Tag tốt nhất)
    # Cấu trúc: https://tactics.tools/player/vn/Tên/Tag
    encoded_name = quote(name)
    url = f"https://tactics.tools/player/vn/{encoded_name}/{tag}"
    
    try:
        # Dùng scraper để gửi yêu cầu (Thay vì requests)
        response = scraper.get(url)
        
        # Kiểm tra nếu bị lỗi 404 (Không tìm thấy tên)
        if response.status_code == 404:
            return None, "❌ Không tìm thấy người chơi (Kiểm tra lại Tên và Tag)."
            
        soup = BeautifulSoup(response.text, 'html.parser')

        # 1. Lấy mô tả (Rank, Winrate) từ thẻ Meta Description
        # Tactics.tools luôn để thông tin này ở đây
        meta_desc = soup.find('meta', attrs={'name': 'description'})
        
        # 2. Lấy link ảnh (Stat Card) từ thẻ og:image
        meta_image = soup.find('meta', property='og:image')
        
        if meta_desc:
            desc_content = meta_desc['content']
            
            # Kiểm tra xem có bị chuyển hướng về trang chủ không
            # Nếu nội dung là "TFT Stats..." chung chung nghĩa là bị lỗi
            if "visualizations and statistics" in desc_content or "set 13" in desc_content.lower():
                 return None, "⚠️ Web đang bảo trì hoặc chặn bot tạm thời."

            image_url = meta_image['content'] if meta_image else None
            
            # Sửa link ảnh nếu có dấu cách
            if image_url:
                image_url = image_url.replace(" ", "%20")

            return {
                "url": url,
                "desc": desc_content,
                "image": image_url
            }, None
            
        return None, "Không đọc được dữ liệu thẻ Meta."

    except Exception as e:
        return None, f"Lỗi Scraper: {str(e)}"

@bot.event
async def on_ready():
    print(f'Bot {bot.user} đã online (Mode: CloudScraper)')

@bot.command()
async def rank(ctx, *, full_name_tag):
    if '#' not in full_name_tag:
        await ctx.send("⚠️ Sai cú pháp! Ví dụ: `!rank Zyud#6969`")
        return

    parts = full_name_tag.split('#')
    tag = parts[-1].strip()
    name = "".join(parts[:-1]).strip()
    
    msg = await ctx.send(f"🔍 Đang phá tường lửa để soi **{name}#{tag}**...")
    
    data, error = get_tft_stats(name, tag)
    
    if data:
        embed = discord.Embed(
            title=f"Hồ sơ: {name}#{tag}",
            url=data['url'],
            description=f"📝 {data['desc']}", # Rank và chỉ số sẽ hiện ở đây
            color=0x9b59b6 # Màu tím
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
