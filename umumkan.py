"""Kirim kartu pengumuman dashboard ke channel Discord, lengkap dengan tombol.

Tombolnya LINK BUTTON (style 5), dan itu sebabnya skrip ini cuma belasan baris
kerja: link button tidak pernah mengirim interaksi balik ke server, jadi tidak
perlu gateway, tidak perlu endpoint interaksi, tidak perlu proses yang hidup
terus. Sekali POST, tombolnya menempel di pesan itu selamanya.

Aman dipajang di channel yang dilihat banyak orang: yang mengklik tetap kena
gerbang login, dan yang bukan pemilik role premium ditolak di halaman depan.

    python umumkan.py            -> hanya menampilkan yang AKAN dikirim
    python umumkan.py --kirim    -> benar-benar mengirim

Bawaannya menampilkan saja. Pesan ke channel member tidak bisa ditarik kembali
tanpa jejak, jadi mengirim harus diminta secara eksplisit.
"""
import json
import os
import sys
import urllib.error
import urllib.request

import env_lokal  # noqa: F401  (mengisi environment dari .env)

API = "https://discord.com/api/v10"
UA = {"User-Agent": "DiscordBot (https://localhost, 1.0)"}

CHANNEL = "1551208988824182864"          # #🤖︱analyst-tracker
GUILD = "1199773381097181317"
ROLE_PING = "1246803191505358928"        # @Premium

DASHBOARD = os.environ.get("APP_URL", "https://drc.up.railway.app").rstrip("/")

# --------------------------------------------------------------------- isi
JUDUL = "Analyst Dashboard"

ISI = f"""Win rate, riwayat panggilan, dan chart tiap call analis — semuanya dalam satu halaman.

**Diperbarui otomatis**
• Zora — tiap 30 menit
• Neil, Lynx & analis lain — tiap hari

**Cara masuk**
Klik tombol di bawah, lalu *Authorize* dengan akun Discord kamu. Tidak ada kata sandi baru yang perlu diingat.

**Biar lancar**
• **Desktop** — buka lewat browser yang sudah login Discord
• **HP** — buka link-nya langsung dari aplikasi Discord

> Hanya pemilik role <@&{ROLE_PING}> yang bisa membukanya. Kalau ditolak, pastikan browser kamu masuk ke akun Discord yang benar."""

WARNA = 0x2F7BFF                         # --biru, sama dengan dashboard
KAKI = "Daily Rekom Crypto"

# BANNER adalah EMBED TERSENDIRI, bukan gambar di dalam kartu isi.
# Embed bergambar selalu menaruh gambarnya DI BAWAH teks; supaya banner muncul
# di ATAS seperti pengumuman Join Premium, ia harus jadi embed pertama yang
# isinya cuma gambar. Keduanya juga tidak boleh berbagi "url" yang sama -
# Discord akan menggabungkannya jadi satu kartu bergaleri.
BANNER = os.environ.get("UMUMKAN_BANNER", "")

TOMBOL = "Buka Dashboard"


def minta(jalur, data=None, metode=None):
    token = os.environ.get("DISCORD_BOT_TOKEN", "")
    if not token:
        sys.exit("DISCORD_BOT_TOKEN belum diset di environment")
    h = dict(UA, Authorization=f"Bot {token}")
    badan = None
    if data is not None:
        badan = json.dumps(data).encode("utf-8")
        h["Content-Type"] = "application/json"
    req = urllib.request.Request(f"{API}{jalur}", data=badan, headers=h, method=metode)
    with urllib.request.urlopen(req, timeout=30) as r:
        isi = r.read().decode("utf-8")
        return json.loads(isi) if isi else {}


def izin():
    """Izin efektif bot di CHANNEL, memakai urutan resolusi Discord.

    Diperiksa LEBIH DULU, bukan dibiarkan gagal saat kirim: tanpa Embed Links,
    Discord menolak seluruh pesannya dengan 403 "Missing Permissions" yang tidak
    menyebut izin mana yang kurang - dan menebaknya itu lambat.
    """
    ch = minta(f"/channels/{CHANNEL}")
    me = minta("/users/@me")
    anggota = minta(f"/guilds/{GUILD}/members/{me['id']}")
    semua = {r["id"]: int(r["permissions"]) for r in minta(f"/guilds/{GUILD}/roles")}

    punya = set(anggota["roles"])
    p = semua.get(GUILD, 0)
    for rid in punya:
        p |= semua.get(rid, 0)
    if p & (1 << 3):                     # Administrator: semua izin
        return ch, me, {"embed": True, "ping": True, "kirim": True}

    ow = {o["id"]: o for o in ch.get("permission_overwrites", [])}
    if GUILD in ow:
        p &= ~int(ow[GUILD]["deny"])
        p |= int(ow[GUILD]["allow"])
    tolak = beri = 0
    for rid in punya:
        if rid in ow:
            tolak |= int(ow[rid]["deny"])
            beri |= int(ow[rid]["allow"])
    p &= ~tolak
    p |= beri
    if me["id"] in ow:
        p &= ~int(ow[me["id"]]["deny"])
        p |= int(ow[me["id"]]["allow"])

    return ch, me, {
        "kirim": bool(p & (1 << 11)),
        "embed": bool(p & (1 << 14)),
        "ping": bool(p & (1 << 17)),
    }


def susun(bisa):
    """Muatan pesan, menyesuaikan izin yang benar-benar dipunyai.

    Tombol TIDAK pernah ikut disesuaikan: komponen bukan embed dan tidak butuh
    Embed Links, jadi bagian terpenting pengumuman ini selalu terkirim walau
    izin lainnya belum diberikan.
    """
    m = {
        "components": [{
            "type": 1,
            "components": [{"type": 2, "style": 5, "label": TOMBOL, "url": DASHBOARD}],
        }],
        # Daftar putih mention: hanya role ini yang boleh memicu notifikasi,
        # sehingga <@&...> di dalam kutipan tidak pernah berubah jadi ping kedua
        # dan salah ketik tidak pernah berubah jadi @everyone.
        "allowed_mentions": {"parse": [], "roles": [ROLE_PING] if bisa["ping"] else []},
    }

    if bisa["embed"]:
        embeds = []
        if BANNER:
            embeds.append({"image": {"url": BANNER}, "color": WARNA})
        embeds.append({
            "title": JUDUL,
            "description": ISI,
            "color": WARNA,
            "url": DASHBOARD,
            "footer": {"text": KAKI},
        })
        m["embeds"] = embeds
        m["content"] = f"<@&{ROLE_PING}>" if bisa["ping"] else ""
    else:
        # Tanpa Embed Links, isinya turun jadi teks biasa. Tetap terbaca, tetap
        # bertombol - cuma tidak ada kartu berwarna maupun banner.
        kepala = f"<@&{ROLE_PING}>\n\n" if bisa["ping"] else ""
        m["content"] = f"{kepala}**{JUDUL}**\n{ISI}"
    return m


def main():
    ch, me, bisa = izin()
    pesan = susun(bisa)

    print(f"bot     : {me['username']}")
    print(f"channel : #{ch.get('name')} ({CHANNEL})")
    print(f"tombol  : [{TOMBOL}] -> {DASHBOARD}")
    print(f"kartu   : {'ya' if bisa['embed'] else 'TIDAK - beri izin Embed Links kalau mau'}")
    print(f"banner  : {BANNER or 'TIDAK ADA - isi UMUMKAN_BANNER kalau mau'}")
    kabar_ping = ("@Premium" if bisa["ping"] else
                  "TIDAK - beri izin Mention Everyone, atau jadikan role Premium mentionable")
    print(f"ping    : {kabar_ping}")
    if not bisa["kirim"]:
        sys.exit("\nbot tidak punya izin Send Messages di channel ini - berhenti.")

    if "--kirim" not in sys.argv:
        print("\n--- tampilan akhir ---\n")
        if BANNER:
            print(f"[ banner: {BANNER} ]\n")
        print(f"**{JUDUL}**")
        for baris in ISI.split("\n"):
            print(f"  {baris}" if baris else "")
        print(f"  — {KAKI}")
        print(f"\n[ {TOMBOL} ] -> {DASHBOARD}")
        print("\n(belum dikirim. tambahkan --kirim untuk benar-benar mengirim)")
        return

    try:
        hasil = minta(f"/channels/{CHANNEL}/messages", pesan)
    except urllib.error.HTTPError as e:
        sys.exit(f"gagal: HTTP {e.code} {e.read().decode('utf-8', 'replace')[:300]}")
    print(f"\nterkirim: https://discord.com/channels/{GUILD}/{CHANNEL}/{hasil['id']}")
    print("saran: pin pesannya supaya tidak perlu diposting ulang.")


if __name__ == "__main__":
    main()
