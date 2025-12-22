import discord
import os
import requests
from discord.ext import commands
from bs4 import BeautifulSoup
from urllib.parse import quote 
from keep_alive import keep_alive 

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)

# --- HÀM LẤY ẢNH THỐNG KÊ TỪ TACTICS.TOOLS ---
def get_stat_card(name, tag):
    # 1. Xử lý tên tiếng Việt (Mã hóa URL)
    # Ví dụ: "Trông Anh Ngược" -> "Trông%20Anh%20Ngược"
    encoded_name = quote(name)
    
    # URL của Tactics.tools (Trang này hỗ trợ tiếng Việt tốt nhất)
    url = f"https://tactics.tools/player/vn/{encoded_name}/{tag}"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }
    
    try:
        response = requests.get(url, headers=headers)
        
        # Nếu không tìm thấy người chơi
        if response.status_code == 404:
            return None, None, "❌ Không tìm thấy tên này. Bạn kiểm tra lại dấu cách hoặc Tag xem."

        soup = BeautifulSoup(response.text, 'html.parser')
        
        # 2. MẸO: Lấy link ảnh từ thẻ Meta "og:image"
        # Đây là tấm ảnh chứa toàn bộ thông tin Rank/Winrate mà web tự tạo ra
        meta_image = soup.find('meta', property='og:image')
        
        if meta_image:
            image_url = meta_image['content']
            # Tactics.tools đôi khi dùng ảnh mặc định nếu chưa cập nhật kịp
            # Nhưng 90% sẽ là ảnh chỉ số chuẩn
            return url, image_url, "OK"
        else:
            return url, None, "⚠️ Web không trả về ảnh thống kê (Có thể do mạng)."

    except Exception as e:
        return None, None, f"Lỗi Bot: {str(e)}"

@bot.event
async def on_ready():
    print(f'Bot đã online: {bot.user}')

@bot.command()
async def rank(ctx, *, full_name_tag):
    # Xử lý input người dùng
    if '#' not in full_name_tag:
        await ctx.send("⚠️ Sai cú pháp! Nhập: `!rank Tên#Tag` (VD: `!rank Trông Anh Ngược#CiS`)")
        return

    parts = full_name_tag.split('#')
    tag = parts[-1].strip()
    name = "".join(parts[:-1]).strip()
    
    msg = await ctx.send(f"🔍 Đang vào Tactics.tools chụp ảnh rank của **{name}#{tag}**...")
    
    # Gọi hàm xử lý
    profile_url, image_url, status = get_stat_card(name, tag)
    
    if status == "OK":
        # Tạo Embed chứa ảnh
        embed = discord.Embed(
            title=f"Hồ sơ đấu thủ: {name}#{tag}",
            url=profile_url,
            color=0x2ecc71 # Màu xanh ngọc
        )
        # Gắn ảnh stat card vào (Đây là phần quan trọng nhất)
        embed.set_image(url=image_url)
        embed.set_footer(text="Dữ liệu hình ảnh từ Tactics.tools")
        
        await msg.edit(content="", embed=embed)
    else:
        await msg.edit(content=status)

keep_alive()
try:
    bot.run(os.environ.get('DISCORD_TOKEN'))
except Exception as e:
    print(f"Lỗi Token: {e}")
