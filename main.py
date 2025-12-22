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

def scrape_tactics_tools(name, tag):
    # 1. Tạo URL Profile
    encoded_name = quote(name)
    profile_url = f"https://tactics.tools/player/vn/{encoded_name}/{tag}"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }
    
    try:
        response = requests.get(profile_url, headers=headers)
        
        if response.status_code == 404:
            return None, None, None, "❌ Không tìm thấy tên người chơi này."
            
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # 2. Lấy thông tin CHỮ (Rank, LP) từ thẻ Description
        # Để phòng trường hợp ảnh không hiện thì vẫn có chữ để đọc
        meta_desc = soup.find('meta', attrs={'name': 'description'})
        description_text = meta_desc['content'] if meta_desc else "Không lấy được thông tin chi tiết."
        
        # 3. Lấy thông tin ẢNH (Stat Card)
        meta_image = soup.find('meta', property='og:image')
        image_url = None
        
        if meta_image:
            raw_image_url = meta_image['content']
            # QUAN TRỌNG: Sửa lỗi link ảnh chứa dấu cách khiến Discord không hiển thị
            image_url = raw_image_url.replace(" ", "%20")
            print(f"Link ảnh tìm được: {image_url}") # In ra console để kiểm tra
        
        return profile_url, description_text, image_url, "OK"

    except Exception as e:
        return None, None, None, f"Lỗi code: {str(e)}"

@bot.event
async def on_ready():
    print(f'Bot đã online: {bot.user}')

@bot.command()
async def rank(ctx, *, full_name_tag):
    if '#' not in full_name_tag:
        await ctx.send("⚠️ Sai cú pháp! Ví dụ: `!rank Zyud#6969`")
        return

    parts = full_name_tag.split('#')
    tag = parts[-1].strip()
    name = "".join(parts[:-1]).strip()
    
    msg = await ctx.send(f"🔍 Đang soi **{name}#{tag}**...")
    
    profile_url, desc_text, image_url, status = scrape_tactics_tools(name, tag)
    
    if status == "OK":
        embed = discord.Embed(
            title=f"Hồ sơ: {name}#{tag}",
            url=profile_url,
            description=f"📊 **Thông tin nhanh:**\n{desc_text}", # Hiển thị chữ ở đây
            color=0x2ecc71
        )
        
        # Nếu có ảnh thì gắn vào, không thì thôi
        if image_url:
            embed.set_image(url=image_url)
        else:
            embed.set_footer(text="Không tìm thấy ảnh thống kê, nhưng link trên vẫn hoạt động.")
            
        await msg.edit(content="", embed=embed)
    else:
        await msg.edit(content=status)

keep_alive()
try:
    bot.run(os.environ.get('DISCORD_TOKEN'))
except Exception as e:
    print(f"Lỗi Token: {e}")
