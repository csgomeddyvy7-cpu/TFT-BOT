import discord
import os
from curl_cffi import requests as cffi_requests 
from discord.ext import commands
from bs4 import BeautifulSoup
from urllib.parse import quote
from keep_alive import keep_alive 

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)

# --- DANH BẠ NGƯỜI QUEN (Sửa tên ở đây) ---
# Lưu ý: Viết chữ thường hết cho phần tên biệt danh để bot dễ tìm
FRIEND_LIST = {
    "tanh": "Zyud#6969",
    "béo": "Bob#Dogak",
    "cường": "ức gà luộc#CiS",
    "dũng gà": "Đangỉalănrangủ#aba",
    "ngọc": "Manted#vn2",
    "bách ngu": "shiro#S144",
    "đức": "Trông Anh Ngược#CiS"
}

# --- HÀM CÀO DỮ LIỆU ---
def get_tft_stats(name, tag):
    encoded_name = quote(name)
    url = f"https://tactics.tools/player/vn/{encoded_name}/{tag}"
    
    try:
        # Giả lập Chrome 110 để vượt Cloudflare
        response = cffi_requests.get(url, impersonate="chrome110", timeout=10)
        
        if response.status_code == 404:
            return None, "❌ Không tìm thấy tên người chơi."
            
        soup = BeautifulSoup(response.text, 'html.parser')
        meta_desc = soup.find('meta', attrs={'name': 'description'})
        meta_image = soup.find('meta', property='og:image')
        
        if meta_desc:
            desc_content = meta_desc['content']
            if "visualizations and statistics" in desc_content:
                 return None, "⚠️ Web đang chặn bot, thử lại sau."

            image_url = meta_image['content'] if meta_image else None
            if image_url: image_url = image_url.replace(" ", "%20")

            return {"url": url, "desc": desc_content, "image": image_url}, None
            
        return None, "Không đọc được dữ liệu."

    except Exception as e:
        return None, f"Lỗi: {str(e)}"

@bot.event
async def on_ready():
    print(f'Bot {bot.user} đã online!')

# --- LỆNH XEM DANH SÁCH ---
@bot.command()
async def list(ctx):
    """Hiện danh sách biệt danh đã lưu"""
    desc = ""
    for nick, real_name in FRIEND_LIST.items():
        # Viết hoa chữ cái đầu cho đẹp
        desc += f"🔹 **{nick.title()}** ➡️ `{real_name}`\n"
    
    embed = discord.Embed(
        title="📜 Danh sách các con vợ",
        description=desc,
        color=0xf1c40f # Màu vàng
    )
    embed.set_footer(text="Gõ !rank [tên] để check nhanh")
    await ctx.send(embed=embed)

# --- LỆNH RANK THÔNG MINH ---
@bot.command()
async def rank(ctx, *, input_name):
    """
    Check rank theo biệt danh hoặc tên đầy đủ.
    VD: !rank Tanh  HOẶC  !rank Zyud#6969
    """
    # 1. Chuẩn hóa đầu vào (biến thành chữ thường để so sánh)
    key_lookup = input_name.lower().strip()

    # 2. Kiểm tra xem có trong danh bạ không
    if key_lookup in FRIEND_LIST:
        real_id = FRIEND_LIST[key_lookup]
        await ctx.send(f"🎯 Phát hiện **{input_name}** là **{real_id}**. Đang soi...")
    else:
        # Nếu không có trong danh bạ, kiểm tra xem có phải gõ tay Tên#Tag không
        if '#' in input_name:
            real_id = input_name
            await ctx.send(f"🔍 Đang soi **{real_id}**...")
        else:
            await ctx.send(f"❌ Không tìm thấy biệt danh **{input_name}** trong lệnh `!list`.\nVui lòng nhập đúng Tên#Tag (VD: `!rank Zyud#6969`)")
            return

    # 3. Tách Tên và Tag để xử lý
    try:
        parts = real_id.split('#')
        tag = parts[-1].strip()
        name = "".join(parts[:-1]).strip()
        
        # 4. Gọi hàm lấy dữ liệu
        data, error = get_tft_stats(name, tag)
        
        if data:
            embed = discord.Embed(
                title=f"Hồ sơ: {real_id}",
                url=data['url'],
                description=f"📝 {data['desc']}",
                color=0xe67e22
            )
            if data['image']: embed.set_image(url=data['image'])
            embed.set_footer(text="Tactics.tools")
            await ctx.send(embed=embed)
        else:
            await ctx.send(f"{error}")
            
    except Exception as e:
        await ctx.send(f"❌ Lỗi xử lý tên: {e}")

keep_alive()
try:
    bot.run(os.environ.get('DISCORD_TOKEN'))
except Exception as e:
    print(f"Lỗi Token: {e}")
