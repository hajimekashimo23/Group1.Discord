import discord
from discord.ext import commands
import base64
import os
import json
import requests
import time
import random
from dotenv import load_dotenv

# Load token dari .env
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)

# Simpan prompt terakhir tiap user
user_last_prompt = {}

# Inisialisasi file data user dan achievement jika belum ada
if not os.path.exists("user_data.json"):
    with open("user_data.json", "w") as f:
        json.dump({}, f)

if not os.path.exists("achievements.json"):
    achievements = {
        "first_win": {
            "nama": "First Answer Right!",
            "deskripsi": "Jawab satu soal kuis.",
            "syarat": {"jawaban_benar": 1}
        },
        "quiz_streak": {
            "nama": "Great Answer!",
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
    }
    with open("achievements.json", "w") as f:
        json.dump(achievements, f, indent=4)

# Bank soal quiz
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

    def generate(self, prompt, pipeline, images=1, width=1024, height=1024):
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

def tambah_jawaban_benar(user_id):
    user_id = str(user_id)
    with open("user_data.json", "r") as f:
        data = json.load(f)
    user = data.get(user_id, {"jawaban_benar": 0, "achievements": [], "poin": 0, "pembelian": 0})
    user["jawaban_benar"] += 1
    data[user_id] = user
    with open("user_data.json", "w") as f:
        json.dump(data, f, indent=4)
    return cek_achievement(user_id, user)

def cek_achievement(user_id, user_data):
    with open("achievements.json", "r") as f:
        achievements = json.load(f)

    unlocked = []
    for key, ach in achievements.items():
        if key in user_data.get("achievements", []):
            continue
        syarat = ach["syarat"]
        if all(user_data.get(k, 0) >= v for k, v in syarat.items()):
            user_data["achievements"].append(key)
            unlocked.append(ach["nama"])

    with open("user_data.json", "r") as f:
        all_data = json.load(f)
    all_data[user_id] = user_data
    with open("user_data.json", "w") as f:
        json.dump(all_data, f, indent=4)
    return unlocked

@bot.command()
async def start(ctx):
    await ctx.send("Halo! Saya bot pembuat gambar AI dan juga bisa kasih kuis. Gunakan `!help` untuk melihat perintah.")

@bot.command(name="help")
async def help_command(ctx):
    await ctx.send(
        "**Perintah yang tersedia:**\n"
        "`!generate <prompt>` - Buat gambar dari deskripsi\n"
        "`!update` - Buat ulang gambar dari prompt terakhir\n"
        "`!quiz` - Mulai kuis tanya-jawab\n"
        "`!achievement` - Lihat achievement yang sudah didapat"
    )

@bot.command()
async def generate(ctx, *, prompt):
    user_last_prompt[ctx.author.id] = prompt
    async with ctx.typing():
        processing_msg = await ctx.send("\U0001F5BC Sedang membuat gambar...")
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
                await ctx.send("\u274C Gagal menghasilkan gambar.")
        except Exception as e:
            await ctx.send(f"Terjadi kesalahan: {e}")
        await processing_msg.delete()

@bot.command()
async def update(ctx):
    prompt = user_last_prompt.get(ctx.author.id)
    if not prompt:
        await ctx.send("\u26A0\ufe0f Kamu belum pernah generate gambar. Gunakan `!generate` dulu.")
        return
    async with ctx.typing():
        processing_msg = await ctx.send(f"\uD83D\uDD01 Membuat ulang gambar dari prompt: `{prompt}`")
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
                await ctx.send("\u274C Gagal menghasilkan ulang gambar.")
        except Exception as e:
            await ctx.send(f"Terjadi kesalahan saat update: {e}")
        await processing_msg.delete()

@bot.command()
async def quiz(ctx):
    soal = random.choice(quiz_bank)
    pertanyaan = f"\U0001F9E0 {soal['question']}\n" + "\n".join(soal['options']) + "\n\n*Ketik A/B/C/D untuk menjawab (15 detik)*"
    await ctx.send(pertanyaan)

    def check(m):
        return m.author == ctx.author and m.channel == ctx.channel and m.content.upper() in ['A', 'B', 'C', 'D']

    try:
        msg = await bot.wait_for("message", timeout=15.0, check=check)
        if msg.content.upper() == soal['answer']:
            await ctx.send("\u2705 Benar!")
            unlocked = tambah_jawaban_benar(ctx.author.id)
            for ach in unlocked:
                await ctx.send(f"\U0001F3C6 {ctx.author.mention} berhasil mendapatkan achievement: **{ach}**!")
        else:
            await ctx.send(f"\u274C Salah! Jawaban benar: {soal['answer']}")
    except:
        await ctx.send(f"\u23F3 Waktu habis! Jawaban yang benar adalah: {soal['answer']}")

@bot.command()
async def achievement(ctx):
    user_id = str(ctx.author.id)
    with open("user_data.json", "r") as f:
        data = json.load(f)
    user_data = data.get(user_id, {"achievements": []})
    with open("achievements.json", "r") as f:
        all_ach = json.load(f)

    embed = discord.Embed(title="🎖️ Achievement Kamu", color=discord.Color.gold())
    for key, val in all_ach.items():
        status = "✅" if key in user_data.get("achievements", []) else "❌"
        embed.add_field(name=f"{status} {val['nama']}", value=val['deskripsi'], inline=False)

    await ctx.send(embed=embed)

bot.run(TOKEN)
