import discord
from discord.ext import commands
import base64
import os
import json
import requests
import time
import random
from dotenv import load_dotenv

# ==========================
# Konfigurasi & Konstanta
# ==========================
# Ganti sesuai kebutuhanmu
QUIZ_POINTS_CORRECT = 10  # Poin yang didapat user saat menjawab kuis dengan benar
IMAGE_WIDTH = 1024
IMAGE_HEIGHT = 1024

# Load token dari .env
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True  # diperlukan untuk memberi role

bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)

# Simpan prompt terakhir tiap user (hanya di memori)
user_last_prompt = {}

# ==========================
# Utilitas File Data
# ==========================
USER_DATA_FILE = "user_data.json"
ACH_FILE = "achievements.json"
SHOP_FILE = "shop_items.json"


def _init_file(path: str, default_obj):
    if not os.path.exists(path):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(default_obj, f, indent=4, ensure_ascii=False)


# Data awal user kosong
_init_file(USER_DATA_FILE, {})

# Achievement default (akan dibuat hanya bila file belum ada)
_init_file(ACH_FILE, {
    "first_win": {
        "nama": "Jawaban Pertama!",
        "deskripsi": "Jawab satu soal kuis.",
        "syarat": {"jawaban_benar": 1}
    },
    "quiz_streak": {
        "nama": "Jawaban Hebat!",
        "deskripsi": "Jawab 10 soal kuis.",
        "syarat": {"jawaban_benar": 10}
    },
    "buy_once": {
        "nama": "Gimmie your money!!",
        "deskripsi": "Melakukan pembelian pertama.",
        "syarat": {"pembelian": 1}
    },
    "quiz_25": {
        "nama": "Push Your Limits!",
        "deskripsi": "Jawab 25 soal kuis.",
        "syarat": {"jawaban_benar": 25}
    },
    "quiz_50": {
        "nama": "Have You Lost Your Mind?",
        "deskripsi": "Jawab 50 soal kuis.",
        "syarat": {"jawaban_benar": 50}
    },
    "quiz_100": {
        "nama": "Touch Some Grass, Man",
        "deskripsi": "Jawab 100 soal kuis.",
        "syarat": {"jawaban_benar": 100}
    },
    "rich": {
        "nama": "Rich Man",
        "deskripsi": "Memiliki 100 poin atau lebih.",
        "syarat": {"poin": 100}
    }
})

# Shop default (boleh kamu ubah / tambah via file atau nanti bikin command admin)
_init_file(SHOP_FILE, {
    "vip": {"nama": "Role VIP", "harga": 100, "role": "VIP"},
    "champion": {"nama": "Role Champion", "harga": 150, "role": "Champion"},
    "badge": {"nama": "Badge Quiz Master", "harga": 50}
})


# ==========================
# Helper Load/Save Data User
# ==========================
def load_user_data():
    with open(USER_DATA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_user_data(data):
    with open(USER_DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)


def get_user_record(user_id: int):
    uid = str(user_id)
    data = load_user_data()
    if uid not in data:
        data[uid] = {
            "poin": 0,
            "jawaban_benar": 0,
            "pembelian": 0,
            "achievements": []
        }
        save_user_data(data)
    return data[uid]


def update_user_record(user_id: int, **kwargs):
    uid = str(user_id)
    data = load_user_data()
    rec = data.get(uid, {
        "poin": 0,
        "jawaban_benar": 0,
        "pembelian": 0,
        "achievements": []
    })
    rec.update(kwargs)
    data[uid] = rec
    save_user_data(data)
    return rec


# ==========================
# Achievement Logic
# ==========================
def load_achievements():
    with open(ACH_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def cek_achievement(user_id: int):
    """Cek semua achievement untuk user, unlock yang terpenuhi dan belum didapat.
    Return list nama achievement yang baru didapat."""
    uid = str(user_id)
    data = load_user_data()
    rec = get_user_record(user_id)  # memastikan ada
    ach_defs = load_achievements()

    unlocked_now = []
    owned = set(rec.get("achievements", []))

    for key, ach in ach_defs.items():
        if key in owned:
            continue
        syarat = ach["syarat"]
        # Semua kondisi harus terpenuhi
        ok = True
        for field, target in syarat.items():
            if rec.get(field, 0) < target:
                ok = False
                break
        if ok:
            rec.setdefault("achievements", []).append(key)
            unlocked_now.append(ach["nama"])

    data[uid] = rec
    save_user_data(data)
    return unlocked_now


# Dipanggil jika user menjawab benar
def tambah_jawaban_benar(user_id: int):
    rec = get_user_record(user_id)
    rec["jawaban_benar"] += 1
    rec["poin"] += QUIZ_POINTS_CORRECT  # bonus poin
    update_user_record(user_id, **rec)
    return cek_achievement(user_id)


# Dipanggil saat user membeli sesuatu
def tambah_pembelian(user_id: int, harga: int):
    rec = get_user_record(user_id)
    rec["poin"] -= harga
    if rec["poin"] < 0:
        rec["poin"] = 0  # safety
    rec["pembelian"] += 1
    update_user_record(user_id, **rec)
    return cek_achievement(user_id)


# ==========================
# Bank Soal Quiz (contoh statis)
# ==========================
quiz_bank = [
    {
        "question": "Apa ibukota Indonesia?",
        "options": ["A. Jakarta", "B. Surabaya", "C. Bandung", "D. Medan"],
        "answer": "A"
    },
    {
        "question": "Planet ke-3 dari Matahari?",
        "options": ["A. Mars", "B. Venus", "C. Bumi", "D. Jupiter"],
        "answer": "C"
    },
    {
        "question": "Siapa penemu bola lampu?",
        "options": ["A. Newton", "B. Einstein", "C. Edison", "D. Tesla"],
        "answer": "C"
    }
]


# ==========================
# FusionBrain API Client
# ==========================
class FusionBrainAPI:
    def __init__(self, url, api_key, secret_key):
        self.URL = url
        self.AUTH_HEADERS = {
            'X-Key': f'Key {api_key}',
            'X-Secret': f'Secret {secret_key}',
        }

    def get_pipeline(self):
        response = requests.get(self.URL + 'key/api/v1/pipelines', headers=self.AUTH_HEADERS)
        response.raise_for_status()
        return response.json()[0]['id']

    def generate(self, prompt, pipeline, images=1, width=IMAGE_WIDTH, height=IMAGE_HEIGHT):
        params = {
            "type": "GENERATE",
            "numImages": images,
            "width": width,
            "height": height,
            "generateParams": {"query": prompt}
        }
        data = {
            'pipeline_id': (None, pipeline),
            'params': (None, json.dumps(params), 'application/json')
        }
        response = requests.post(self.URL + 'key/api/v1/pipeline/run', headers=self.AUTH_HEADERS, files=data)
        response.raise_for_status()
        return response.json()['uuid']

    def check_generation(self, request_id, attempts=10, delay=10):
        while attempts > 0:
            response = requests.get(self.URL + 'key/api/v1/pipeline/status/' + request_id, headers=self.AUTH_HEADERS)
            response.raise_for_status()
            data = response.json()
            if data['status'] == 'DONE':
                return data['result']['files']
            attempts -= 1
            time.sleep(delay)
        return None


api = FusionBrainAPI(
    'https://api-key.fusionbrain.ai/',
    '6CAE578B101F75847F807FAFB7EF0FDC',
    'C01DF41B2BBC24330BB8190D9555B61C'
)


# ==========================
# Command: start & help
# ==========================
@bot.command()
async def start(ctx):
    await ctx.send("Halo! Saya bot pembuat gambar AI + kuis + shop. Gunakan `!help` untuk lihat perintah.")


@bot.command(name="help")
async def help_command(ctx):
    await ctx.send(
        "**Perintah yang tersedia:**\n"
        "`!generate <prompt>` - Buat gambar dari deskripsi\n"
        "`!update` - Buat ulang gambar dari prompt terakhir\n"
        "`!quiz` - Mulai kuis tanya-jawab\n"
        f"`!poin` - Lihat poin kamu (mendapat {QUIZ_POINTS_CORRECT} poin per jawaban benar)\n"
        "`!shop` - Lihat daftar item shop\n"
        "`!beli <item_key>` - Beli item dari shop\n"
        "`!achievement` - Lihat achievement yang sudah didapat"
    )


# ==========================
# Command: Generate Image
# ==========================
@bot.command()
async def generate(ctx, *, prompt):
    user_last_prompt[ctx.author.id] = prompt
    async with ctx.typing():
        processing_msg = await ctx.send("🖼️ Sedang membuat gambar...")
        try:
            pipeline_id = api.get_pipeline()
            uuid = api.generate(prompt, pipeline_id)
            files = api.check_generation(uuid)
            if files:
                for idx, img_base64 in enumerate(files):
                    filename = f"temp_image_{idx+1}.png"
                    with open(filename, "wb") as f:
                        f.write(base64.b64decode(img_base64))
                    await ctx.send(file=discord.File(filename))
                    os.remove(filename)
            else:
                await ctx.send("❌ Gagal menghasilkan gambar.")
        except Exception as e:
            await ctx.send(f"Terjadi kesalahan: {e}")
        await processing_msg.delete()


# ==========================
# Command: Update Image (Regenerate last prompt)
# ==========================
@bot.command()
async def update(ctx):
    prompt = user_last_prompt.get(ctx.author.id)
    if not prompt:
        await ctx.send("⚠️ Kamu belum pernah generate gambar. Gunakan `!generate` dulu.")
        return
    async with ctx.typing():
        processing_msg = await ctx.send(f"🔁 Membuat ulang gambar dari prompt: `{prompt}`")
        try:
            pipeline_id = api.get_pipeline()
            uuid = api.generate(prompt, pipeline_id)
            files = api.check_generation(uuid)
            if files:
                for idx, img_base64 in enumerate(files):
                    filename = f"updated_image_{idx+1}.png"
                    with open(filename, "wb") as f:
                        f.write(base64.b64decode(img_base64))
                    await ctx.send(file=discord.File(filename))
                    os.remove(filename)
            else:
                await ctx.send("❌ Gagal menghasilkan ulang gambar.")
        except Exception as e:
            await ctx.send(f"Terjadi kesalahan saat update: {e}")
        await processing_msg.delete()


# ==========================
# Command: Quiz
# ==========================
@bot.command()
async def quiz(ctx):
    soal = random.choice(quiz_bank)
    pertanyaan = (
        f"🧠 {soal['question']}\n" + "\n".join(soal['options']) +
        f"\n\n*Ketik A/B/C/D untuk menjawab (15 detik)*"
    )
    await ctx.send(pertanyaan)

    def check(m):
        return m.author == ctx.author and m.channel == ctx.channel and m.content.upper() in ['A', 'B', 'C', 'D']

    try:
        msg = await bot.wait_for("message", timeout=15.0, check=check)
        if msg.content.upper() == soal['answer']:
            await ctx.send("✅ Benar!")
            unlocked = tambah_jawaban_benar(ctx.author.id)
            if QUIZ_POINTS_CORRECT:
                await ctx.send(f"+{QUIZ_POINTS_CORRECT} poin!")
            for ach in unlocked:
                await ctx.send(f"🏆 {ctx.author.mention} mendapatkan achievement: **{ach}**!")
        else:
            await ctx.send(f"❌ Salah! Jawaban benar: {soal['answer']}")
    except:
        await ctx.send(f"⌛ Waktu habis! Jawaban yang benar adalah: {soal['answer']}")


# ==========================
# Command: Lihat Poin
# ==========================
@bot.command()
async def poin(ctx):
    rec = get_user_record(ctx.author.id)
    await ctx.send(f"{ctx.author.mention}, kamu punya **{rec['poin']}** poin.")


# ==========================
# Command: Shop (lihat item)
# ==========================
@bot.command()
async def shop(ctx):
    with open(SHOP_FILE, "r", encoding="utf-8") as f:
        shop_data = json.load(f)

    rec = get_user_record(ctx.author.id)

    embed = discord.Embed(title="🛍️ Shop", description=f"Poin kamu: **{rec['poin']}**", color=discord.Color.blurple())
    for key, item in shop_data.items():
        harga = item.get("harga", 0)
        nama = item.get("nama", key)
        rname = item.get("role")
        desc = f"Harga: {harga} poin"
        if rname:
            desc += f"\nMemberi role: {rname}"
        embed.add_field(name=f"{key} — {nama}", value=desc, inline=False)

    await ctx.send(embed=embed)


# ==========================
# Command: Beli Item
# ==========================
@bot.command()
async def beli(ctx, item_key: str = None):
    if item_key is None:
        await ctx.send("Gunakan: `!beli <item_key>` — lihat `!shop` untuk daftar.")
        return

    # Load shop
    with open(SHOP_FILE, "r", encoding="utf-8") as f:
        shop_data = json.load(f)

    if item_key not in shop_data:
        await ctx.send("❌ Item tidak ditemukan di shop.")
        return

    item = shop_data[item_key]
    harga = item.get("harga", 0)
    role_name = item.get("role")

    # User data
    rec = get_user_record(ctx.author.id)

    if rec['poin'] < harga:
        await ctx.send(f"💸 Poin kamu tidak cukup. Kamu punya {rec['poin']}, harga item {harga}.")
        return

    # Kalau item kasih role, pastikan role ada di server
    if role_name:
        role = discord.utils.get(ctx.guild.roles, name=role_name)
        if role is None:
            await ctx.send(f"⚠️ Role `{role_name}` tidak ditemukan di server. Pembelian dibatalkan.")
            return

    # Kurangi poin & tambah pembelian
    unlocked = tambah_pembelian(ctx.author.id, harga)

    # Reload rec after update
    rec = get_user_record(ctx.author.id)

    # Beri role jika ada
    if role_name:
        try:
            role = discord.utils.get(ctx.guild.roles, name=role_name)
            if role:
                await ctx.author.add_roles(role, reason="Pembelian shop bot")
        except discord.Forbidden:
            await ctx.send("🚫 Bot tidak punya izin untuk memberi role ini. Minta admin atur permission & urutan role.")
        except Exception as e:
            await ctx.send(f"Terjadi kesalahan saat memberi role: {e}")

    await ctx.send(f"✅ {ctx.author.mention} berhasil membeli **{item.get('nama', item_key)}** seharga {harga} poin! Sisa poin: {rec['poin']}")

    # Achievement yang baru unlock dari pembelian/poin
    for ach in unlocked:
        await ctx.send(f"🏆 {ctx.author.mention} mendapatkan achievement: **{ach}**!")


# ==========================
# Command: Achievement
# ==========================
@bot.command()
async def achievement(ctx):
    rec = get_user_record(ctx.author.id)
    ach_defs = load_achievements()

    embed = discord.Embed(title="🎖️ Achievement Kamu", color=discord.Color.gold())
    for key, val in ach_defs.items():
        status = "✅" if key in rec.get("achievements", []) else "❌"
        embed.add_field(name=f"{status} {val['nama']}", value=val['deskripsi'], inline=False)

    await ctx.send(embed=embed)


# ==========================
# Jalankan Bot
# ==========================
bot.run(TOKEN)
