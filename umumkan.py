"""Kirim kartu pengumuman dashboard ke channel Discord, lengkap dengan tombol.

Tombolnya LINK BUTTON (style 5), dan itu sebabnya skrip ini cuma belasan baris
kerja: link button tidak pernah mengirim interaksi balik ke server, jadi tidak
perlu gateway, tidak perlu endpoint interaksi, tidak perlu proses yang hidup
terus. Sekali POST, tombolnya menempel di pesan itu selamanya.

Aman dipajang di channel yang dilihat banyak orang: yang mengklik tetap kena
gerbang login, dan yang bukan pemilik role premium ditolak di halaman depan.

    python umumkan.py            -> hanya menampilkan yang AKAN dikirim
    python umumkan.py --kirim    -> benar-benar mengirim
    python umumkan.py --uji      -> periksa susunan multipart, tanpa jaringan

Bawaannya menampilkan saja. Pesan ke channel member tidak bisa ditarik kembali
tanpa jejak, jadi mengirim harus diminta secara eksplisit.
"""
import json
import os
import pathlib
import secrets
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

ISI = f"""Win rate, riwayat panggilan, dan chart tiap call analis dalam satu halaman.

**Diperbarui otomatis**
• Zora: tiap 30 menit
• Neil, Lynx & analis lain: tiap hari

**Cara masuk**
Klik tombol di bawah, lalu *Authorize* dengan akun Discord kamu. Tidak ada kata sandi baru yang perlu diingat.

**Biar lancar**
• **Desktop**: buka lewat browser yang sudah login Discord
• **HP**: buka link-nya langsung dari aplikasi Discord

> Hanya pemilik role <@&{ROLE_PING}> yang bisa membukanya. Kalau ditolak, pastikan browser kamu masuk ke akun Discord yang benar."""

WARNA = 0x2F7BFF                         # --biru, sama dengan dashboard
KAKI = "Daily Rekom Crypto"

# BANNER adalah EMBED TERSENDIRI, bukan gambar di dalam kartu isi.
# Embed bergambar selalu menaruh gambarnya DI BAWAH teks; supaya banner muncul
# di ATAS seperti pengumuman Join Premium, ia harus jadi embed pertama yang
# isinya cuma gambar. Keduanya juga tidak boleh berbagi "url" yang sama -
# Discord akan menggabungkannya jadi satu kartu bergaleri.
#
# BANNER-nya DIUNGGAH, bukan ditautkan. Pesan ini akan dipin permanen, dan
# tautan ke pihak ketiga bisa mati kapan saja - imgur menghapusnya, mengubah
# kebijakan hotlink, atau sekadar tidak bisa dihubungi - dan yang tersisa
# adalah kotak kosong di pengumuman utama, selamanya. Berkas yang ikut terunggah
# jadi bagian dari pesan itu sendiri dan hidup selama pesannya hidup.
#
# Boleh diisi URL (diunduh dulu) atau jalur berkas di laptop.
BANNER = os.environ.get("UMUMKAN_BANNER", "")

# Batas lampiran server tanpa boost adalah 10 MB. Diperiksa sendiri supaya
# gagalnya berbunyi jelas, bukan HTTP 413 yang tidak menyebut apa-apa.
BATAS_BANNER = 9 * 1024 * 1024

JENIS = {"image/png": "png", "image/jpeg": "jpg", "image/gif": "gif", "image/webp": "webp"}

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


def ambil_banner():
    """Memulangkan (nama, isi, mime) untuk diunggah, atau None kalau tidak dipakai."""
    if not BANNER:
        return None

    if BANNER.startswith(("http://", "https://")):
        # User-Agent bergaya peramban: imgur dan sebagian CDN membalas 403 untuk
        # yang terlihat seperti skrip.
        req = urllib.request.Request(BANNER, headers={"User-Agent": "Mozilla/5.0"})
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                isi = r.read()
                mime = (r.headers.get("Content-Type") or "").split(";")[0].strip()
        except urllib.error.URLError as e:
            sys.exit(f"banner tidak bisa diunduh dari {BANNER}: {e}")
    else:
        p = pathlib.Path(BANNER)
        if not p.is_file():
            sys.exit(f"banner tidak ditemukan: {p}")
        isi = p.read_bytes()
        mime = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
                ".gif": "image/gif", ".webp": "image/webp"}.get(p.suffix.lower(), "")

    if mime not in JENIS:
        sys.exit(f"banner bukan gambar yang dikenal (Content-Type: {mime or 'tidak diketahui'}). "
                 f"Kalau memakai imgur, pastikan tautannya yang LANGSUNG - i.imgur.com/xxx.png, "
                 f"bukan halaman imgur.com/xxx.")
    if len(isi) > BATAS_BANNER:
        sys.exit(f"banner {len(isi)/1024/1024:.1f} MB, melebihi batas {BATAS_BANNER/1024/1024:.0f} MB.")
    return f"banner.{JENIS[mime]}", isi, mime


def kirim_pesan(pesan, lampiran):
    """POST pesannya. Dengan lampiran, badannya multipart - bukan JSON biasa.

    Ditulis tangan alih-alih memakai pustaka: satu berkas, satu bidang JSON,
    dan requests bukan dependency proyek ini.
    """
    if not lampiran:
        return minta(f"/channels/{CHANNEL}/messages", pesan)

    nama, isi, mime = lampiran
    batas = "----drc" + secrets.token_hex(12)

    def bagian(kepala, badan):
        return (b"--" + batas.encode() + b"\r\n" + kepala + b"\r\n\r\n" + badan + b"\r\n")

    badan = bytearray()
    badan += bagian(
        b'Content-Disposition: form-data; name="payload_json"\r\n'
        b"Content-Type: application/json",
        json.dumps(pesan, ensure_ascii=False).encode("utf-8"),
    )
    badan += bagian(
        f'Content-Disposition: form-data; name="files[0]"; filename="{nama}"\r\n'
        f"Content-Type: {mime}".encode("utf-8"),
        isi,
    )
    badan += b"--" + batas.encode() + b"--\r\n"

    req = urllib.request.Request(
        f"{API}/channels/{CHANNEL}/messages",
        data=bytes(badan),
        headers={**UA,
                 "Authorization": f"Bot {os.environ.get('DISCORD_BOT_TOKEN', '')}",
                 "Content-Type": f"multipart/form-data; boundary={batas}"},
    )
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read().decode("utf-8"))


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


def susun(bisa, lampiran):
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
        if lampiran:
            nama = lampiran[0]
            # attachment:// menunjuk berkas yang ikut TERUNGGAH di pesan yang
            # sama. Bukan URL - Discord menyambungkannya sendiri ke lampiran
            # bernama itu, jadi tidak ada pihak ketiga yang bisa membuatnya mati.
            embeds.append({"image": {"url": f"attachment://{nama}"}, "color": WARNA})
            m["attachments"] = [{"id": 0, "filename": nama}]
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


def _uji():
    """Bongkar ulang badan multipart yang disusun sendiri.

    Encoding-nya ditulis tangan, dan salah satu CRLF saja sudah cukup membuat
    Discord menolaknya dengan galat yang tidak menyebut sebabnya. Jadi badannya
    disusun, lalu dibaca ULANG dengan pengurai standar - kalau JSON-nya utuh dan
    byte gambarnya sama persis, susunannya benar. Tidak ada pesan yang terkirim.

        python umumkan.py --uji
    """
    import email
    import re

    gambar = bytes(range(256)) * 40 + b"\r\n--palsu--\r\n"   # sengaja memuat CRLF dan garis batas
    pesan = {"content": "halo — ünïcode", "embeds": [{"image": {"url": "attachment://banner.png"}}]}

    terkirim = {}

    def palsu(req, timeout=None):                    # noqa: ARG001
        terkirim["ct"] = req.headers["Content-type"]
        terkirim["badan"] = req.data
        raise SystemExit("_uji tidak boleh benar-benar mengirim")

    asli = urllib.request.urlopen
    urllib.request.urlopen = palsu
    try:
        kirim_pesan(pesan, ("banner.png", gambar, "image/png"))
    except SystemExit:
        pass
    finally:
        urllib.request.urlopen = asli

    batas = re.search(r"boundary=(.+)$", terkirim["ct"]).group(1)
    mentah = (f"Content-Type: multipart/form-data; boundary={batas}\r\n\r\n").encode() + terkirim["badan"]
    pesan_email = email.message_from_bytes(mentah)
    bagian = {p.get_param("name", header="content-disposition"): p for p in pesan_email.get_payload()}

    assert set(bagian) == {"payload_json", "files[0]"}, f"bidang meleset: {set(bagian)}"
    balik = json.loads(bagian["payload_json"].get_payload(decode=True).decode("utf-8"))
    assert balik == pesan, "payload_json berubah saat dibungkus"
    berkas = bagian["files[0]"]
    assert berkas.get_filename() == "banner.png", berkas.get_filename()
    assert berkas.get_content_type() == "image/png", berkas.get_content_type()
    isi = berkas.get_payload(decode=True)
    assert isi == gambar, f"byte gambar berubah: {len(isi)} vs {len(gambar)}"

    print("umumkan: badan multipart lolos - JSON utuh, gambar utuh, nama dan tipe benar")


def main():
    if "--uji" in sys.argv:
        return _uji()

    ch, me, bisa = izin()
    lampiran = ambil_banner() if bisa["embed"] else None
    pesan = susun(bisa, lampiran)

    print(f"bot     : {me['username']}")
    print(f"channel : #{ch.get('name')} ({CHANNEL})")
    print(f"tombol  : [{TOMBOL}] -> {DASHBOARD}")
    print(f"kartu   : {'ya' if bisa['embed'] else 'TIDAK - beri izin Embed Links kalau mau'}")
    if lampiran:
        print(f"banner  : {lampiran[0]} ({len(lampiran[1])/1024:.0f} KB, {lampiran[2]}) - DIUNGGAH")
    else:
        print(f"banner  : {'TIDAK ADA - isi UMUMKAN_BANNER kalau mau'}")
    kabar_ping = ("@Premium" if bisa["ping"] else
                  "TIDAK - beri izin Mention Everyone, atau jadikan role Premium mentionable")
    print(f"ping    : {kabar_ping}")
    if not bisa["kirim"]:
        sys.exit("\nbot tidak punya izin Send Messages di channel ini - berhenti.")

    if "--kirim" not in sys.argv:
        print("\n--- tampilan akhir ---\n")
        if lampiran:
            print(f"[ banner terlampir: {lampiran[0]} ]\n")
        print(f"**{JUDUL}**")
        for baris in ISI.split("\n"):
            print(f"  {baris}" if baris else "")
        print(f"  {KAKI}")
        print(f"\n[ {TOMBOL} ] -> {DASHBOARD}")
        print("\n(belum dikirim. tambahkan --kirim untuk benar-benar mengirim)")
        return

    try:
        hasil = kirim_pesan(pesan, lampiran)
    except urllib.error.HTTPError as e:
        sys.exit(f"gagal: HTTP {e.code} {e.read().decode('utf-8', 'replace')[:300]}")
    print(f"\nterkirim: https://discord.com/channels/{GUILD}/{CHANNEL}/{hasil['id']}")
    print("saran: pin pesannya supaya tidak perlu diposting ulang.")


if __name__ == "__main__":
    main()
