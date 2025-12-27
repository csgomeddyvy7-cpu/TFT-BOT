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

# --- DANH BẠ (Viết thường hết ở phần tên biệt danh nhé) ---
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

@bot.command()
async def list(ctx):
    """Hiện danh sách biệt danh"""
    desc = ""
    for nick, real_name in FRIEND_LIST.items():
        desc += f"🔹 **{nick.title()}** ➡️ `{real_name}`\n"
    
    embed = discord.Embed(
        title="📜 Danh sách các con vợ",
        description=desc,
        color=0xf1c40f 
    )
    embed.set_footer(text="Gõ !rank [tên] để check")
    await ctx.send(embed=embed)

@bot.command()
async def rank(ctx, *, input_name):
    """Check rank theo biệt danh hoặc tên đầy đủ."""
    
    # 1. Chuẩn hóa tên nhập vào (biến thành chữ thường)
    key_lookup = input_name.lower().strip()
    real_id = None

    # 2. LOGIC ĐÃ SỬA: Ưu tiên tìm trong danh bạ trước!
    if key_lookup in FRIEND_LIST:
        real_id = FRIEND_LIST[key_lookup]
        await ctx.send(f"🎯 Phát hiện **{input_name.title()}** là **{real_id}**. Đang soi...")
    
    # 3. Nếu không có trong danh bạ, mới kiểm tra xem có phải nhập tay (có dấu #) không
    elif '#' in input_name:
        real_id = input_name
        await ctx.send(f"🔍 Đang soi **{real_id}**...")
    
    # 4. Nếu cả 2 đều sai -> Báo lỗi và DỪNG LẠI (return)
    else:
        await ctx.send(f"❌ Không tìm thấy biệt danh **{input_name}** và cũng không đúng cú pháp Tên#Tag.")
        return 

    # --- Phần xử lý lấy dữ liệu (Chỉ chạy khi đã có real_id) ---
    try:
        parts = real_id.split('#')
        tag = parts[-1].strip()
        name = "".join(parts[:-1]).strip()
        
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
