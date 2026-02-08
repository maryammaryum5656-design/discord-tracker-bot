import discord
from discord import app_commands
import json
from datetime import datetime
import matplotlib.pyplot as plt
import os
import tempfile

# ===================== الإعدادات =====================
TOKEN = os.getenv("DISCORD_TOKEN")

GUILD_ID = 1321896972117868605                # سيرفرك
DATABASE_CHANNEL_ID = 1469730960215117910     # قناة الداتا بيز
REPORTS_CHANNEL_ID  = 1469801496617943064     # قناة التقارير
# ====================================================

intents = discord.Intents.default()
intents.message_content = True

class TrackerBot(discord.Client):
    def __init__(self):
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self):
        # مسح الأوامر القديمة وتسجيل الجديدة في السيرفر المحدد
        guild = discord.Object(id=GUILD_ID)
        self.tree.clear_commands(guild=guild)
        self.tree.copy_global_to(guild=guild)
        await self.tree.sync(guild=guild)
        print(f"✅ تم تحديث الأوامر بنجاح في السيرفر: {GUILD_ID}")

bot = TrackerBot()

# ===================== وظائف مساعدة =====================

def parse_duration(d: str) -> int:
    """ تحويل صيغة الوقت 00h 00m 00s إلى ثواني """
    try:
        parts = d.lower().replace("h", "").replace("m", "").replace("s", "").split()
        if len(parts) == 3:
            h, m, s = map(int, parts)
            return h * 3600 + m * 60 + s
        return 0
    except:
        return 0

def format_seconds(seconds: int) -> str:
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    return f"{h:02d}h {m:02d}m {s:02d}s"

def create_line_chart(times, labels):
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".png")
    path = tmp.name
    tmp.close()

    plt.figure(figsize=(10, 5))
    plt.plot(labels, times, marker="o", color="#1ABC9C")
    plt.xticks(rotation=45, ha="right")
    plt.ylabel("Seconds Played")
    plt.title("Play Time Over Sessions")
    plt.grid(True, linestyle="--", alpha=0.5)
    plt.tight_layout()
    plt.savefig(path)
    plt.close()
    return path

async def get_all_known_players():
    """ جلب قائمة بكل اللاعبين المسجلين في الشات لعمل البحث التلقائي """
    players = set()
    channel = bot.get_channel(DATABASE_CHANNEL_ID)
    if not channel: return []

    async for msg in channel.history(limit=1000):
        if "```json" in msg.content:
            try:
                json_text = msg.content.split("```json")[1].split("```")[0]
                data = json.loads(json_text)
                if "username" in data:
                    players.add(data["username"])
            except:
                continue
    return sorted(list(players))

# ===================== نظام البحث (Autocomplete) =====================

async def player_autocomplete(interaction: discord.Interaction, current: str):
    players = await get_all_known_players()
    return [
        app_commands.Choice(name=player, value=player)
        for player in players if current.lower() in player.lower()
    ][:25] # ديسكورد يدعم 25 اختيار كحد أقصى

# ===================== الأوامر =====================

@bot.tree.command(name="leaderboard", description="عرض قائمة المتصدرين حسب وقت اللعب")
async def leaderboard(interaction: discord.Interaction):
    await interaction.response.defer(thinking=True)
    
    db_channel = bot.get_channel(DATABASE_CHANNEL_ID)
    playtime = {}

    async for msg in db_channel.history(limit=2000):
        if "```json" in msg.content:
            try:
                json_text = msg.content.split("```json")[1].split("```")[0]
                data = json.loads(json_text)
                user = data.get("username")
                dur = parse_duration(data.get("duration", "00h 00m 00s"))
                playtime[user] = playtime.get(user, 0) + dur
            except: continue

    if not playtime:
        await interaction.followup.send("❌ لا توجد بيانات مسجلة حالياً.")
        return

    sorted_players = sorted(playtime.items(), key=lambda x: x[1], reverse=True)[:10]
    desc = "\n".join([f"**{i+1}. {p[0]}** — `{format_seconds(p[1])}`" for i, p in enumerate(sorted_players)])

    embed = discord.Embed(title="🏆 قائمة المتصدرين (Top Playtime)", description=desc, color=0xF1C40F)
    await interaction.followup.send(embed=embed)

@bot.tree.command(name="lastseen", description="آخر ظهور للاعب في السيرفر")
@app_commands.autocomplete(player=player_autocomplete)
async def lastseen(interaction: discord.Interaction, player: str):
    await interaction.response.defer(thinking=True)
    
    db_channel = bot.get_channel(DATABASE_CHANNEL_ID)
    last_record = None

    async for msg in db_channel.history(limit=2000):
        if "```json" in msg.content:
            try:
                json_text = msg.content.split("```json")[1].split("```")[0]
                data = json.loads(json_text)
                if data.get("username") == player:
                    last_record = data
                    break # أول نتيجة نجدها هي الأحدث في الهيستوري
            except: continue

    if not last_record:
        await interaction.followup.send(f"❌ لم يتم العثور على سجلات للاعب **{player}**")
        return

    embed = discord.Embed(title=f"👀 آخر ظهور — {player}", color=0x3498DB)
    embed.add_field(name="📍 المكان", value=f"`{last_record.get('place', 'Unknown')}`", inline=False)
    embed.add_field(name="🟢 دخول", value=f"`{last_record.get('joinedAt', '-')}`", inline=True)
    embed.add_field(name="🔴 خروج", value=f"`{last_record.get('leftAt', '-')}`", inline=True)
    await interaction.followup.send(embed=embed)

@bot.tree.command(name="report", description="تقرير كامل عن نشاط اللاعب مع الرسم البياني")
@app_commands.autocomplete(player=player_autocomplete)
async def report(interaction: discord.Interaction, player: str):
    await interaction.response.defer(thinking=True)
    
    db_channel = bot.get_channel(DATABASE_CHANNEL_ID)
    records = []

    async for msg in db_channel.history(limit=2000):
        if "```json" in msg.content:
            try:
                json_text = msg.content.split("```json")[1].split("```")[0]
                data = json.loads(json_text)
                if data.get("username") == player:
                    records.append(data)
            except: continue

    if not records:
        await interaction.followup.send(f"❌ لا توجد بيانات كافية لعمل تقرير عن **{player}**")
        return

    records.reverse() # ترتيب من الأقدم للأحدث للرسم البياني
    total_sec = sum(parse_duration(r.get("duration", "0")) for r in records)
    
    durations = [parse_duration(r.get("duration", "0")) for r in records]
    labels = [r.get("joinedAt", "")[:10] for r in records] # تاريخ اليوم فقط للتوضيح

    chart_path = create_line_chart(durations, labels)
    
    embed = discord.Embed(title=f"📊 تقرير النشاط — {player}", color=0x1ABC9C)
    embed.add_field(name="⏱️ إجمالي وقت اللعب", value=f"`{format_seconds(total_sec)}`", inline=False)
    embed.add_field(name="🎮 عدد الجلسات", value=f"`{len(records)}` جلسة", inline=True)

    report_channel = bot.get_channel(REPORTS_CHANNEL_ID)
    if report_channel:
        await report_channel.send(embed=embed)
        await report_channel.send(file=discord.File(chart_path))
        await interaction.followup.send(f"✅ تم إرسال التقرير بنجاح في <#{REPORTS_CHANNEL_ID}>")
    else:
        await interaction.followup.send("❌ قناة التقارير غير صحيحة، تأكد من الـ ID.")
    
    if os.path.exists(chart_path):
        os.remove(chart_path)

bot.run(TOKEN)