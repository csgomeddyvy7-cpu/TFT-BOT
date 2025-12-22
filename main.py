import discord
import os
import requests
from discord.ext import commands
from bs4 import BeautifulSoup
from keep_alive import keep_alive # Giữ bot sống trên Render

# Cấu hình Bot
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)

# Hàm cào dữ liệu từ Tactics.tools
def scrape_tft_stats(name, tag):
    # Tạo URL chuẩn
    url = f"https://tactics.tools/player/vn/{name}/{tag}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }
    
    try:
        response = requests.get(url, headers=headers)
        
        if response.status_code == 404:
            return None, "Không tìm thấy người chơi này. Kiểm tra lại tên và tag (VD: Zyud#6969)"
        
        if response.status_code != 200:
            return None, f"Lỗi kết nối đến web (Code {response.status_code})"

        soup = BeautifulSoup(response.text, 'html.parser')
        
        # --- MẸO HAY: LẤY DỮ LIỆU TỪ THẺ META ---
        # Tactics.tools tóm tắt mọi thứ trong thẻ meta description để hiển thị lên Google/Facebook
        # Chúng ta chỉ cần lấy cái đó là đủ thông tin, không cần đào sâu vào HTML
        
        # 1. Lấy Rank và Tên từ Tiêu đề trang (Title)
        # VD Title: "Zyud #6969 - Emerald IV 23 LP - TFT Stats"
        page_title = soup.title.text.strip()
        
        # 2. Lấy Tỷ lệ thắng/Top 4 từ thẻ Meta Description
        # Thẻ này thường chứa: "Zyud #6969 is a... Win Rate: 15.5%, Top 4 Rate: 55.2%..."
        meta_desc = soup.find('meta', attrs={'name': 'description'})
        description = meta_desc['content'] if meta_desc else "Không lấy được chi tiết."

        return page_title, description

    except Exception as e:
        return None, f"Lỗi code: {str(e)}"

@bot.event
async def on_ready():
    print(f'Bot đã đăng nhập với tên: {bot.user}')

@bot.command()
async def ping(ctx):
    await ctx.send('Pong! Bot vẫn đang sống nhăn răng.')

@bot.command()
async def rank(ctx, *, full_name_tag):
    """
    Cách dùng: !rank Tên Người Chơi#Tag
    Ví dụ: !rank Trông Anh Ngược#CiS
    """
    if '#' not in full_name_tag:
        await ctx.send("⚠️ Sai cú pháp! Vui lòng nhập kèm Tag. Ví dụ: `!rank Trông Anh Ngược#CiS`")
        return

    # Tách tên và tag
    try:
        # Xử lý chuỗi để lấy phần cuối làm tag
        parts = full_name_tag.split('#')
        tag = parts[-1].strip()
        name = "".join(parts[:-1]).strip() # Ghép lại tên nếu tên có dấu # (hiếm nhưng đề phòng)
        
        await ctx.send(f"🔍 Đang đi soi profile của **{name}#{tag}**...")
        
        title, desc = scrape_tft_stats(name, tag)
        
        if title:
            # Gửi kết quả đẹp mắt
            msg = f"**KẾT QUẢ SOI KÈO:**\n"
            msg += f"👤 **{title}**\n" # Dòng này chứa Rank và LP
            msg += f"📊 {desc}\n"      # Dòng này chứa Win Rate, Top 4
            msg += f"🔗 Link: <https://tactics.tools/player/vn/{name.replace(' ', '%20')}/{tag}>"
            await ctx.send(msg)
        else:
            await ctx.send(f"❌ {desc}") # Gửi lỗi
            
    except Exception as e:
        await ctx.send(f"❌ Có lỗi xảy ra: {e}")

# --- CHẠY BOT ---
keep_alive()
try:
    bot.run(os.environ.get('DISCORD_TOKEN'))
except Exception as e:
    print(f"Không lấy được Token: {e}")
