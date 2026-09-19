"""Ringkasan obrolan analis dari Discord, lewat Bot API resmi.

KENAPA BOT RESMI, BUKAN TOKEN AKUN PRIBADI:

  Cara yang beredar di internet adalah memakai token akun Anda sendiri untuk
  membaca pesan — yang disebut self-bot. Itu melanggar Ketentuan Layanan
  Discord secara eksplisit dan berujung banned permanen. Skrip ini memakai Bot
  API resmi: bot punya identitas sendiri, diundang ke server oleh pemiliknya,
  dan hanya membaca channel yang izinnya diberikan.

APA YANG DIBUTUHKAN SEKALI SAJA:

  1. Buat aplikasi di https://discord.com/developers/applications
  2. Tab "Bot" -> Reset Token -> salin tokennya
  3. Di tab "Bot", nyalakan **MESSAGE CONTENT INTENT**. Tanpa itu isi pesan
     pulang dalam keadaan kosong, dan itu gagal secara diam-diam — pesannya
     terhitung ada tetapi teksnya kosong.
  4. Tab "OAuth2" -> URL Generator -> scope `bot`, permission
     `View Channels` + `Read Message History` -> buka URL-nya, undang ke server
  5. setx DISCORD_BOT_TOKEN "..."   lalu tutup dan buka ulang terminal
  6. Di Discord, aktifkan Developer Mode (Settings > Advanced), lalu klik kanan
     tiap channel -> Copy Channel ID, dan isikan ke discord_channels.json

BATAS YANG PERLU DISADARI:

  - Bot hanya melihat channel yang izinnya ia punya. Channel privat yang tidak
    dibuka untuknya tidak akan terbaca, dan itu memang seharusnya begitu.
  - Ringkasan LLM bisa keliru. Karena itu jumlah pesan, rentang waktu, dan
    kutipan mentahnya ikut disimpan supaya hasilnya bisa diperiksa sendiri.
  - Ini KONTEKS, bukan sinyal. Proyek ini sudah dua kali mengukur bahwa
    sentimen berita tidak mendahului arah harga; obrolan analis satu keluarga
    dengan itu.

Pakai:
    python fetch_discord.py              -> discord_ringkas.json
    python fetch_discord.py --jam 48     -> jendela 48 jam ke belakang
"""
import sys as _sys

# Nama analis memuat huruf di luar cp1252 (tanda kutip miring pada
# "Trader Neil's Bot"). Windows memakai cp1252 begitu keluarannya dialihkan ke
# berkas atau ditangkap proses lain, dan satu print nama sudah cukup untuk
# menjatuhkan seluruh penarikan dengan UnicodeEncodeError. Terjadi sungguhan,
# dan di Railway seluruh keluaran memang selalu ditangkap.
for _s in (_sys.stdout, _sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:                                        # noqa: BLE001
        pass

import concurrent.futures as cf
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

# Binance diblokir di lapis DNS oleh ISP Indonesia; ini memulihkannya.
# .env folder ini ikut dimuat, supaya kunci tidak harus lewat setx.
import env_lokal  # noqa: E402,F401
import dns_doh  # noqa: E402,F401
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
# --- jalur berkas disesuaikan untuk proyek dashboard analis ---------------
#
# Berkas datanya hidup di data/, bukan di sebelah skrip. Dan di Railway, apa pun
# yang ditulis ke folder aplikasi hilang pada deploy berikutnya - jadi tulisannya
# diarahkan ke volume permanen (DATA_DIR) kalau ada.
#
# Arsip dan konfigurasi DISALIN sekali dari repo ke volume saat pertama kali
# dibutuhkan. Tanpa itu, penarikan pertama di server mulai tanpa arsip dan
# mengekstrak ulang ribuan pesan lama secara sia-sia.
import shutil as _shutil

_REPO_DATA = HERE / "data"
_vol = os.environ.get("DATA_DIR")
DATA_TULIS = (Path(_vol) if _vol and Path(_vol).is_dir() else _REPO_DATA)


def _siapkan(nama):
    tujuan = DATA_TULIS / nama
    asal = _REPO_DATA / nama
    if not tujuan.exists() and asal.exists() and tujuan != asal:
        tujuan.parent.mkdir(parents=True, exist_ok=True)
        _shutil.copy2(asal, tujuan)
    return tujuan


OUT = DATA_TULIS / "discord_ringkas.json"
# Arsip inkremental. Enam bulan chat hanya sekitar seribu pesan dan seratus lima
# puluh panggilan, jadi JSON sudah cukup — database tidak diperlukan di skala
# ini. Gunanya satu: pesan yang sudah pernah diekstrak tidak pernah dikirim ke
# LLM dua kali, sehingga menjalankan ulang berbiaya hampir nol.
ARSIP = _siapkan("discord_arsip.json")
KONFIG = _siapkan("discord_channels.json")

API = "https://discord.com/api/v10"
# Dua User-Agent, dan keduanya WAJIB berbeda — terukur, bukan kehati-hatian:
#   Discord mensyaratkan format "DiscordBot (url, versi)". Diberi string bergaya
#     browser, ia memulangkan 0 pesan tanpa galat, yang jauh lebih menyesatkan
#     daripada penolakan terang-terangan.
#   Binance futures (fapi) justru sebaliknya: User-Agent bergaya pustaka ditolak
#     dengan HTTP 403.
UA = {"User-Agent": "DiscordBot (https://localhost, 1.0)"}
UA_BURSA = {"User-Agent": "Mozilla/5.0 (compatible; LQDashboard/1.0)"}

TOKEN = os.environ.get("DISCORD_BOT_TOKEN", "")

# Endpoint peringkas: apa pun yang bicara protokol OpenAI chat/completions.
# Bawaannya xAI karena kuncinya sudah ada di mesin ini; Groq, OpenRouter, dan
# Mistral semuanya cocok dengan mengganti tiga variabel di bawah.
LLM_BASE = os.environ.get("LLM_BASE", "https://api.x.ai/v1")
LLM_MODEL = os.environ.get("LLM_MODEL", "grok-4-fast")
LLM_KEY = os.environ.get("LLM_KEY") or os.environ.get("XAI_API_KEY", "")


def minta(url, headers=None, data=None, timeout=40):
    h = dict(UA_BURSA if "binance.com" in url else UA)
    h.update(headers or {})
    req = urllib.request.Request(url, data=data, headers=h)
    if data is not None:
        req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def contoh_konfig():
    KONFIG.write_text(json.dumps({
        "_cara": "Nyalakan Developer Mode di Discord, klik kanan nama channel di "
                 "daftar kiri, Copy Channel ID, lalu tempel di 'id'. 'nama' bebas.",
        "_analis": "OPSIONAL. Isi user ID atau username analis yang ingin dibaca; "
                   "pesan dari orang lain diabaikan. Kosongkan untuk membaca semua "
                   "orang. Jalankan 'python fetch_discord.py --cek' untuk melihat "
                   "daftar penulis beserta ID-nya. Bisa juga ditaruh per channel.",
        "analis": [],
        "channels": [
            {"nama": "Contoh — ganti ini", "id": "000000000000000000"},
        ],
    }, ensure_ascii=False, indent=1), encoding="utf-8")


def minta_h(url, headers=None, data=None, timeout=40):
    """Seperti minta(), tetapi juga memulangkan sisa kuota token dari header.

    Groq mengirim x-ratelimit-remaining-tokens di tiap balasan. Membacanya jauh
    lebih tepat daripada menebak jeda, karena batasnya token per menit — bukan
    jumlah permintaan.
    """
    h = dict(UA)
    h.update(headers or {})
    req = urllib.request.Request(url, data=data, headers=h)
    if data is not None:
        req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        badan = json.loads(r.read().decode("utf-8"))
        sisa = r.headers.get("x-ratelimit-remaining-tokens")
        try:
            sisa = int(sisa) if sisa is not None else None
        except (TypeError, ValueError):
            sisa = None
        return badan, sisa


def saring_analis(pesan, analis):
    """Sisakan hanya pesan dari analis yang didaftarkan.

    Tanpa penyaring ini, channel yang ramai membuat ringkasan encer dan
    melahirkan "panggilan" dari obrolan santai anggota biasa. Kosongkan
    daftarnya kalau memang ingin semua orang ikut terbaca.
    """
    if not analis:
        return pesan, 0
    kunci = {str(a).lower().lstrip("@") for a in analis}
    simpan = [p for p in pesan
              if p.get("penulisId") in kunci or (p.get("penulis") or "").lower() in kunci]

    # Peringatkan kalau sebuah bot tersaring lewat NAMA, bukan ID. Webhook boleh
    # mengganti nama tampilannya per pesan — terukur: filter "sinyalbot" hanya
    # menangkap 2 dari 3 pesan karena satu di antaranya tertulis "Sinyal Bot".
    # Kebocoran semacam ini tidak menimbulkan galat, hanya diam-diam kehilangan
    # data, jadi harus disebut.
    for p in simpan:
        if p.get("bot") and p.get("penulisId") not in kunci:
            print(f"      PERINGATAN: {p['penulis']} adalah bot yang tersaring lewat nama. "
                  f"Ganti dengan ID {p.get('penulisId')} — nama webhook bisa "
                  f"berubah tiap pesan dan sebagian akan terlewat.")
            break

    # Entri yang tidak pernah cocok dengan siapa pun. Tanpa peringatan ini,
    # salah tulis satu nama membuat seluruh channel pulang kosong dan terlihat
    # seperti channelnya memang sepi.
    ada = {p.get("penulisId") for p in pesan} | {(p.get("penulis") or "").lower() for p in pesan}
    nihil = [a for a in analis if str(a).lower().lstrip("@") not in ada]
    if nihil:
        print(f"      PERINGATAN: {', '.join(map(str, nihil))} tidak cocok dengan "
              f"penulis mana pun di sini.")
        # Format lama username#0001 sudah dihapus Discord sejak 2023; nama
        # sekarang tidak lagi membawa empat angka di belakangnya.
        if any("#" in str(a) for a in nihil):
            print("      Nama bergaya lama 'nama#1234' sudah tidak dipakai Discord. "
                  "Pakai user ID-nya — jalankan --cek untuk melihat daftarnya.")
        contoh = sorted({(p.get("penulis") or "?") + " (id " + (p.get("penulisId") or "?") + ")"
                         for p in pesan})[:6]
        if contoh:
            print("      Yang benar-benar menulis di sini: " + "; ".join(contoh))

    return simpan, len(pesan) - len(simpan)


RE_URL = re.compile(r"https?://[^\s<>\"')\]]+")

# Klaim hasil yang diumumkan analis sendiri. Dibaca dengan pola teks, BUKAN
# LLM: bentuknya baku, jadi regex membacanya tepat, gratis, dan bisa ditelusuri.
# Ini melengkapi penilaian harga Binance, bukan menggantikannya — yang satu
# "apa kata mereka", yang lain "apa yang terjadi". Selisih keduanya justru
# bagian paling berguna.
# Pola pengakuan hasil, disusun dari kalimat SUNGGUHAN di channel — bukan
# tebakan. Contoh yang sempat lolos dari versi pertama dan kini tertangkap:
#
#   "Stopped on ZEC guys, couple of L's recently in a row"
#   "Stops hit on HYPE guys, had us back and forth all day"
#   "TP1 smashed on FARTCOIN fam, stops BE. Good wins today"
#   "Going to go ahead and take TP1 on JTO here at 0.58. Good W"
#   "Full TP hit on ETH @ 1921 for 12R"
#   "Closing ENA early here before the 1H close"
#
# URUTAN MENENTUKAN BENAR-SALAHNYA:
#   TP dulu   -> "TP1 smashed on FARTCOIN, stops BE" hasilnya TP. "stops BE" di
#                situ memindahkan stop pada SISA posisi, bukan hasil posisinya.
#   lalu BE   -> "Stopped BE on the rest" tanpa sebutan TP memang impas.
#   lalu stop -> "stops BE" juga mengandung kata "stops", jadi kalau stop
#                diperiksa lebih dulu, impas salah tercatat sebagai kerugian.
KLAIM = [
    (re.compile(r"\btp\s*\d*\s*(?:hit|reached|done|smashed|tagged|secured|filled)\b"
                r"|\bhit\s+tp\s*\d*\b|\bgot\s+tp\s*\d*\b"
                r"|\btak(?:e|ing|en)\s+tp\s*\d*\b|\bfull\s+tp\b"
                r"|\btarget\s+(?:hit|reached|smashed)\b", re.I), "diaku TP kena"),
    (re.compile(r"\bstop(?:s|ped)?\s+(?:out\s+)?be\b|\bbreak\s*even\b"
                r"|\bmoved?\s+(?:to\s+)?be\b|\bstops?\s+to\s+be\b", re.I), "diaku BE"),
    (re.compile(r"\bstop(?:s|ped)?\s+(?:hit|out|on)\b|\bsl\s+hit\b"
                r"|\bhit\s+(?:my\s+)?sl\b|\bstopped\b|\bgot\s+stopped\b"
                r"|\bcouple\s+of\s+l'?s\b|\btook\s+(?:a\s+)?loss\b", re.I),
     "diaku kena stop"),
    (re.compile(r"\bclos(?:ed|ing)\b|\btook\s+profit\b|\bpartials?\b", re.I),
     "diaku ditutup"),
]

# TP1 / TP2 / TP3 yang berdiri sendiri, tanpa kata kerja apa pun.
#
# Perhatikan huruf "s" sengaja TIDAK diizinkan: "TPs above" dan "TPs 2/3 above"
# adalah cara analis menyebut target yang DIGAMBAR di chart, bukan target yang
# sudah kena. Pola \btp\s?[1-4]\b tidak menyentuh keduanya karena setelah "tp"
# harus langsung angka.
# Lynx menulis kabar hasil dalam bahasa Indonesia dan sangat singkat, sering
# hanya satu kata di balasan. Contoh sungguhan dari channel:
#
#   "Running"                      -> posisi sedang untung, BELUM ditutup
#   "Sempat running 16%"           -> pernah untung 16%, tidak menyatakan keluar
#   "Coyyy meledak ke bawah"       -> harga jatuh; untung kalau short, rugi kalau long
#   "Luber rugpull"                -> harga ambruk
#
# DIBEDAKAN DENGAN SENGAJA: "sedang untung" bukan "sudah ambil untung". Posisi
# yang sedang hijau masih bisa berbalik, jadi menghitungnya sebagai TP akan
# mengulang persis kesalahan yang membuat angka menang jadi optimistis.
RE_ID_AMBIL = re.compile(
    r"\b(?:amanin|amankan|di\s*aman(?:kan|in)|ambil\s+(?:untung|profit|cuan)"
    r"|closed?\s+cuan|tutup\s+(?:untung|cuan)|nyayur|sayur(?:an)?)\b", re.I)
RE_ID_JALAN = re.compile(
    r"\b(?:running|jalan|lagi\s+(?:untung|ijo|hijau)|cuan(?:nya)?|profit"
    r"|meledak|ledak|terbang|roket)\b", re.I)
RE_ID_RUGI = re.compile(
    r"\b(?:kena\s+(?:sl|stop)|cut\s*loss|cl(?:ose)?\s+rugi|rugi|nyangkut"
    r"|kejebak|ke\s*jebak|boncos|sl\s+kena)\b", re.I)

RE_TP_TELANJANG = re.compile(r"\btp\s?[1-4]\b", re.I)

# Penjaga: kalimat yang justru sedang MEMBUKA posisi baru.
#
# Tanpa ini, "Long ETH here, TP1 at 2000" akan salah dibaca sebagai pengakuan
# bahwa TP1 sudah kena — padahal itu rencana, bukan hasil. Penjaga ini hanya
# berlaku untuk TP telanjang; "TP1 hit" tetap dihitung walau ada kata "long",
# karena kata kerjanya sudah menyatakan hasil.
RE_BUKA_POSISI = re.compile(
    r"\b(?:going|go)\s+(?:long|short)\b|\b(?:long|short)ing\b"
    r"|\bmarket\s+(?:long|short)\b|\bat\s+cmp\b|\bscalp\s+(?:long|short)\b"
    r"|\bentry\b|\bdca\b|\blimit\s+(?:long|short)\b"
    r"|\b(?:long|short)\s+\w+\s+here\b", re.I)

# "TP1 at 2000" / "TP1 2000" menyebut HARGA target — itu rencana, bukan hasil.
# Yang sudah kena selalu ditulis dengan kata kerja ("TP1 hit at 2000"), dan itu
# tertangkap aturan eksplisit di atas sebelum sampai ke pemeriksaan ini.
RE_TP_RENCANA = re.compile(r"\btp\s?[1-4]\s*(?:at|@|:)?\s*\$?\d", re.I)


# Level dari teks, dibaca dengan pola tetap — bukan LLM, bukan OCR.
#
# Level TIDAK lagi ditampilkan sebagai kolom (chart TradingView di dashboard
# memperlihatkannya langsung), tetapi tetap dihitung karena dipakai menilai
# "target atau stop mana yang tersentuh lebih dulu" saat keduanya diketahui.
#
# Pola diambil dari kalimat sungguhan di channel:
#   "Market long INIT here at CMP. TPs above, 15min close under 0.052 for stops"
#   "Going long FARTCOIN here at CMP. TPs above, dca @ 0.1702, 4H close under 0.166"
#   "Full TP hit on ETH @ 1921 for 12R"
RE_STOP = re.compile(
    r"clos(?:e|ing|ed)?\s+(?:under|below|above|over)\s+\$?([\d]+(?:[.,]\d+)?)"
    r"|stops?\s+(?:at|@)\s*\$?([\d]+(?:[.,]\d+)?)"
    r"|sl\s*(?:at|@|:)?\s*\$?([\d]+(?:[.,]\d+)?)", re.I)
RE_TP_HARGA = re.compile(
    r"tp\s*\d*\s+(?:hit|smashed|reached|done)\s*(?:on\s+\w+\s*)?(?:@|at)\s*\$?([\d]+(?:[.,]\d+)?)"
    r"|tak(?:e|ing)\s+tp\s*\d*\s+(?:on\s+\w+\s+)?(?:here\s+)?(?:@|at)\s*\$?([\d]+(?:[.,]\d+)?)"
    r"|tps?\s*(?:at|@|:)\s*\$?([\d]+(?:[.,]\d+)?)", re.I)
RE_DCA = re.compile(r"dca\s*(?:@|at)\s*\$?([\d]+(?:[.,]\d+)?)", re.I)


def _angka(m):
    """Kelompok pertama yang terisi; koma desimal disamakan jadi titik."""
    if not m:
        return None
    for g in m.groups():
        if g:
            try:
                return float(g.replace(",", "."))
            except ValueError:
                return None
    return None


def level_dari_teks(teks):
    """{'stop': x, 'target': y, 'entry': z} sejauh yang benar-benar tertulis."""
    t = teks or ""
    return {"stop": _angka(RE_STOP.search(t)),
            "target": _angka(RE_TP_HARGA.search(t)),
            "entry": _angka(RE_DCA.search(t))}


# Nomor TP yang disebut: "TP1", "TP2", "TP3", "Full TP".
# Berguna karena TP1 dan TP3 sangat berbeda artinya — TP1 sering hanya sebagian
# kecil posisi, sedangkan Full TP berarti seluruhnya keluar di target.
RE_NOMOR_TP = re.compile(r"\bfull\s+tp\b|\btp\s?([1-4])\b|\btps?\b", re.I)


def nomor_tp(teks):
    t = teks or ""
    m = RE_NOMOR_TP.search(t)
    if not m:
        return None
    if m.group(0).lower().startswith("full"):
        return "Full TP"
    return ("TP" + m.group(1)) if m.group(1) else "TP"


def klaim_hasil(teks):
    t = teks or ""
    for pola, label in KLAIM:
        if pola.search(t):
            return label
    # TP telanjang dipakai hanya kalau kalimatnya bukan pembukaan posisi baru.
    if (RE_TP_TELANJANG.search(t) and not RE_BUKA_POSISI.search(t)
            and not RE_TP_RENCANA.search(t)):
        return "diaku TP kena"
    if RE_ID_RUGI.search(t):
        return "diaku kena stop"
    if RE_ID_AMBIL.search(t):
        return "diaku TP kena"
    if RE_ID_JALAN.search(t) and not RE_BUKA_POSISI.search(t):
        # Sengaja label tersendiri: sedang untung TIDAK sama dengan sudah keluar
        # di target, dan tidak dihitung sebagai menang.
        return "diaku sedang jalan"
    return None


# Kalimat yang MENGABARKAN posisi lama, bukan membuka posisi baru.
#
# Terukur: "I'm still holding my VVV long on Hyperliquid, and WOW what an
# insane move" masuk tabel sebagai panggilan VVV baru pada 18 Agustus, padahal
# panggilan aslinya dibuat 16 Agustus. Satu posisi tercatat dua kali, dan
# statistik analisnya ikut terhitung dua kali.
RE_MASIH_PEGANG = re.compile(
    r"still\s+(?:holding|long|short|in)|still\s+got"
    r"|holding\s+(?:my|the)|masih\s+(?:pegang|hold|jalan)", re.I)


def _klausa(teks):
    """Pecah pesan jadi klausa. Batasnya titik, baris baru, dan penghubung yang
    memang memisahkan dua pernyataan berbeda."""
    pisah = r"[.!?" + "\n" + r"]+|\s+(?:but|and|however|meanwhile)\s+"
    return [k for k in re.split(pisah, teks or "") if k.strip()]


def klaim_untuk_aset(teks, aset, semua_aset=None):
    """Pengakuan hasil yang benar-benar TENTANG aset ini.

    KENAPA TIDAK CUKUP MEMERIKSA SELURUH PESAN, terukur pada data sungguhan:

        "Got stopped on ENA overnight fam. Still long VVV as long as this 1H
         close holds"

    Pesan itu menyebut dua aset. Kalimat pertama mengabarkan ENA kena stop;
    kalimat kedua justru menyatakan posisi VVV MASIH DIPEGANG. Karena
    pemeriksaannya dulu berlaku atas seluruh teks, kata "stopped" ikut
    menempel ke VVV, dan tiga panggilan VVV sekaligus tercatat kena stop
    padahal analisnya baru saja bilang ia masih memegangnya.

    Jadi: kalau pesannya hanya menyebut SATU aset, seluruh teks boleh dipakai.
    Kalau menyebut lebih dari satu, kata pengakuannya harus berada di klausa
    yang sama dengan nama asetnya.
    """
    t = teks or ""
    aset = (aset or "").upper()
    if not aset:
        return None
    # Aset lain dikenali HANYA kalau ditulis huruf besar, dan harus berdiri
    # sebagai kata utuh.
    #
    # Sejumlah token bernama sama dengan kata Inggris biasa: NOT (Notcoin), ME,
    # UNI, SUN, ARC, LIT. Terukur akibatnya: "FARTCOIN not moving up with the
    # rest of the market... Closing it fully here at BE" dianggap menyebut dua
    # aset gara-gara kata "not", sehingga pengakuan "Closing it fully" dibuang
    # dan panggilan FARTCOIN tetap tercatat Open padahal sudah ditutup.
    #
    # Analis menulis ticker dengan huruf besar tanpa kecuali. Kalau suatu saat
    # ada yang menulis huruf kecil, akibatnya hanya kembali ke perilaku lama
    # yang lebih longgar, bukan salah label.
    lain = [a for a in (semua_aset or set())
            if a != aset and re.search(r"\b" + re.escape(a) + r"\b", t)]
    if not lain:
        return klaim_hasil(t)
    for k in _klausa(t):
        if re.search(r"" + re.escape(aset) + r"", k, re.I):
            h = klaim_hasil(k)
            if h:
                return h
    return None


def baca_channel(cid, sejak, guild=""):
    """Ambil pesan terbaru sampai melewati batas waktu.

    Discord memulangkan maksimal 100 pesan sekali panggil, terbaru lebih dulu,
    dan halaman berikutnya diambil lewat parameter `before`.
    """
    pesan, sebelum = [], None
    for _ in range(60):                      # atap 6.000 pesan per channel
        q = {"limit": 100}
        if sebelum:
            q["before"] = sebelum
        url = f"{API}/channels/{cid}/messages?" + urllib.parse.urlencode(q)
        batch = minta(url, {"Authorization": f"Bot {TOKEN}"})
        if not batch:
            break
        for m in batch:
            t = datetime.fromisoformat(m["timestamp"].replace("Z", "+00:00"))
            if t < sejak:
                return pesan
            isi = (m.get("content") or "").strip()
            # Embed sering memuat isi sebenarnya untuk pesan bot/webhook
            for e in (m.get("embeds") or []):
                bagian = [e.get("title"), e.get("description")]
                for f in (e.get("fields") or []):
                    bagian.append(f"{f.get('name')}: {f.get('value')}")
                isi = (isi + " " + " ".join(x for x in bagian if x)).strip()
            if not isi:
                continue
            # Lampiran (bukan embed) adalah cara Lynx mengirim kartu posisi Gate.io.
            # URL-nya disimpan supaya bisa dibaca belakangan kalau ada pembaca
            # gambar; tanpa disimpan, satu-satunya bukti hasil itu hilang.
            lampiran = [a.get("url") for a in (m.get("attachments") or [])
                        if (a.get("content_type") or "").startswith("image/")][:4]
            # Balasan Discord menautkan kabar hasil ke panggilan aslinya SECARA
            # PASTI — jauh lebih dapat dipercaya daripada menebak lewat "pesan
            # berikutnya yang menyebut aset yang sama". Terukur di channel Lynx:
            # 20 dari 50 pesan adalah balasan.
            ref = (m.get("message_reference") or {}).get("message_id")
            rujuk = m.get("referenced_message") or {}
            au = m.get("author") or {}
            # Tautan lompat Discord: /channels/{server}/{channel}/{pesan}.
            # Membukanya di aplikasi Discord langsung menyorot pesan aslinya,
            # jadi ringkasan apa pun bisa ditelusuri ke sumbernya.
            mid = str(m.get("id") or "")
            pesan.append({
                "waktu": t.isoformat(),
                "penulis": au.get("global_name") or au.get("username") or "?",
                # ID ikut disimpan karena nama pengguna bisa diganti kapan saja,
                # sementara ID tidak pernah berubah. Penyaring analis memakainya.
                "penulisId": str(au.get("id") or ""),
                "bot": bool(au.get("bot")),
                "teks": isi[:1200],
                "pesanId": mid,
                "kanalId": str(cid),
                "sumber": (f"https://discord.com/channels/{guild}/{cid}/{mid}"
                           if guild and mid else ""),
                # URL yang disebut di dalam pesan, dipisah supaya bisa jadi
                # tautan yang bisa diklik di dashboard.
                "tautan": RE_URL.findall(isi)[:6],
                "klaim": klaim_hasil(isi),
                "balasKe": str(ref) if ref else "",
                "balasTeks": ((rujuk.get("content") or "")[:300]) if rujuk else "",
                "gambar": lampiran,
                # Avatar Discord: hash-nya perlu disimpan karena URL-nya
                # dibentuk dari id pengguna + hash itu.
                "avatar": (f"https://cdn.discordapp.com/avatars/{au.get('id')}/"
                           f"{au.get('avatar')}.png?size=64"
                           if au.get("avatar") and au.get("id") else ""),
            })
        sebelum = batch[-1]["id"]
        if len(batch) < 100:
            break
        time.sleep(0.4)                      # Discord membatasi laju per rute
    return pesan


def ringkas(nama, pesan):
    """Minta LLM meringkas. Kalau tidak ada kunci, kembalikan None — panelnya
    tetap menampilkan pesan mentah, hanya tanpa ringkasan."""
    if not LLM_KEY or not pesan:
        return None
    # 4.000 karakter (~1.100 token). Ditambah max_tokens 1.500 hasilnya sekitar
    # 2.600 token per panggilan, sehingga empat panggilan masih muat dalam
    # anggaran 8.000 token per menit milik tier gratis Groq.
    # BUG YANG DIPERBAIKI: sebelumnya `reversed(pesan)` lalu dipotong [:4000].
    # `pesan` urut TERBARU dulu, jadi reversed() membuatnya TERLAMA dulu dan
    # pemotongan mengambil bagian paling tua. Dengan jendela enam bulan,
    # ringkasan Jaxx bertanggal "28 Feb - 7 Mar" padahal hari ini akhir Agustus.
    #
    # Sekarang: ambil dari yang TERBARU sampai anggaran karakter habis, baru
    # dibalik supaya urutan bacanya tetap kronologis (lama -> baru).
    ANGGARAN = 4000
    dipakai, n = [], 0
    for x in pesan:                       # pesan[0] adalah yang paling baru
        baris = f"[{x['waktu'][5:16]}] {x['penulis']}: {x['teks']}"
        if n + len(baris) > ANGGARAN and dipakai:
            break
        dipakai.append(baris)
        n += len(baris)
    teks = "\n".join(reversed(dipakai))
    prompt = (
        "Berikut kutipan obrolan TERBARU dari sebuah channel analis kripto, "
        "urut dari lama ke baru. Ringkas dalam bahasa Indonesia, maksimal 6 poin.\n\n"
        "Aturan yang mengikat:\n"
        "- Hanya tulis yang benar-benar ada di teks. Jangan menambah analisis "
        "sendiri, jangan menyimpulkan arah harga yang tidak mereka sebut.\n"
        "- Kalau ada angka (level harga, target, ukuran posisi), tulis persis.\n"
        "- Sebutkan siapa yang mengatakan apa kalau penulisnya berbeda-beda.\n"
        "- Kalau isinya obrolan ringan tanpa isi analitis, katakan begitu "
        "secara singkat dan jangan dipaksakan jadi enam poin.\n"
        "- JANGAN memakai tanda bintang, pagar, atau format Markdown apa pun. "
        "Tulis poin biasa yang diawali tanda hubung.\n\n"
        f"=== {nama} ===\n{teks}"
    )
    return llm_panggil(prompt, suhu=0.2)


# ===================== panggilan analis dan rantainya =====================
#
# Tiga lapis, dan pembagiannya disengaja:
#
#   1. LLM MENGEKSTRAK, tidak menyimpulkan. Ia hanya boleh mengeluarkan
#      panggilan yang benar-benar tertulis, dan wajib menyertakan kutipan
#      persisnya.
#   2. KUTIPAN DIVERIFIKASI di kode. Kalau kutipannya tidak ada di pesan asli,
#      panggilan itu dibuang. Ini yang mencegah model mengarang panggilan atau
#      salah menempelkan ke orang lain.
#   3. RANTAI DAN HASIL dihitung deterministik, bukan oleh model. Rantai dari
#      urutan waktu per aset; hasil dari harga Binance sungguhan.

SKEMA = """Keluarkan HANYA array JSON, tanpa penjelasan apa pun di luarnya.
Tiap elemen mewakili satu panggilan trading yang BENAR-BENAR tertulis:

{"penulis":"nama persis","aset":"TICKER","arah":"long|short|netral",
 "level":angka atau null,"target":angka atau null,"invalidasi":angka atau null,
 "waktu":"stempel waktu pesan itu","kutipan":"potongan kalimat PERSIS dari pesan"}

Aturan yang mengikat:
- "aset" adalah ticker apa pun yang disebut, apa adanya: BTC, ETH, SOL, HYPE,
  SWARMS, PIXEL, VVV, TUT, FARTCOIN, dan seterusnya. JANGAN menulis "lainnya"
  atau mengelompokkan; tulis tickernya sendiri tanpa tanda $.
- "kutipan" harus disalin huruf demi huruf dari pesan. Jangan diparafrase.
- Jangan mengarang level, target, atau arah yang tidak disebut. Isi null.
- Komentar umum tanpa level atau arah BUKAN panggilan. Lewati saja.
- Kalau tidak ada satu pun panggilan, keluarkan array kosong []."""


_llm_terakhir = 0.0
# Tier gratis Groq membatasi token per menit. Dengan ekstraksi berkelompok,
# satu analis bisa memicu lima panggilan atau lebih — terukur: dengan jeda 3
# detik sebagian kelompok hilang kena 429 dan hasilnya turun dari 9 panggilan
# jadi 2. Enam detik jauh lebih tahan.
JEDA_LLM = 6.0


_MODEL_MATI = {}

# Urutan pilihan kalau model yang diset ternyata sudah pensiun. Yang penalar
# lebih dulu karena ekstraksi panggilan menuntut ketelitian membaca, bukan
# kecepatan; whisper dan prompt-guard sengaja tidak masuk daftar.
PILIHAN = ["openai/gpt-oss-120b", "qwen/qwen3.8-27b", "qwen/qwen3.6-27b",
           "openai/gpt-oss-20b", "groq/compound"]


def _model_pengganti():
    try:
        d = minta(f"{LLM_BASE}/models", {"Authorization": f"Bearer {LLM_KEY}"})
        ada = {m.get("id") for m in (d.get("data") or [])}
    except Exception:                                        # noqa: BLE001
        return None
    for m in PILIHAN:
        if m in ada:
            print(f"\n  model '{LLM_MODEL}' sudah dipensiunkan penyedia; "
                  f"beralih ke '{m}'.")
            print(f"  Supaya menetap: setx LLM_MODEL \"{m}\"")
            return m
    return None


def llm_panggil(prompt, suhu=0.2, coba=4):
    """Satu pintu ke LLM, dengan jeda dan percobaan ulang saat kena 429.

    Tier gratis Groq membatasi TOKEN per menit, bukan hanya jumlah permintaan.
    Delapan panggilan beruntun dengan konteks 24.000 karakter melampauinya —
    terukur: tiga dari empat ringkasan gagal 429 tanpa penundaan. Header
    `retry-after` dari server dipatuhi kalau ada, bukan ditebak.
    """
    global _llm_terakhir, LLM_MODEL
    if not LLM_KEY:
        return None
    # Penyedia memensiunkan model tanpa memberi tahu, dan gejalanya menyesatkan:
    # setiap panggilan balas HTTP 404, ekstraksi jadi nol panggilan, dan
    # dashboard tampak "tidak menemukan apa-apa" padahal pesannya ada. Sudah dua
    # kali kejadian (llama-3.3-70b-versatile). Jadi sekali saja: tanya daftar
    # model yang benar-benar dilayani, pindah ke yang terdekat, lanjutkan.
    if _MODEL_MATI.get(LLM_MODEL):
        gan = _model_pengganti()
        if not gan:
            return None
        LLM_MODEL = gan

    # max_tokens harus cukup untuk model penalar, TETAPI tidak boleh besar.
    # Dua temuan yang saling bertarik, keduanya terukur:
    #
    #   1. Tanpa max_tokens sama sekali: finish_reason='length', reasoning
    #      9.178 karakter, content KOSONG — 3.070 dari 3.072 token bawaan habis
    #      di penalaran.
    #   2. Groq membatasi 8.000 token PER MENIT, dan max_tokens dihitung sebagai
    #      "Requested" terhadap kuota itu — bukan hanya token yang benar-benar
    #      terpakai. Pesan galatnya eksplisit: "Limit 8000, Used 4200,
    #      Requested 4296". Jadi max_tokens 8000 memesan seluruh anggaran
    #      semenit dalam satu panggilan.
    #
    # 1.500 adalah titik tengahnya: cukup untuk enam poin ringkasan atau satu
    # array JSON pendek, dan menyisakan ruang bagi empat panggilan per menit.
    isi_body = {"model": LLM_MODEL,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": suhu,
                "max_tokens": 1500}
    # reasoning_effort hanya dikenal keluarga gpt-oss; mengirimnya ke penyedia
    # lain berisiko 400, jadi dibatasi berdasarkan nama modelnya.
    if "gpt-oss" in LLM_MODEL:
        isi_body["reasoning_effort"] = "low"
    body = json.dumps(isi_body).encode()
    for i in range(coba):
        tunggu = JEDA_LLM - (time.time() - _llm_terakhir)
        if tunggu > 0:
            time.sleep(tunggu)
        try:
            r, sisa = minta_h(f"{LLM_BASE}/chat/completions",
                              {"Authorization": f"Bearer {LLM_KEY}"}, body, timeout=180)
            _llm_terakhir = time.time()
            # Anggaran per menit dibaca dari header servernya sendiri, bukan
            # ditebak. Kalau tinggal sedikit, tunggu sampai jendelanya berganti
            # daripada menabrak 429 lalu mengulang.
            if sisa is not None and sisa < 3000:
                print(f"\n      kuota menipis ({sisa} token), menunggu 35 detik...",
                      end="", flush=True)
                time.sleep(35)
                _llm_terakhir = time.time()
            m = r["choices"][0].get("message") or {}
            teks = (m.get("content") or "").strip()
            # Jaring pengaman: kalau content tetap kosong tetapi jawabannya
            # nyangkut di jejak penalaran, ambil dari sana daripada menyerah.
            if not teks and m.get("reasoning"):
                teks = str(m["reasoning"]).strip()
            return teks
        except urllib.error.HTTPError as e:
            if e.code == 404:
                _MODEL_MATI[LLM_MODEL] = True
                gan = _model_pengganti()
                if not gan:
                    return f"[model '{LLM_MODEL}' tidak dilayani penyedia]"
                LLM_MODEL = gan
                isi_body["model"] = gan
                if "gpt-oss" not in gan:
                    isi_body.pop("reasoning_effort", None)
                elif "reasoning_effort" not in isi_body:
                    isi_body["reasoning_effort"] = "low"
                body = json.dumps(isi_body).encode()
                continue
            _llm_terakhir = time.time()
            if e.code != 429 or i == coba - 1:
                return f"[ringkasan gagal: HTTP {e.code}]"
            jeda = 20.0
            try:
                jeda = float(e.headers.get("retry-after") or 20) + 1
            except (TypeError, ValueError):
                pass
            print(f"\n      429 dari LLM, menunggu {jeda:.0f} detik "
                  f"(coba {i + 2}/{coba})...", end="", flush=True)
            time.sleep(min(jeda, 70))
        except Exception as e:                               # noqa: BLE001
            _llm_terakhir = time.time()
            return f"[ringkasan gagal: {type(e).__name__}]"
    return "[ringkasan gagal: batas laju]"


POTONG = 1800          # karakter per kelompok


def ekstrak_calls(pesan):
    """Minta LLM menarik panggilan terstruktur, sekelompok kecil sekali jalan.

    Pesan DIPECAH, bukan dikirim sekaligus. Terukur pada openai/gpt-oss-120b:
    dengan masukan 6.500 karakter model hanya memakai 174 token penalaran lalu
    memulangkan array kosong — ia menyerah, bukan gagal. Dengan 2.000 karakter
    ia memakai 666 token dan benar-benar mengekstrak. Jadi ukuran kelompoklah
    yang menentukan, bukan batas token.
    """
    if not LLM_KEY or not pesan:
        return [], (1 if pesan else 0)

    kelompok, kini = [], []
    n = 0
    for p in reversed(pesan):                     # urut waktu naik
        baris = f'[{p["waktu"]}] {p["penulis"]}: {p["teks"]}'
        if n + len(baris) > POTONG and kini:
            kelompok.append("\n".join(kini))
            kini, n = [], 0
        kini.append(baris)
        n += len(baris)
    if kini:
        kelompok.append("\n".join(kini))

    semua, gagal = [], 0
    for i, blok in enumerate(kelompok, 1):
        isi = llm_panggil(SKEMA + "\n\n=== PESAN ===\n" + blok, suhu=0)
        if not isi or (isi.startswith("[model") and isi.endswith("]")):
            gagal += 1
            continue
        semua.extend(_urai_json(isi))
    # Dipulangkan bersama jumlah kegagalan supaya pemanggilnya bisa menahan diri
    # menandai pesan sebagai "sudah diekstrak". Tanpa ini, satu kali LLM tumbang
    # (mis. model dipensiunkan lalu balas 404) akan MENGUBUR pesan-pesan itu:
    # arsip mencatatnya selesai, hasilnya nol, dan tidak pernah dicoba lagi.
    return semua, gagal


def _urai_json(isi):
    """Ambil array JSON dari keluaran model, seberapa pun kotornya."""
    if isi.startswith("[ringkasan gagal"):
        return []
    # model kadang membungkus dengan pagar kode
    if "```" in isi:
        isi = isi.split("```")[1].lstrip("json").strip()
    a, b = isi.find("["), isi.rfind("]")
    if a < 0 or b < a:
        return []
    try:
        d = json.loads(isi[a:b + 1])
        return d if isinstance(d, list) else []
    except json.JSONDecodeError:
        return []


def normal(t):
    return " ".join((t or "").lower().split())


def verifikasi(calls, pesan):
    """Buang panggilan yang kutipannya tidak ada di pesan mana pun.

    Ini pagar terpenting di seluruh berkas: tanpa ini, satu halusinasi model
    akan tampil sebagai panggilan seorang analis yang tidak pernah ia buat.
    """
    korpus = [(normal(p["teks"]), p) for p in pesan]
    aset_batch = {(c.get("aset") or "").upper() for c in calls if c.get("aset")}
    sah, tolak = [], 0
    for c in calls:
        k = normal(c.get("kutipan"))
        if len(k) < 8:
            tolak += 1
            continue
        induk = next((p for teks, p in korpus if k in teks), None)
        if not induk:
            tolak += 1
            continue
        # Kabar posisi lama BUKAN panggilan baru.
        #
        # Terukur: "I'm still holding my VVV long on Hyperliquid, and WOW what
        # an insane move" masuk tabel sebagai panggilan VVV baru 18 Agustus,
        # padahal posisinya dibuka 16 Agustus. Satu posisi tercatat dua kali,
        # dan itu menggandakan bobotnya pada statistik analisnya.
        #
        # Syaratnya dua-duanya: kalimatnya mengabarkan posisi lama DAN tidak
        # ada tanda pembukaan posisi. "I'm longing VVV here at CMP again" tetap
        # lolos, karena "at CMP" menandainya sebagai pembukaan sungguhan.
        asli = induk.get("teks") or ""
        if RE_MASIH_PEGANG.search(asli) and not RE_BUKA_POSISI.search(asli):
            tolak += 1
            continue
        c["penulis"] = induk["penulis"]        # penulis diambil dari pesan asli
        c["waktu"] = induk["waktu"]            # begitu juga stempel waktunya
        c["sumber"] = induk.get("sumber") or ""   # tautan ke pesan aslinya
        c["kanal"] = induk.get("kanal") or ""
        c["tautan"] = induk.get("tautan") or []
        # Klaim diambil dengan pengikatan aset, bukan label seluruh pesan.
        # Tanpa ini "Got stopped on ENA... Still long VVV" memberi label
        # "kena stop" kepada panggilan VVV yang kebetulan ikut disebut.
        c["klaim"] = klaim_untuk_aset(induk.get("teks"), c.get("aset"), aset_batch)
        for f in ("level", "target", "invalidasi"):
            try:
                c[f] = float(c[f]) if c.get(f) is not None else None
            except (TypeError, ValueError):
                c[f] = None
        sah.append(c)
    return sah, tolak


# Kalimat pembuka panggilan yang bentuknya tetap. Sengaja sempit: hanya frasa
# yang memang dipakai analis untuk MEMBUKA posisi, bukan membicarakannya.
POLA_CALL = re.compile(
    r"(?<![A-Za-z])"
    r"(long|longing|longed|short|shorting|shorted|buying)"
    r"(?:\s+some)?(?:\s+spot)?\s+\$?"
    r"([A-Za-z][A-Za-z0-9]{1,9})(?![A-Za-z0-9])",
    re.I)
# Kata yang bentuknya seperti ticker tetapi bukan. Tanpa ini "long here" jadi
# panggilan aset "HERE".
BUKAN_ASET = {"HERE", "THIS", "THAT", "NOW", "AT", "CMP", "IT", "THE", "MORE",
              "AGAIN", "SOME", "SPOT", "BACK", "IN", "INTO", "ON", "UP", "DOWN",
              "TP", "SL", "BE", "DCA", "R", "AND", "WITH", "FOR", "FROM"}


def calls_dari_pola(pesan, sudah_ada):
    """Jaring pengaman deterministik untuk panggilan yang LLM lewatkan.

    KENAPA PERLU, terukur: tiga panggilan Neil yang kalimatnya sangat jelas
    ("Market long INIT here at CMP", "Buying some spot UNI here at CMP",
    "Im going long ETH here at CMP") tidak pernah masuk tabel. Diuji ulang satu
    per satu, model menemukan dua dari tiga; digabung dalam kelompok lain ia
    menemukan ketiganya. Jadi hasilnya bergantung pada pengelompokan, dan itu
    berarti panggilan mana pun bisa hilang kapan saja tanpa ada yang tahu.

    Jaring ini tidak bisa berhalusinasi: asetnya harus muncul persis di teks,
    harus dikenal Binance, dan kutipannya diambil dari pesan aslinya. Ia hanya
    MENAMBAH yang belum ada, tidak pernah menimpa hasil LLM yang lebih kaya.

    Dijalankan atas SELURUH pesan dalam jendela, bukan hanya yang baru. Itu
    sekaligus memulihkan pesan yang terlanjur tertandai selesai pada run lama
    yang gagal, yang kalau tidak begitu akan terkubur selamanya.
    """
    simbol = simbol_binance()
    out = []
    for p in pesan:
        if p.get("pesanId") in sudah_ada:
            continue
        teks = p.get("teks") or ""
        # Pagar yang sama seperti di verifikasi(): "Still long VVV as long as
        # this 15min 200 holds" cocok dengan pola pembuka, padahal itu kabar
        # posisi lama. Tanpa ini jaring pengaman justru menyuntikkan panggilan
        # hantu yang baru saja dibuang di tempat lain.
        if RE_MASIH_PEGANG.search(teks) and not RE_BUKA_POSISI.search(teks):
            continue
        m = POLA_CALL.search(teks)
        if not m:
            continue
        arah_kata, aset = m.group(1).lower(), m.group(2).upper()
        if aset in BUKAN_ASET or not pasangan(aset):
            continue
        lt = level_dari_teks(teks)
        out.append({
            "aset": aset,
            "arah": "short" if arah_kata.startswith("short") else "long",
            "level": lt["entry"], "target": lt["target"], "invalidasi": lt["stop"],
            "kutipan": teks[:200],
            "penulis": p["penulis"], "waktu": p["waktu"],
            "sumber": p.get("sumber") or "", "kanal": p.get("kanal") or "",
            "tautan": p.get("tautan") or [], "klaim": p.get("klaim"),
            "dariPola": True,
        })
    return out


def rantai(calls):
    """Sambungkan panggilan berurutan per penulis dan aset.

    Deterministik dari urutan waktu, bukan dari penilaian model — supaya
    rantainya bisa ditelusuri sendiri.
    """
    grup = {}
    for c in sorted(calls, key=lambda x: x.get("waktu") or ""):
        kunci = (c.get("penulis") or "?", (c.get("aset") or "?").upper())
        grup.setdefault(kunci, []).append(c)
    out = []
    for (penulis, aset), isi in grup.items():
        out.append({"penulis": penulis, "aset": aset, "n": len(isi), "calls": isi})
    out.sort(key=lambda g: (-g["n"], g["penulis"]))
    return out


# Daftar simbol Binance ditarik sekali, bukan ditanam.
#
# Versi pertama hanya mengenal BTC/ETH/SOL/HYPE, dan akibatnya panggilan $SUI
# yang punya target 0,7677 serta invalidasi 0,67 lewat begitu saja tanpa dinilai
# — analis memanggil koin apa saja, bukan hanya empat yang kebetulan ada di
# dashboard. Sekarang aset apa pun yang diperdagangkan di Binance ikut dinilai.
_simbol_cache = None


def simbol_binance():
    """Simbol spot DAN futures.

    Sebelumnya hanya spot, dan itu membuang banyak panggilan tanpa alasan:
    HYPE, FARTCOIN, TON, GRASS, SWARMS, VVV, dan LIT semuanya diperdagangkan di
    Binance futures tetapi tidak di spot. Dari 72 panggilan yang dulu tercatat
    "tidak ada di Binance", sebagian besar sebenarnya ada.
    """
    global _simbol_cache
    if _simbol_cache is None:
        _simbol_cache = {}
        try:
            d = minta("https://api.binance.com/api/v3/exchangeInfo?permissions=SPOT")
            for x in d.get("symbols", []):
                if x.get("status") == "TRADING":
                    _simbol_cache[x["symbol"]] = "spot"
        except Exception:                                    # noqa: BLE001
            pass
        try:
            d = minta("https://fapi.binance.com/fapi/v1/exchangeInfo")
            for x in d.get("symbols", []):
                if x.get("status") == "TRADING" and x["symbol"] not in _simbol_cache:
                    _simbol_cache[x["symbol"]] = "futures"
        except Exception:                                    # noqa: BLE001
            pass
    return _simbol_cache


# Nama yang ditulis analis tidak selalu sama dengan tiker bursanya.
ALIAS = {"SOLANA": "SOL", "BITCOIN": "BTC", "ETHEREUM": "ETH", "ETHER": "ETH",
         "RIPPLE": "XRP", "DOGECOIN": "DOGE", "PUMPFUN": "PUMP"}


def pasangan(aset):
    """Pasangan USDT untuk sebuah aset; None kalau memang tidak diperdagangkan."""
    a = (aset or "").upper().lstrip("$").strip()
    # LLM kadang sudah menyertakan pasangannya di nama aset ("AKEUSDT"), yang
    # kalau dibiarkan jadi "AKEUSDTUSDT" dan tidak pernah ketemu.
    for akhiran in ("USDT", "USDC", "PERP", "/USDT"):
        if len(a) > len(akhiran) and a.endswith(akhiran):
            a = a[:-len(akhiran)]
            break
    a = ALIAS.get(a, a)
    if not a:
        return None
    ada = simbol_binance()
    for kandidat in (a + "USDT", "1000" + a + "USDT", a + "USDC"):
        if kandidat in ada:
            return kandidat
    return None


def klines(sym, sejak_ms):
    url = ("https://api.binance.com/api/v3/klines?symbol=" + sym +
           "&interval=1h&limit=500&startTime=" + str(sejak_ms))
    try:
        return minta(url)
    except Exception:                                        # noqa: BLE001
        return []


HORIZON_HARI = 7

# Dashboard menampilkan enam bulan; arsip diberi sedikit kelebihan supaya
# baris di tepi rentang tidak hilang lebih dulu daripada yang menampilkannya.
RETENSI_HARI = 200
BAR_PER_HARI = 6                    # lilin 4 jam

# Batas jarak pengakuan dari panggilannya, untuk keperluan menghitung imbal.
#
# Pengakuan dicari pada pesan BERIKUTNYA dari orang yang sama yang menyebut aset
# itu. Untuk aset yang dipanggil berulang kali, cara itu bisa memasangkan
# pengakuan ke panggilan yang keliru. Terukur pada data sungguhan: median jarak
# 2,6 hari, tetapi ekornya sampai 160 hari, dan pada jarak seperti itu
# pasangannya praktis tidak mungkin benar. Di luar batas ini, imbal kembali
# memakai horizon tetap, bukan menebak.
MAKS_KLAIM_HARI = 30


def seri_harian(sym, sejak_ms):
    """Lilin 4 jam sepanjang jendela, diambil bertahap.

    Sengaja 4 jam, bukan harian. Dengan lilin harian, harga masuk sebuah
    panggilan pukul 17:00 baru terbaca pada pembukaan HARI BERIKUTNYA — meleset
    sampai 24 jam dari saat panggilan dibuat, dan untuk aset yang bergerak cepat
    itu cukup untuk membalik untung jadi rugi. Empat jam memperkecil meleset itu
    jadi paling lama 4 jam.

    Binance memulangkan maksimal 500 lilin sekali panggil; 6 bulan pada 4 jam
    butuh sekitar 1.080, jadi diambil tiga tahap.
    """
    # Simbol futures harus ditarik dari fapi; api.binance.com tidak mengenalnya.
    pangkal = ("https://fapi.binance.com/fapi/v1/klines"
               if simbol_binance().get(sym) == "futures"
               else "https://api.binance.com/api/v3/klines")
    keluar, mulai = [], sejak_ms
    for _ in range(4):
        url = (pangkal + "?symbol=" + sym +
               "&interval=4h&limit=500&startTime=" + str(mulai))
        try:
            batch = minta(url)
        except Exception:                                    # noqa: BLE001
            break
        if not batch:
            break
        keluar.extend(batch)
        if len(batch) < 500:
            break
        mulai = int(batch[-1][0]) + 1
    return keluar


def nilai_harga(baris, sejak_ms):
    """Isi hasil tiap panggilan dari harga sungguhan.

    KENAPA BUKAN SEKADAR TARGET-vs-STOP: hanya 4% panggilan menyebut entry dan
    7% menyebut target, jadi aturan "mana tersentuh lebih dulu" hanya bisa
    dipakai untuk segelintir. Untuk sisanya dipakai imbal hasil ke depan dari
    harga saat pesan ditulis — ukuran yang bisa dihitung untuk SEMUA panggilan
    dan menjawab pertanyaan sebenarnya: kalau diikuti, untung atau rugi?

    Arah diperhitungkan: short yang harganya turun dihitung menang.
    """
    per_aset = {}
    for r in baris:
        if r.get("aset"):
            per_aset.setdefault(r["aset"].upper(), []).append(r)

    # Seluruh deret harga ditarik LEBIH DULU dan BERSAMAAN.
    #
    # Terukur satu per satu: 0,8 sampai 4,8 detik per aset, dan ada 84 aset.
    # Berurutan itu dua sampai tiga menit hanya untuk menunggu jaringan, dan
    # itu bagian terbesar dari seluruh waktu penarikan. Pekerjaannya murni
    # baca, tidak ada yang saling menimpa, jadi menunggunya bisa ditumpuk.
    #
    # Enam pekerja, bukan lebih: Binance membatasi per bobot permintaan, dan
    # tiap aset memerlukan beberapa halaman. Angka ini memberi percepatan
    # terbesar tanpa mendekati batas itu.
    simbol_per_aset = {a: pasangan(a) for a in per_aset}
    perlu = sorted({s for s in simbol_per_aset.values() if s})
    print(f"menarik harga {len(perlu)} aset secara bersamaan...")
    t_harga = time.time()
    seri_per_simbol = {}

    def _tarik(sym):
        try:
            return sym, seri_harian(sym, sejak_ms)
        except Exception:                                    # noqa: BLE001
            return sym, None

    with cf.ThreadPoolExecutor(max_workers=6) as pool:
        for sym, k in pool.map(_tarik, perlu):
            seri_per_simbol[sym] = k
    print(f"  selesai dalam {time.time() - t_harga:.0f} detik")

    ok = gagal = 0
    for i, (aset, daftar) in enumerate(sorted(per_aset.items()), 1):
        sym = simbol_per_aset.get(aset)
        # Pasangan sesungguhnya dan bursanya ikut disimpan. Dashboard tidak bisa
        # menebaknya sendiri: nama aset "HYPE" jadi HYPEUSDT yang hanya ada di
        # FUTURES, dan TradingView menamai perpetual Binance dengan akhiran .P.
        # Tanpa ini chart-nya menampilkan "Simbol ini tidak tersedia".
        for r in daftar:
            r["pair"] = sym
            r["bursa"] = simbol_binance().get(sym) if sym else None
        if not sym:
            for r in daftar:
                r["hasil"] = "tidak ada di Binance"
            gagal += 1
            continue
        k = seri_per_simbol.get(sym)
        if not k:
            for r in daftar:
                r["hasil"] = "harga tidak terambil"
            gagal += 1
            continue
        # [waktu buka, open, high, low, close, ...]
        seri = [(int(x[0]), float(x[1]), float(x[2]), float(x[3]), float(x[4])) for x in k]
        for r in daftar:
            try:
                t = datetime.fromisoformat(r["waktu"]).timestamp() * 1000
            except Exception:                                # noqa: BLE001
                continue
            mulai = next((n for n, b in enumerate(seri) if b[0] >= t), None)
            if mulai is None or mulai >= len(seri) - 1:
                r["hasil"] = "terlalu baru untuk dinilai"
                continue
            masuk = seri[mulai][1]                # open lilin pertama sesudahnya
            jendela = seri[mulai:mulai + HORIZON_HARI * BAR_PER_HARI + 1]
            naik = (max(b[2] for b in jendela) / masuk - 1) * 100
            turun = (min(b[3] for b in jendela) / masuk - 1) * 100
            akhir = (jendela[-1][4] / masuk - 1) * 100
            pendek = (r.get("arah") or "long").lower() == "short"
            r["masuk"] = round(masuk, 8)
            r["imbal"] = round(-akhir if pendek else akhir, 2)

            # IMBAL BERHENTI DI JAM PENGAKUAN, bukan di ujung jendela 7 hari.
            #
            # Terukur sebelum ini ada: 56 dari 219 baris (26%) menampilkan
            # kombinasi yang terbaca sebagai salah hitung, misalnya "SL, rugi,
            # +42,20%". Keduanya benar tetapi menjawab pertanyaan berbeda.
            # Status SL berasal dari pengakuan analis, sedangkan imbal 7 hari
            # mengandaikan posisinya TIDAK pernah ditutup. Untuk VVV itu berarti
            # analisnya kena stop, lalu koinnya naik 42% dalam sisa pekan.
            #
            # Yang dijanjikan kolom Imbal kepada pembaca adalah hasil kalau
            # panggilan itu diikuti, jadi ia harus berhenti di tempat analisnya
            # berhenti. Ini penalaran yang sama yang sudah dipakai untuk kartu
            # posisi; di sini tinggal diperluas ke pengakuan bertanggal.
            #
            # Jendelanya berakhir di jam pengakuan KALAU jam itu tersimpan, dan
            # di ujung horizon 7 hari kalau tidak. Aturan ekstremnya sama di
            # kedua hal, supaya satu panggilan tidak dinilai dengan cara berbeda
            # hanya karena stempel waktunya kebetulan hilang di arsip lama.
            kw = r.get("klaimWaktu")
            adaKlaim = bool((r.get("klaim") or "").strip())
            if adaKlaim:
                tk = None
                if kw:
                    try:
                        tk = datetime.fromisoformat(kw).timestamp() * 1000
                    except Exception:                        # noqa: BLE001
                        tk = None
                    if not (t < tk <= t + MAKS_KLAIM_HARI * 86400_000):
                        tk = None
                if True:
                    # Diukur dari SELURUH deret sejak masuk, bukan dari jendela
                    # 7 hari: pengakuan yang datang di hari ke-10 kalau dipotong
                    # ke ujung jendela menghasilkan angka horizon lagi, dan
                    # kontradiksinya tetap ada. Terukur: 63% pengakuan datang
                    # dalam 7 hari, sisanya sesudahnya.
                    if tk:
                        lanjut = seri[mulai:mulai + MAKS_KLAIM_HARI * BAR_PER_HARI + 1]
                        sampai = [b for b in lanjut if b[0] <= tk] or lanjut[:1]
                    else:
                        sampai = jendela          # tanpa stempel: horizon penuh

                    # HARGA KELUAR MEMAKAI EKSTREM YANG MENGUNTUNGKAN, BUKAN
                    # PENUTUPAN. Ini pilihan sadar, dan condong ke analisnya.
                    #
                    # Alasannya nyata: TP1 hampir selalu keluar sebagian di
                    # lonjakan intraday, dan lilin 4 jam tidak menyimpan lonjakan
                    # itu di harga penutupannya. Terukur, INJ diaku TP dalam 0,3
                    # hari tetapi penutupan lilinnya -5,23%; tertinggi lilin yang
                    # sama menyentuh targetnya. Memakai penutupan berarti
                    # menghukum analis untuk sesuatu yang memang ia hindari.
                    #
                    # Sisi condongnya tetap harus dikatakan, dan dikatakan di
                    # tooltip: ini mengandaikan eksekusi pada harga TERBAIK yang
                    # tersedia di lilin pengakuan. Trader sungguhan jarang
                    # mendapat harga itu. Karena itu penutupan tetap disimpan
                    # sebagai imbalTutup, supaya versi konservatifnya tidak
                    # hilang dan bisa dibandingkan kapan saja.
                    tutup = (sampai[-1][4] / masuk - 1) * 100
                    naik_k = max(b[2] for b in sampai)      # tertinggi periode
                    turun_k = min(b[3] for b in sampai)     # terendah periode

                    # Ekstrem dipilih menurut JENIS pengakuan, karena begitulah
                    # order sungguhan terisi: take profit terpicu oleh harga
                    # tertinggi, stop terpicu oleh harga terendah. Bukan oleh
                    # harga penutupan, dan bukan hanya di lilin pengumumannya.
                    #
                    # Jam pengakuan adalah jam ANALIS MENGUMUMKAN, bukan jam
                    # ordernya terisi. Terukur: INJ diaku TP 0,3 hari sesudah
                    # masuk dengan ekstrem lilin pengumuman -0,24%, padahal
                    # tertinggi sepanjang periode itu +12,99%. Memakai lilin
                    # pengumuman saja berarti melewatkan momen TP-nya sendiri.
                    k = (r.get("klaim") or "").lower()
                    if "tp" in k or "target" in k:
                        ref = naik_k if not pendek else turun_k
                    elif "stop" in k or "sl" in k:
                        ref = turun_k if not pendek else naik_k
                    else:
                        ref = sampai[-1][4]        # BE atau ditutup: penutupan
                    baik = (ref / masuk - 1) * 100
                    r["imbal7h"] = r["imbal"]       # pembanding, untuk tooltip
                    r["imbalTutup"] = round(-tutup if pendek else tutup, 2)
                    r["imbal"] = round(-baik if pendek else baik, 2)
                    r["imbalSampai"] = kw if tk else None
                    r["imbalDasar"] = "klaim" if tk else "horizon"
                    r["hariDinilaiKlaim"] = round(len(sampai) / BAR_PER_HARI, 1)
            r["terbaik"] = round(-turun if pendek else naik, 2)
            r["terburuk"] = round(-naik if pendek else turun, 2)
            r["hariDinilai"] = round((len(jendela) - 1) / BAR_PER_HARI, 1)

            # Kalau target dan stop memang disebut, mana yang tersentuh lebih
            # dulu tetap lebih bermakna daripada imbal hasil mentah.
            tgt, stp = r.get("target"), r.get("stop")
            if tgt and stp:
                kena = None
                for b in jendela:
                    if not pendek:
                        if b[3] <= stp:
                            kena = "invalidasi tersentuh"
                            break
                        if b[2] >= tgt:
                            kena = "target tersentuh"
                            break
                    else:
                        if b[2] >= stp:
                            kena = "invalidasi tersentuh"
                            break
                        if b[3] <= tgt:
                            kena = "target tersentuh"
                            break
                r["hasil"] = kena or "belum tersentuh"
            else:
                r["hasil"] = "untung" if r["imbal"] > 0 else "rugi" if r["imbal"] < 0 else "datar"
            ok += 1
        print(f"\r  menilai {i}/{len(per_aset)} aset...", end="", flush=True)
    print(f"\r  {ok} panggilan dinilai dari harga, {gagal} aset tanpa data     ")


def klaim_lanjutan(grup, pesan_per_orang):
    """Cari pengakuan hasil di pesan SESUDAH panggilan dibuat.

    Analis mengumumkan hasilnya di pesan terpisah — "TP1 hit on PIXEL" datang
    jam-jam setelah "going long PIXEL". Jadi klaim dicari pada pesan berikutnya
    dari orang yang sama yang menyebut aset itu.
    """
    # Satu pesan pengakuan hanya boleh menutup SATU panggilan.
    #
    # Terukur: pesan "Got stopped on ENA... Still long VVV" dipakai sebagai
    # pengakuan untuk TIGA panggilan VVV sekaligus. Di dunia nyata satu
    # pengumuman menutup satu posisi, jadi sesudah dipakai ia dicoret.
    dipakai = set()
    # Daftar aset yang dikenal, dipakai untuk mendeteksi pesan yang menyebut
    # LEBIH DARI SATU aset. Diambil dari panggilan yang ada, bukan dari daftar
    # Binance penuh, supaya kata umum seperti "ID" atau "ME" tidak dihitung
    # sebagai aset kedua hanya karena kebetulan ada simbolnya.
    SEMUA_ASET = {(g["aset"] or "").upper() for g in grup if g.get("aset")}
    # Panggilan diurut dari yang TERBARU. Kalau ada beberapa posisi terbuka di
    # aset yang sama, pengumuman menutup yang paling akhir dibuka, bukan yang
    # paling lama menganggur.
    for g in grup:
        pesan = pesan_per_orang.get(g["penulis"]) or []
        aset = (g["aset"] or "").upper()
        for c in sorted(g["calls"], key=lambda x: x.get("waktu") or "", reverse=True):
            # "sedang jalan" adalah label SEMENTARA — aturan balasan di bawah
            # bisa menaikkannya jadi TP. Kalau dilewati seperti klaim lain,
            # panggilan lama dari arsip tidak akan pernah dinilai ulang.
            # Klaim dari arsip DIVALIDASI ULANG, tidak dipercaya begitu saja.
            # Arsip menyimpan hasil aturan versi lama, dan aturan yang salah
            # akan hidup selamanya kalau yang lama tidak pernah diperiksa.
            # Yang gugur dikosongkan supaya dicarikan pasangan yang benar.
            if c.get("klaim") and c.get("klaimTeks"):
                if not klaim_untuk_aset(c["klaimTeks"], aset, SEMUA_ASET):
                    for f_ in ("klaim", "klaimSumber", "klaimWaktu", "klaimTeks",
                               "tpKe", "dasarTP"):
                        c.pop(f_, None)
            if c.get("klaim") and c["klaim"] != "diaku sedang jalan":
                continue
            t0 = c.get("waktu") or ""
            # ID pesan asal panggilan ini, dibaca dari tautan sumbernya.
            asal = (c.get("sumber") or "").rsplit("/", 1)[-1]
            for p in sorted(pesan, key=lambda x: x["waktu"]):
                if p["waktu"] <= t0:
                    continue
                # Balasan langsung ke panggilan ini selalu diterima, walau
                # nama asetnya tidak diulang di teks balasannya — dan memang
                # sering tidak diulang ("Bahh", "Nyayur", "Lumayan uda running").
                balasan_ke_ini = asal and p.get("balasKe") == asal
                if not balasan_ke_ini and aset and aset not in (p.get("teks") or "").upper():
                    continue
                if p.get("pesanId") in dipakai:
                    continue
                # Klaim dinilai ULANG di sini terhadap aset panggilan ini,
                # bukan diambil dari label seluruh pesan. Alasannya ada di
                # klaim_untuk_aset().
                k = (p.get("klaim") if balasan_ke_ini
                     else klaim_untuk_aset(p.get("teks"), aset, SEMUA_ASET))
                if balasan_ke_ini and not k:
                    # Ada kabar, tetapi kalimatnya tidak menyatakan hasil.
                    # Dicatat apa adanya, TIDAK ditebak jadi menang atau kalah.
                    c.setdefault("kabar", []).append({
                        "waktu": p["waktu"], "teks": (p.get("teks") or "")[:160],
                        "sumber": p.get("sumber") or "", "gambar": p.get("gambar") or []})
                    continue
                # BALASAN ke panggilan sendiri diperlakukan berbeda dari pesan
                # biasa. Lynx tidak pernah menulis "TP hit"; cara dia
                # mengumumkan hasil adalah MEMBALAS panggilannya sendiri dengan
                # kartu posisi hijau dan satu kata seperti "Running" atau
                # "Nyayur". Dalam konteks itu, balasan yang menunjukkan untung
                # memang pengumuman kemenangan, bukan sekadar kabar.
                #
                # Ini melonggarkan aturan sebelumnya, dan konsekuensinya
                # disebut apa adanya: posisi yang masih berjalan bisa berbalik,
                # jadi angka menang di sini lebih longgar daripada "keluar di
                # target". Kolom harga tetap ada untuk memeriksanya.
                if balasan_ke_ini and k == "diaku sedang jalan":
                    k = "diaku TP kena"
                    c["dasarTP"] = "balasan menunjukkan untung"
                if k:
                    dipakai.add(p.get("pesanId"))
                    c["klaim"] = k
                    c["klaimSumber"] = p.get("sumber") or ""
                    c["klaimWaktu"] = p["waktu"]
                    c["klaimTeks"] = (p.get("teks") or "")[:200]
                    if k == "diaku TP kena":
                        c["tpKe"] = nomor_tp(p.get("teks"))
                    # Pesan pengakuan sering memuat harga keluarnya:
                    # "Full TP hit on ETH @ 1921". Itu target sungguhan.
                    lt = level_dari_teks(p.get("teks"))
                    if lt["target"] and c.get("target") is None:
                        c["target"] = lt["target"]
                    break


def nilai_hasil(grup):
    """Apakah panggilannya terbukti? Aturannya sederhana dan bisa diperiksa:
    setelah panggilan dibuat, mana yang tersentuh lebih dulu — target atau
    invalidasi. Kalau belum ada yang tersentuh, statusnya masih berjalan."""
    cache = {}
    for g in grup:
        sym = pasangan(g["aset"])
        if not sym:
            # Tetap dicatat alasannya, supaya kolom hasil yang kosong di
            # dashboard tidak terlihat seperti kegagalan tanpa sebab.
            for c in g["calls"]:
                if c.get("target") is not None or c.get("invalidasi") is not None:
                    c["hasil"] = "tidak diperdagangkan di Binance"
            continue
        for c in g["calls"]:
            tgt, inv = c.get("target"), c.get("invalidasi")
            if tgt is None and inv is None:
                continue
            try:
                mulai = int(datetime.fromisoformat(c["waktu"]).timestamp() * 1000)
            except Exception:                                # noqa: BLE001
                continue
            kunci = (sym, mulai // 3600000)
            if kunci not in cache:
                cache[kunci] = klines(sym, mulai)
                time.sleep(0.25)
            bar = cache[kunci]
            kena_t = kena_i = None
            for b in bar:
                hi, lo = float(b[2]), float(b[3])
                if tgt is not None and kena_t is None and lo <= tgt <= hi:
                    kena_t = b[0]
                if inv is not None and kena_i is None and lo <= inv <= hi:
                    kena_i = b[0]
                if kena_t or kena_i:
                    break
            # Nol bar berarti belum ada harga setelah panggilan itu — misalnya
            # stempel waktunya di masa depan atau simbolnya baru terdaftar.
            # Melaporkannya sebagai "masih berjalan" akan menyiratkan kita sudah
            # memeriksa dan belum ada yang tersentuh, padahal tidak memeriksa
            # apa pun.
            if not bar:
                c["hasil"] = "belum bisa dinilai"
            elif kena_t and (not kena_i or kena_t <= kena_i):
                c["hasil"] = "target tersentuh"
            elif kena_i:
                c["hasil"] = "invalidasi tersentuh"
            else:
                c["hasil"] = "masih berjalan"
            c["barDiperiksa"] = len(bar)


def periksa():
    """`--cek`: pastikan token sah dan tiap channel benar-benar terbaca.

    Dijalankan sebelum penarikan sungguhan supaya kegagalan izin ketahuan di
    langkah pemasangan, bukan setelah menunggu ratusan pesan.
    """
    print("1. Token")
    if not TOKEN:
        print("   BELUM ADA. setx DISCORD_BOT_TOKEN \"...\" lalu buka terminal baru.")
        return 1
    try:
        me = minta(f"{API}/users/@me", {"Authorization": f"Bot {TOKEN}"})
        print(f"   OK — bot bernama {me.get('username')} (id {me.get('id')})")
    except urllib.error.HTTPError as e:
        print(f"   DITOLAK (HTTP {e.code}). Token salah atau sudah di-reset.")
        return 1

    print("\n2. Server yang sudah mengundang bot ini")
    try:
        guild = minta(f"{API}/users/@me/guilds", {"Authorization": f"Bot {TOKEN}"})
        if not guild:
            print("   BELUM ADA. Bot belum diundang ke server mana pun.")
        for g in guild:
            print(f"   - {g.get('name')} (id {g.get('id')})")
    except urllib.error.HTTPError as e:
        print(f"   gagal dibaca (HTTP {e.code})")

    print("\n3. Channel di discord_channels.json")
    if not KONFIG.exists():
        contoh_konfig()
        print(f"   {KONFIG.name} baru dibuat — isi channel ID-nya dulu.")
        return 1
    cfg = json.loads(KONFIG.read_text(encoding="utf-8"))
    daftar = [c for c in cfg.get("channels", [])
              if str(c.get("id", "")).isdigit() and not str(c["id"]).startswith("00000")]
    if not daftar:
        print("   Belum ada channel ID yang sah.")
        return 1

    kosong_isi = 0
    for c in daftar:
        nama, cid = c.get("nama") or c["id"], str(c["id"])
        try:
            pesan = minta(f"{API}/channels/{cid}/messages?limit=5",
                          {"Authorization": f"Bot {TOKEN}"})
        except urllib.error.HTTPError as e:
            sebab = {403: "bot tidak punya izin View Channel / Read Message History",
                     404: "channel tidak ada, atau bot bukan anggota servernya"
                     }.get(e.code, f"HTTP {e.code}")
            print(f"   {nama:26} GAGAL — {sebab}")
            continue
        berisi = sum(1 for m in pesan if (m.get("content") or "").strip())
        if not pesan:
            # Discord memulangkan daftar kosong berstatus 200 — bukan 403 —
            # kalau Read Message History tidak diizinkan. Melaporkannya "OK"
            # justru menyembunyikan masalah yang sedang dicari.
            print(f"   {nama:26} 0 pesan — kemungkinan besar Read Message History")
            print(f"   {'':26} belum dicentang HIJAU (netral tidak cukup, karena")
            print(f"   {'':26} @everyone menolaknya di tingkat channel).")
        elif berisi == 0:
            kosong_isi += 1
            print(f"   {nama:26} terbaca {len(pesan)} pesan tapi SEMUA ISINYA KOSONG")
        else:
            print(f"   {nama:26} OK — {len(pesan)} pesan, {berisi} berisi teks")
        # Penulis beserta ID-nya dicetak supaya tinggal disalin ke daftar analis.
        siapa = {}
        for m in pesan:
            a = m.get("author") or {}
            nm = a.get("global_name") or a.get("username") or "?"
            siapa[str(a.get("id"))] = nm + (" [bot]" if a.get("bot") else "")
        for uid, nm in siapa.items():
            print(f"        penulis: {nm:22} id {uid}")
        time.sleep(0.3)

    if kosong_isi:
        print("\n   >> MESSAGE CONTENT INTENT kemungkinan besar belum dinyalakan.")
        print("      Developer Portal > aplikasi Anda > Bot > Privileged Gateway")
        print("      Intents > MESSAGE CONTENT INTENT > Save, lalu ulangi --cek.")

    print("\n4. Kunci peringkas (opsional)")
    print(f"   {'ADA' if LLM_KEY else 'tidak ada'} — model {LLM_MODEL}, endpoint {LLM_BASE}")
    if not LLM_KEY:
        print("   Tanpa ini pesan tetap terkumpul, hanya tidak diringkas.")
    return 0


def daftar_model():
    """`--model`: tanyakan model apa saja yang tersedia di endpoint terpasang.

    Nama model berubah dari waktu ke waktu — Groq dan OpenRouter menarik model
    lama secara berkala. Menebak namanya hanya menghasilkan galat 404 yang
    membingungkan, jadi lebih baik ditanyakan langsung.
    """
    print(f"endpoint : {LLM_BASE}")
    print(f"model kini: {LLM_MODEL}")
    if not LLM_KEY:
        print("kunci    : TIDAK ADA — set LLM_KEY dulu")
        return 1
    asal = "LLM_KEY" if os.environ.get("LLM_KEY") else "XAI_API_KEY (jatuh kembali!)"
    print(f"kunci    : ada, dari {asal}")
    if asal.startswith("XAI") and "x.ai" not in LLM_BASE:
        print("           ^ endpoint bukan xAI tetapi kuncinya kunci xAI. "
              "Hampir pasti 401.")
    try:
        r = minta(f"{LLM_BASE}/models", {"Authorization": f"Bearer {LLM_KEY}"})
    except urllib.error.HTTPError as e:
        print(f"\ngagal: HTTP {e.code}" +
              ("  — kunci tidak cocok dengan endpoint ini" if e.code == 401 else ""))
        return 1
    daftar = [m.get("id") for m in (r.get("data") or []) if m.get("id")]
    print(f"\n{len(daftar)} model tersedia:")
    for m in sorted(daftar):
        print(f"  {m}" + ("   <== yang sedang dipakai" if m == LLM_MODEL else ""))
    if LLM_MODEL not in daftar:
        print(f"\nPERINGATAN: '{LLM_MODEL}' tidak ada di daftar. "
              f"Set LLM_MODEL ke salah satu di atas.")
    return 0


BULAN_ID = ["Januari", "Februari", "Maret", "April", "Mei", "Juni", "Juli",
            "Agustus", "September", "Oktober", "November", "Desember"]


def muat_arsip():
    if not ARSIP.exists():
        return {"diproses": [], "calls": []}
    try:
        d = json.loads(ARSIP.read_text(encoding="utf-8"))
        return {"diproses": d.get("diproses") or [], "calls": d.get("calls") or [],
                "ringkasan": d.get("ringkasan") or {}}
    except Exception:                                        # noqa: BLE001
        return {"diproses": [], "calls": [], "ringkasan": {}}


def data_pasar(aset):
    """Market cap dan volume 24 jam, satu panggilan untuk 500 koin teratas.

    Sengaja CoinGecko, bukan bursa: ia tidak diblokir operator dan satu
    permintaan menutup seluruh daftar, jadi ongkosnya tetap satu panggilan
    berapa pun simbol yang dipanggil analis.
    """
    if not aset:
        return {}
    cari = {a.upper() for a in aset}
    out = {}
    for hal in (1, 2):
        try:
            url = ("https://api.coingecko.com/api/v3/coins/markets?vs_currency=usd"
                   f"&order=market_cap_desc&per_page=250&page={hal}")
            for x in minta(url):
                sym = (x.get("symbol") or "").upper()
                if sym in cari and sym not in out:
                    out[sym] = {"mcap": x.get("market_cap"),
                                "vol24": x.get("total_volume"),
                                "harga": x.get("current_price")}
        except Exception:                                    # noqa: BLE001
            break
        time.sleep(3)                # CoinGecko gratis: 429 di sekitar 10/menit
    return out


# Status ringkas untuk tabel, diturunkan HANYA dari pengakuan analisnya sendiri.
# Harga bursa sengaja tidak dipakai di sini: itu permintaan eksplisit, dan
# konsekuensinya disebut apa adanya di dashboard — angka menang jadi optimistis
# karena orang melaporkan menang lebih rajin daripada kalah.
def status_dari_klaim(klaim):
    if not klaim:
        return "Open"
    if "TP" in klaim:
        return "TP"
    if "stop" in klaim:
        return "SL"
    if "BE" in klaim:
        return "BE"
    if "sedang jalan" in klaim:
        return "Jalan"
    if "ditutup" in klaim:
        return "Ditutup"
    return "Open"


def _uji():
    """Pemeriksaan cepat aturan yang paling gampang rusak diam-diam.

    Tiga kali dalam satu hari, pola regex di berkas ini rusak karena escape
    yang salah tulis, dan tiap kali akibatnya BUKAN galat melainkan data yang
    salah tanpa bunyi. Jadi aturannya sekarang punya uji yang bisa dijalankan
    sebelum menarik apa pun: python fetch_discord.py --uji
    """
    A = {"FARTCOIN", "NOT", "ENA", "VVV", "ME", "UNI", "WLD", "ONDO", "INIT"}
    kasus = [
        # kata Inggris yang kebetulan nama token tidak boleh dihitung aset kedua
        ("FARTCOIN not moving up with the rest of the market. Closing it fully here at BE",
         "FARTCOIN", "diaku ditutup"),
        # dua aset sungguhan: klaim hanya berlaku untuk yang sekalimat
        ("Got stopped on ENA overnight fam. Still long VVV as long as this 15min holds",
         "ENA", "diaku kena stop"),
        ("Got stopped on ENA overnight fam. Still long VVV as long as this 15min holds",
         "VVV", None),
        ("TP1 smashed on FARTCOIN fam, stops BE. Good wins today", "FARTCOIN", "diaku TP kena"),
        ("Closing ENA early here before the 1H close", "ENA", "diaku ditutup"),
    ]
    for teks, aset, harap in kasus:
        got = klaim_untuk_aset(teks, aset, A)
        assert got == harap, f"klaim {aset}: {got!r} bukan {harap!r} :: {teks[:50]}"

    # pola pembuka posisi
    for teks in ("Market long INIT here at CMP", "Buying some spot UNI here at CMP",
                 "Im going long ETH here at CMP guys", "Just longed INIT here at CMP"):
        assert POLA_CALL.search(teks), f"pola pembuka meleset: {teks}"
    for teks in ("TP hit on INIT fam, 4.7R", "Got stopped on ENA overnight fam",
                 "Stops BE on this, up 3R already", "Closing ENA early here"):
        m = POLA_CALL.search(teks)
        assert not m or m.group(2).upper() in BUKAN_ASET, f"salah tangkap: {teks}"

    # kabar posisi lama bukan panggilan baru
    assert RE_MASIH_PEGANG.search("I'm still holding my VVV long on Hyperliquid")
    assert not RE_MASIH_PEGANG.search("I'm longing VVV here at CMP again")
    assert RE_BUKA_POSISI.search("I'm longing VVV here at CMP again")

    print("fetch_discord: semua pemeriksaan aturan lolos")


def main():
    if "--uji" in sys.argv:
        return _uji()
    if "--cek" in sys.argv:
        sys.exit(periksa())
    if "--model" in sys.argv:
        sys.exit(daftar_model())

    jam = 24
    if "--jam" in sys.argv:
        jam = int(sys.argv[sys.argv.index("--jam") + 1])
    if "--bulan" in sys.argv:                # jalan pintas: --bulan 6
        jam = int(sys.argv[sys.argv.index("--bulan") + 1]) * 30 * 24

    # Contoh konfigurasi dibuat lebih dulu supaya kedua langkah persiapan —
    # token dan daftar channel — terlihat sekaligus, bukan satu per satu.
    baru = not KONFIG.exists()
    if baru:
        contoh_konfig()

    kurang = []
    if not TOKEN:
        kurang.append('  DISCORD_BOT_TOKEN belum diset.\n'
                      '    PowerShell: setx DISCORD_BOT_TOKEN "..."\n'
                      '    lalu tutup dan buka ulang terminalnya.')
    if baru:
        kurang.append(f"  {KONFIG.name} baru dibuat — isi channel ID-nya.")
    if kurang:
        sys.exit("Persiapan belum lengkap:\n" + "\n".join(kurang) +
                 "\n\n  Langkah membuat bot ada di bagian atas berkas ini.")

    cfg = json.loads(KONFIG.read_text(encoding="utf-8"))
    daftar = [c for c in cfg.get("channels", [])
              if str(c.get("id", "")).isdigit() and not str(c["id"]).startswith("00000")]
    if not daftar:
        sys.exit(f"Belum ada channel yang sah di {KONFIG.name}.")

    try:
        me = minta(f"{API}/users/@me", {"Authorization": f"Bot {TOKEN}"})
        print(f"bot: {me.get('username')}#{me.get('discriminator')}")
    except urllib.error.HTTPError as e:
        sys.exit(f"Token ditolak Discord (HTTP {e.code}). Periksa DISCORD_BOT_TOKEN.")

    # ID server dibutuhkan untuk menyusun tautan lompat ke pesan aslinya.
    guild = ""
    try:
        g = minta(f"{API}/users/@me/guilds", {"Authorization": f"Bot {TOKEN}"})
        if g:
            guild = str(g[0].get("id") or "")
    except urllib.error.HTTPError:
        pass

    sejak = datetime.now(timezone.utc) - timedelta(hours=jam)
    analis_cfg = cfg.get("analis") or []

    # ------------------------------------------------- kumpulkan dulu
    # Pesan dari semua channel disatukan, baru dikelompokkan per orang.
    # Analis yang sama sering menulis di beberapa channel, dan memisahkannya
    # per ruangan akan memecah jejaknya jadi potongan yang tidak nyambung.
    semua, kanal = [], []
    for c in daftar:
        nama, cid = c.get("nama") or c["id"], str(c["id"])
        try:
            pesan = baca_channel(cid, sejak, guild)
        except urllib.error.HTTPError as e:
            catat = {403: "bot tidak punya izin membaca channel ini",
                     404: "channel tidak ditemukan atau bot bukan anggota servernya"
                     }.get(e.code, f"HTTP {e.code}")
            print(f"  {nama:28} gagal: {catat}")
            kanal.append({"nama": nama, "id": cid, "galat": catat, "jumlah": 0})
            continue
        pesan, dibuang = saring_analis(pesan, c.get("analis") or analis_cfg)
        for p in pesan:
            p["kanal"] = nama
        semua.extend(pesan)
        kanal.append({"nama": nama, "id": cid, "jumlah": len(pesan)})
        print(f"  {nama:28} {len(pesan):>4} pesan" +
              (f" ({dibuang} disaring keluar)" if dibuang else ""))

    # ------------------------------------------------- kelompokkan per orang
    orang = {}
    for p in semua:
        k = p.get("penulisId") or p.get("penulis") or "?"
        o = orang.setdefault(k, {"nama": p.get("penulis") or "?", "id": p.get("penulisId") or "",
                                 "bot": p.get("bot", False), "pesan": [], "kanal": set(),
                                 "alias": set(), "avatar": ""})
        if not o["avatar"] and p.get("avatar"):
            o["avatar"] = p["avatar"]
        o["pesan"].append(p)
        o["kanal"].add(p.get("kanal"))
        # Nama tampilan webhook bisa berbeda tiap pesan; semuanya dicatat supaya
        # jelas bahwa ketiganya satu sumber, bukan tiga analis berbeda.
        o["alias"].add(p.get("penulis") or "?")

    print(f"\n{len(orang)} analis terdeteksi dari {len(semua)} pesan")

    _ars = muat_arsip()
    batas_iso = sejak.isoformat()
    # MASA SIMPAN ARSIP TETAP, bukan mengikuti jendela run ini.
    #
    # Sebelumnya pemangkasannya memakai `sejak`, yaitu jendela run yang sedang
    # berjalan. Akibatnya satu perintah `--jam 72` membuang 224 dari 227
    # panggilan SECARA PERMANEN, karena pesannya tetap tercatat di `diproses`
    # sehingga tidak akan pernah diekstrak ulang. Terjadi sungguhan: tabel enam
    # bulan menyusut jadi 3 baris dan 4 analis jadi 2, dan hanya bisa dipulihkan
    # karena berkasnya kebetulan sudah masuk git.
    #
    # Arsip melayani tampilan, bukan run. Jadi ukurannya adalah rentang
    # terpanjang yang pernah ditampilkan dashboard, apa pun argumen hari ini.
    batas_arsip = (datetime.now(timezone.utc)
                   - timedelta(days=RETENSI_HARI)).isoformat()
    arsip_lama = [c for c in _ars["calls"] if (c.get("waktu") or "") >= batas_arsip]
    # Panggilan hantu dari aturan versi lama dibuang saat dimuat, bukan
    # dibiarkan hidup di arsip selamanya. Lihat RE_MASIH_PEGANG.
    n_hantu = len(arsip_lama)
    arsip_lama = [c for c in arsip_lama
                  if not (RE_MASIH_PEGANG.search(c.get("kutipan") or "")
                          and not RE_BUKA_POSISI.search(c.get("kutipan") or ""))]
    if n_hantu != len(arsip_lama):
        print(f"arsip: {n_hantu - len(arsip_lama)} kabar posisi lama dibuang "
              f"(bukan panggilan baru)")
    if len(arsip_lama) < len(_ars["calls"]):
        print(f"arsip: {len(_ars['calls']) - len(arsip_lama)} panggilan lewat "
              f"{RETENSI_HARI} hari dibuang, {len(arsip_lama)} disimpan")
    sudah = set(_ars["diproses"])
    arsip_baru = []
    # Ringkasan juga disinggah. Tanpa ini, jalan ulang tetap memanggil LLM
    # sekali per analis walau tidak ada satu pun pesan baru — terukur menabrak
    # 429 dengan tunggu 1.348 detik setelah beberapa kali percobaan sehari.
    ringkas_lama = _ars.get("ringkasan", {})
    ringkas_baru = {}
    if arsip_lama:
        print(f"arsip: {len(arsip_lama)} panggilan lama dipakai ulang, "
              f"{len(sudah)} pesan tidak perlu diekstrak lagi")

    hasil, semua_calls, tolak_total = [], [], 0
    pesan_penuh = {}
    for k, o in sorted(orang.items(), key=lambda kv: -len(kv[1]["pesan"])):  # sementara
        pesan = sorted(o["pesan"], key=lambda p: p["waktu"], reverse=True)
        label = o["nama"]
        print(f"  {label:24} {len(pesan):>4} pesan", end="")
        # Hanya pesan yang belum pernah diekstrak yang dikirim ke LLM. Enam bulan
        # sekaligus berarti ratusan potongan; tanpa ini, tiap kali dijalankan
        # ulang seluruhnya diekstrak lagi dan kuota Groq habis sia-sia.
        baru = [p for p in pesan if p.get("pesanId") not in sudah]
        lama_n = len(pesan) - len(baru)
        # Kunci singgahan memuat jumlah pesan, jadi ringkasan otomatis dibuat
        # ulang begitu ada pesan baru, tapi tidak sebelum itu.
        # Versi ikut jadi kunci. Tanpa ini, ringkasan lama yang dibuat dari
        # pesan TERLAMA akan terus dipakai ulang karena jumlah pesannya sama.
        kunci_r = f"v2|{label}|{len(pesan)}"
        r = ringkas_lama.get(kunci_r)
        if r:
            print("  [ringkasan dari arsip]", end="")
        else:
            r = ringkas(label, pesan)
        if r and not r.startswith("["):
            ringkas_baru[kunci_r] = r
        calls, ditolak, gagal = ([], 0, 0)
        if baru:
            mentah, gagal = ekstrak_calls(baru)
            calls, ditolak = verifikasi(mentah, baru)
        if gagal:
            print(f"\n      {gagal} potongan gagal diekstrak; pesannya TIDAK "
                  f"ditandai selesai supaya dicoba lagi nanti.", end="")
        else:
            for p in baru:
                sudah.add(p.get("pesanId"))
        arsip_baru.extend(calls)
        tolak_total += ditolak
        # panggilan lama milik orang ini, diambil dari arsip
        calls = calls + [c for c in arsip_lama if c.get("penulis") == label]

        # Jaring pengaman deterministik, dijalankan atas SELURUH pesan orang ini
        # dan bukan hanya yang baru. Alasannya ada di calls_dari_pola().
        punya = {c.get("sumber") for c in calls if c.get("sumber")}
        tambahan = [c for c in calls_dari_pola(pesan, set())
                    if c.get("sumber") not in punya]
        if tambahan:
            print("\n      " + str(len(tambahan)) +
                  " panggilan diselamatkan jaring pola: " +
                  ", ".join(sorted({c["aset"] for c in tambahan})), end="")
            calls += tambahan
            arsip_baru.extend(tambahan)
        semua_calls.extend(calls)
        print(f"  {len(calls)} panggilan" +
              (f" ({ditolak} ditolak)" if ditolak else "") +
              (f" [{lama_n} dari arsip]" if lama_n else "") +
              ("  ringkasan ok" if r and not r.startswith("[") else f"  {r or 'tanpa ringkasan'}"))
        pesan_penuh[label] = pesan
        hasil.append({
            "nama": label,
            # Ditentukan lewat konfigurasi, bukan aturan turunan. Sempat dicoba
            # memakai rasio panggilan/pesan, tetapi angkanya tidak memisahkan:
            # Lynx 0,09 justru LEBIH RENDAH daripada Jaxx 0,13, sehingga aturan
            # apa pun yang diturunkan dari situ akan salah mengelompokkan.
            "ringkasanDulu": (o["id"] in (cfg.get("ringkasanDulu") or [])
                              or label in (cfg.get("ringkasanDulu") or [])), "id": o["id"], "bot": o["bot"], "avatar": o["avatar"],
            "alias": sorted(a for a in o["alias"] if a and a != label),
            "kanal": sorted(x for x in o["kanal"] if x),
            "jumlah": len(pesan), "ringkasan": r,
            # Kutipan mentah ikut disimpan supaya ringkasannya bisa diperiksa.
            "pesan": pesan[:80],
            "dari": pesan[-1]["waktu"] if pesan else None,
            "sampai": pesan[0]["waktu"] if pesan else None,
            "calls": [],
        })

    # ------------------------------------------------- rantai dan hasilnya
    grup = rantai(semua_calls)
    if grup:
        # Hasil HANYA dari pengakuan analisnya sendiri, sesuai permintaan.
        # nilai_hasil() yang membaca harga bursa sengaja tidak dipanggil lagi:
        # selain Binance diblokir operator, Gate.io butuh 25 detik per simbol
        # sehingga menilai ratusan panggilan mustahil dilakukan interaktif.
        # SELURUH pesan, bukan a["pesan"] yang sudah dipotong 40 untuk tampilan.
        # Dengan potongan itu, pengakuan yang lebih tua dari 40 pesan terakhir
        # tak pernah ditemukan — pada Neil yang punya 378 pesan, itu berarti
        # hampir semua klaim luput.
        klaim_lanjutan(grup, pesan_penuh)
        for g in grup:
            for c in g["calls"]:
                c["status"] = status_dari_klaim(c.get("klaim"))
        nk = sum(1 for g in grup for c in g["calls"] if c.get("klaim"))
        print(f"\n{nk} dari {len(semua_calls)} panggilan punya pengakuan hasil")
    # tempelkan rantai ke analis pemiliknya
    for g in grup:
        for a in hasil:
            if a["nama"] == g["penulis"]:
                a["calls"].append({"aset": g["aset"], "n": g["n"], "calls": g["calls"]})

    # ------------------------------------------------- baris tabel
    # Satu baris per panggilan, sudah rata — dashboard tidak perlu menelusuri
    # struktur bersarang hanya untuk menggambar satu tabel.
    baris = []
    for g in grup:
        for i, c in enumerate(g["calls"]):
            # Level dari teks dipakai untuk MENAMBAL yang tidak ditemukan LLM.
            # Polanya tetap dan bisa diperiksa, jadi lebih tepercaya daripada
            # tebakan model — tetapi tidak menimpa yang sudah ada.
            lt = level_dari_teks(c.get("kutipan"))
            baris.append({
                "aset": g["aset"], "penulis": g["penulis"],
                "arah": c.get("arah"),
                "entry": c.get("level") if c.get("level") is not None else lt["entry"],
                "target": c.get("target") if c.get("target") is not None else lt["target"],
                "stop": c.get("invalidasi") if c.get("invalidasi") is not None else lt["stop"],
                "status": c.get("status") or "Open", "klaim": c.get("klaim"),
                # Dihitung di sini, bukan hanya di klaim_lanjutan: panggilan yang
                # datang dari arsip sudah punya klaim, sehingga fungsi itu
                # melewatinya dan nomor TP-nya tidak pernah terisi.
                "kabar": c.get("kabar") or [],
                "dasarTP": c.get("dasarTP"),
                "tpKe": (c.get("tpKe") or
                         (nomor_tp(c.get("klaimTeks") or c.get("kutipan"))
                          if (c.get("klaim") or "").find("TP") >= 0 else None)),
                "klaimTeks": c.get("klaimTeks"),
                # Jam pengakuan ikut dibawa supaya imbal bisa dihitung sampai
                # saat itu, bukan sampai akhir jendela 7 hari. Tanpa ini kolom
                # Imbal menjawab pertanyaan yang berbeda dari kolom Hasil.
                "klaimWaktu": c.get("klaimWaktu"),
                "waktu": c.get("waktu"), "sumber": c.get("sumber"),
                "kutipan": c.get("kutipan"), "ke": i + 1, "dari": g["n"],
            })
    # SATU PESAN, SATU PANGGILAN PER ASET DAN ARAH.
    #
    # Model kadang memulangkan beberapa panggilan dari SATU pesan, masing-masing
    # mengutip potongan berbeda dari kalimat yang sama, dan verifikasi()
    # meloloskan semuanya karena tiap kutipan memang benar-benar ada di pesan
    # itu. Terukur: 7 dari 249 baris kembar begitu, termasuk satu pesan Jaxx
    # yang menjadi tiga baris BTC short sekaligus.
    #
    # Kuncinya memakai aset DAN arah, bukan pesan saja: satu pesan yang benar
    # menyebut dua aset ("long BTC dan ETH di sini") memang seharusnya jadi dua
    # panggilan, dan itu tidak boleh ikut terbuang.
    #
    # Yang dipertahankan adalah kutipan yang paling lengkap, diukur dari jumlah
    # level yang terisi lalu panjang kutipannya, karena kutipan penuh itulah
    # yang membawa entry, target, dan stop.
    _lihat = {}
    for r in baris:
        kunci = ((r.get("sumber") or "").rsplit("/", 1)[-1],
                 (r.get("aset") or "").upper(), (r.get("arah") or "").lower())
        if not kunci[0]:
            continue
        skor = (sum(r.get(f) is not None for f in ("entry", "target", "stop")),
                len(r.get("kutipan") or ""))
        if kunci not in _lihat or skor > _lihat[kunci][0]:
            _lihat[kunci] = (skor, r)
    _pilih = {id(v[1]) for v in _lihat.values()}
    _sebelum = len(baris)
    baris = [r for r in baris
             if not (r.get("sumber") or "").rsplit("/", 1)[-1] or id(r) in _pilih]
    if len(baris) != _sebelum:
        print(f"kembar: {_sebelum - len(baris)} baris dari pesan yang sama dibuang")

    # KOREKSI MANUAL, dibaca dari koreksi_manual.json yang ikut repo.
    #
    # Sebagian analis menutup posisi tanpa satu pun kata kunci yang bisa dibaca
    # mesin: mereka membalas dengan tangkapan layar chart, satu emoji, atau
    # kalimat yang tidak menyebut TP maupun stop. Pembaca manusia paham,
    # pembacaan otomatis tidak.
    #
    # Diterapkan DI SINI, sesudah baris terbentuk dan SEBELUM nilai_harga(),
    # supaya seluruh perhitungan di hilir memperlakukannya persis sama seperti
    # pengakuan yang terbaca sendiri. Tidak ada jalur kode kedua yang harus
    # ikut diuji.
    #
    # Asalnya tetap ditandai sumberHasil="manual", dan itu disengaja: alat ini
    # bisa menaikkan win rate, dan dashboardnya dibaca orang lain.
    # Dibaca lewat env_lokal supaya SATU aturan berlaku untuk kedua jalur:
    # koreksi lewat halaman web (tersimpan di volume) dan lewat alat lokal
    # (ikut repo). Lihat muat_koreksi().
    try:
        _kor = env_lokal.muat_koreksi()
    except Exception as e:                                   # noqa: BLE001
        _kor = {}
        print(f"koreksi manual tidak terbaca, dilewati: {e}")
    if _kor:
        # PENGHAPUSAN dijalankan lebih dulu, sebelum koreksi hasil, supaya baris
        # yang memang kembar tidak sempat ikut dihitung di mana pun. Alasannya
        # tetap tersimpan di berkas koreksi, jadi penghapusan bisa ditelusuri
        # dan dibatalkan.
        _hapus = {i for i, v in _kor.items() if v.get("hapus")}
        if _hapus:
            _n = len(baris)
            baris = [r for r in baris
                     if (r.get("sumber") or "").rsplit("/", 1)[-1] not in _hapus]
            print(f"koreksi manual: {_n - len(baris)} baris dihapus manual")

        n_kor = 0
        for r in baris:
            k = _kor.get((r.get("sumber") or "").rsplit("/", 1)[-1])
            if not k or not k.get("klaim"):
                continue
            r["klaim"] = k["klaim"]
            r["klaimTeks"] = "Koreksi manual: " + (k.get("catatan") or "")
            r["klaimWaktu"] = k.get("klaimWaktu")
            # Status ikut diturunkan lewat fungsi yang sama seperti pengakuan
            # biasa. Tanpa ini kolom Status tetap tertulis "Open" padahal
            # klaimnya sudah TP, dan itu persis kontradiksi yang sudah kita
            # buang beberapa perbaikan lalu.
            r["status"] = status_dari_klaim(k["klaim"])
            r["koreksiManual"] = True
            r["koreksiCatatan"] = k.get("catatan") or ""
            if k.get("tpKe"):
                r["tpKe"] = k["tpKe"]
            n_kor += 1
        print(f"koreksi manual: {n_kor} panggilan diperbaiki")

    baris.sort(key=lambda x: x["waktu"] or "", reverse=True)

    aset_dipakai = sorted({b["aset"] for b in baris if b.get("aset")})
    print(f"mengambil market cap dan volume untuk {len(aset_dipakai)} aset...")
    pasar_awal = data_pasar(aset_dipakai)
    print(f"  {len(pasar_awal)} dari {len(aset_dipakai)} aset ketemu di CoinGecko")

    # Penyaring kewarasan level. LLM kadang menarik angka yang kebetulan ada di
    # kalimat tapi bukan harga — terukur: entry "6793" untuk BTC saat BTC di
    # $78.000, yang membuat kolom target tertulis +138.706%. Angka semacam itu
    # lebih buruk daripada kosong, karena terlihat seperti data.
    #
    # Ambangnya lebar (10x) dengan sengaja: rentangnya enam bulan dan sebagian
    # aset memang bergerak beberapa kali lipat. Yang dibuang hanya yang mustahil.
    dibuang = 0
    for r in baris:
        acuan = (pasar_awal.get(r["aset"]) or {}).get("harga")
        if not acuan:
            continue
        for k in ("entry", "target", "stop"):
            v = r.get(k)
            if v and (v > acuan * 10 or v < acuan / 10):
                r[k] = None
                dibuang += 1
    if dibuang:
        print(f"{dibuang} level dibuang karena terlalu jauh dari harga wajar asetnya")

    # ------------------------------------------------- kartu posisi dari gambar
    # Sebagian analis mengabarkan hasil hanya lewat tangkapan layar kartu posisi
    # bursa, dengan teks satu kata. Kalau pembacanya tersedia, kartu itu memberi
    # yang tidak bisa didapat dari mana pun: harga entry PERSIS dan status
    # posisi (masih dipegang atau sudah ditutup).
    gbr = []
    for r in baris:
        for k in (r.get("kabar") or []):
            gbr.extend(k.get("gambar") or [])
    if gbr:
        try:
            import baca_kartu
            print(f"membaca {len(gbr)} kartu posisi dari gambar...")
            kartu, galat = baca_kartu.baca(gbr)
            if galat:
                print(f"  dilewati: {galat} "
                      f"(jalankan 'python baca_kartu.py' untuk langkah pemasangannya)")
            else:
                terpakai = 0
                for r in baris:
                    for k in (r.get("kabar") or []):
                        for u in (k.get("gambar") or []):
                            d = kartu.get(u) or {}
                            if d.get("galat") or d.get("bukan_kartu"):
                                continue
                            k["kartu"] = d
                            # Entry dari kartu MENGALAHKAN tebakan kline: ini
                            # angka yang benar-benar dipakai analisnya.
                            if d.get("entry") and r.get("entry") is None:
                                r["entry"] = d["entry"]
                            r["kartuGerak"] = d.get("gerak")
                            r["kartuStatus"] = d.get("status")
                            # Kartu yang ditempel di BALASAN adalah cara analis
                            # mengumumkan hasil. Tandanya diambil dari gerak
                            # harganya, bukan dari status "closed" saja —
                            # kartu "holding" yang hijau tetap pengumuman
                            # kemenangan menurut kebiasaan mereka.
                            #
                            # SIMETRIS DENGAN SENGAJA: kartu merah dihitung
                            # rugi. Menghitung yang hijau saja akan mengulang
                            # persis bias yang membuat angka menang membengkak.
                            if d.get("gerak") is not None:
                                r["klaim"] = ("diaku TP kena" if d["gerak"] > 0
                                              else "diaku kena stop")
                                r["status"] = status_dari_klaim(r["klaim"])
                                r["dasarTP"] = ("kartu posisi "
                                                + (d.get("status") or "tanpa status"))
                            terpakai += 1
                print(f"  {terpakai} kartu terbaca dan dipakai")
        except ImportError:
            print("  baca_kartu.py tidak ditemukan, kartu gambar dilewati")

    # Kolom hasil KEDUA, berdampingan dengan klaim — bukan menggantikannya.
    # Terukur: dalam 1.350 pesan selama 6 bulan tidak ada satu pun laporan
    # kerugian, sehingga kolom klaim saja selalu memberi 100% menang. Itu
    # mengukur kebiasaan mengumumkan, bukan hasil dagang.
    print("menilai panggilan terhadap harga Binance...")
    nilai_harga(baris, int(sejak.timestamp() * 1000))

    # Urutan acuan: PENGAKUAN ANALIS DULU, harga hanya kalau tidak ada pengakuan.
    # Alasannya, analis tahu kapan ia benar-benar keluar dari posisi, sedangkan
    # harga hanya bisa mengira-ngira lewat horizon tetap tujuh hari. Horizon itu
    # asumsi, bukan fakta — kalau ada yang tahu lebih baik, dialah yang dipakai.
    for r in baris:
        k = r.get("klaim") or ""
        if "TP" in k:
            r["hasilAkhir"], r["sumberHasil"] = "untung", "analis"
        elif "stop" in k:
            r["hasilAkhir"], r["sumberHasil"] = "rugi", "analis"
        elif "BE" in k:
            r["hasilAkhir"], r["sumberHasil"] = "impas", "analis"
        elif "ditutup" in k:
            r["hasilAkhir"], r["sumberHasil"] = "ditutup", "analis"
        elif "sedang jalan" in k:
            # Analis hanya mengabarkan posisinya masih berjalan — itu bukan
            # hasil. Harga yang menentukan, kalau tersedia.
            r["hasilAkhir"] = r.get("hasil")
            r["sumberHasil"] = "harga" if r.get("imbal") is not None else None
        else:
            r["hasilAkhir"] = r.get("hasil")
            r["sumberHasil"] = "harga" if r.get("imbal") is not None else None
    # Asal "manual" ditegaskan SESUDAH pemetaan hasil, bukan di tengahnya.
    # Pemetaannya sengaja dilewati sama persis seperti pengakuan biasa supaya
    # tidak ada cabang kedua; yang berbeda hanya keterangan asalnya, dan itu
    # yang dipakai dashboard untuk menandainya.
    for r in baris:
        if r.get("koreksiManual"):
            r["sumberHasil"] = "manual"

    # STATUS IKUT HARGA KALAU ANALISNYA TIDAK PERNAH MENGAKU.
    #
    # Dilaporkan pembaca: satu baris tertulis STATUS "Open" tetapi HASIL
    # "stop kena". Itu memang bertolak belakang. Kalau harga sudah menyentuh
    # batas invalidasinya, posisinya tertutup oleh stop, apakah analisnya
    # mengumumkannya atau tidak. Yang belum diketahui hanya pengakuannya.
    #
    # Jadi statusnya diisi, dan asalnya ditandai supaya tetap bisa dibedakan
    # dari status yang benar-benar diakui analisnya sendiri.
    for r in baris:
        if r.get("klaim") or r.get("status") not in (None, "", "Open"):
            r["statusSumber"] = "analis" if r.get("klaim") else None
            continue
        h = r.get("hasil")
        if h == "invalidasi tersentuh":
            r["status"], r["statusSumber"] = "SL", "harga"
        elif h == "target tersentuh":
            r["status"], r["statusSumber"] = "TP", "harga"

    # IMBAL DIAMBIL DARI KARTU KALAU ADA — dan ini WAJIB dijalankan SESUDAH
    # nilai_harga(), bukan sebelumnya, karena fungsi itu menulis r["imbal"] dan
    # akan menimpa apa pun yang dipasang lebih dulu.
    #
    # Contoh yang memaksa perubahan ini: AKEUSDT short, 20 Juli. Kartu Lynx
    # menunjukkan +5,63% sembilan jam setelah masuk; kline tujuh hari
    # menunjukkan -153% karena token itu naik 153% dalam sepekan. Keduanya
    # benar, tetapi mengukur hal berbeda — kartu mencatat apa yang BENAR-BENAR
    # dialami analisnya, sedangkan horizon tujuh hari mengandaikan posisinya
    # dipegang terus. Kalau kabarnya ada, kabar itulah yang berlaku.
    for r in baris:
        if r.get("kartuGerak") is not None:
            r["imbalHarga"] = r.get("imbal")      # pembanding, disimpan di tooltip
            r["imbal"] = r["kartuGerak"]
            r["imbalSumber"] = "kartu"
        else:
            r["imbalSumber"] = "harga" if r.get("imbal") is not None else None
    dari_analis = sum(1 for r in baris if r.get("sumberHasil") == "analis")
    dari_harga = sum(1 for r in baris if r.get("sumberHasil") == "harga")
    print(f"acuan hasil: {dari_analis} dari pengakuan analis, {dari_harga} dari harga, "
          f"{len(baris) - dari_analis - dari_harga} tanpa acuan")

    # Win rate dan runtun per analis, dihitung dari status yang sudah pasti saja.
    # "Open" tidak dihitung sebagai menang maupun kalah — memasukkannya akan
    # membuat angkanya bergerak hanya karena ada panggilan yang belum selesai.
    for a in hasil:
        milik = [b for b in baris if b["penulis"] == a["nama"]]
        putus = [b for b in milik if b["status"] in ("TP", "SL")]
        menang = sum(1 for b in putus if b["status"] == "TP")
        a["wr"] = round(menang / len(putus) * 100, 1) if putus else None
        a["nPutus"] = len(putus)
        a["nCall"] = len(milik)
        runtun = 0
        for b in putus:                      # sudah urut terbaru dulu
            if b["status"] == "TP":
                runtun += 1
            else:
                break
        a["runtun"] = runtun
        # Statistik dari harga, dipisah dari klaim. Keduanya menjawab
        # pertanyaan berbeda dan tidak boleh dicampur jadi satu angka.
        MENANG = ("untung", "target tersentuh")
        KALAH = ("rugi", "invalidasi tersentuh")
        pasti = [x for x in milik if x.get("hasilAkhir") in MENANG + KALAH]
        a["nAkhir"] = len(pasti)
        a["wrAkhir"] = (round(sum(1 for x in pasti if x["hasilAkhir"] in MENANG)
                              / len(pasti) * 100, 1) if pasti else None)
        dinilai = [x for x in milik if x.get("imbal") is not None]
        a["nHarga"] = len(dinilai)
        a["wrHarga"] = (round(sum(1 for x in dinilai if x["imbal"] > 0)
                              / len(dinilai) * 100, 1) if dinilai else None)
        a["imbalRata"] = (round(sum(x["imbal"] for x in dinilai) / len(dinilai), 2)
                          if dinilai else None)
        a["imbalDariKartu"] = sum(1 for x in dinilai if x.get("imbalSumber") == "kartu")

    # Analis diurutkan ulang berdasarkan JUMLAH PANGGILAN, bukan jumlah pesan.
    # Yang paling banyak bicara belum tentu yang paling banyak memberi panggilan
    # — Lynx menulis 487 pesan tetapi 43 panggilan, sedangkan Neil 378 pesan
    # dengan 131 panggilan. Karena segmen ini tentang panggilan, yang paling
    # produktif itulah yang pantas terbuka lebih dulu.
    hasil.sort(key=lambda a: -(a.get("nCall") or 0))

    # ------------------------------------------------- kelompok per bulan
    bulan = {}
    for b in baris:
        k = (b["waktu"] or "")[:7]
        if not k:
            continue
        bulan.setdefault(k, []).append(b)
    daftar_bulan = []
    for k in sorted(bulan, reverse=True):
        th, bl = k.split("-")
        daftar_bulan.append({"kunci": k, "label": f"{BULAN_ID[int(bl) - 1]} {th}",
                             "baris": bulan[k]})

    # ------------------------------------------------- heatmap harian
    # Satu sel per tanggal: hijau kalau ada TP, merah kalau ada SL. Hari dengan
    # keduanya dicatat apa adanya supaya dashboard bisa memilih warnanya sendiri
    # alih-alih menyembunyikan salah satunya.
    harian = {}
    for b in baris:
        hr = (b["waktu"] or "")[:10]
        if not hr:
            continue
        d = harian.setdefault(hr, {"tp": 0, "sl": 0, "lain": 0})
        if b["status"] == "TP":
            d["tp"] += 1
        elif b["status"] == "SL":
            d["sl"] += 1
        else:
            d["lain"] += 1

    pasar = pasar_awal

    ARSIP.write_text(json.dumps({
        "diperbarui": datetime.now(timezone.utc).isoformat(),
        "diproses": sorted(sudah),
        "calls": arsip_lama + arsip_baru,
        "ringkasan": {**ringkas_lama, **ringkas_baru},
    }, ensure_ascii=False), encoding="utf-8")

    OUT.write_text(json.dumps({
        "dibuat": datetime.now(timezone.utc).isoformat(),
        "jendelaJam": jam,
        "model": LLM_MODEL if LLM_KEY else None,
        "catatan": "Konteks, bukan sinyal. Ringkasan dibuat LLM dan bisa keliru; "
                   "kutipan mentahnya disertakan supaya bisa diperiksa sendiri. "
                   "Panggilan hanya dimuat kalau kutipannya terbukti ada di pesan "
                   "asli. HASIL BERASAL DARI PENGAKUAN ANALISNYA SENDIRI, bukan "
                   "dari harga bursa — jadi angka menang cenderung optimistis, "
                   "karena orang melaporkan menang lebih rajin daripada kalah.",
        "bulan": daftar_bulan,
        "harian": harian,
        "pasar": pasar,
        "baris": baris,
        "analis": hasil,
        "channels": kanal,
        "callDitolak": tolak_total,
        "callSah": len(semua_calls),
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{len(baris)} baris tabel dalam {len(daftar_bulan)} bulan, "
          f"{len(harian)} hari terisi di heatmap")
    print(f"\n{len(semua)} pesan dari {len(kanal)} channel, dikelompokkan jadi "
          f"{len(hasil)} analis, {len(semua_calls)} panggilan sah "
          f"({tolak_total} ditolak karena kutipannya tidak terbukti)")
    print(f"tersimpan di {OUT}")


if __name__ == "__main__":
    main()
