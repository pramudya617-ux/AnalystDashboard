"""Membaca kartu posisi Gate.io dari gambar lampiran Discord, lewat Gemini.

KENAPA ADA
    Sebagian analis — Lynx yang paling menonjol — mengabarkan hasil bukan
    dengan kalimat, melainkan dengan menempelkan tangkapan layar kartu posisi
    Gate.io dan menulis satu kata seperti "Running" atau "Bahh". Teksnya tidak
    menyatakan apa pun yang bisa dihitung; seluruh isinya ada di gambar.

APA YANG ADA DI KARTU ITU
    Terbaca dari contoh sungguhan (IMG_6161.png di channel Lynx):

        HYPEUSDT  Futures
        Short 75x   Holding
        ROI  +189.55%
        Last Price 80.081     Entry Price 82.279
        2026-08-26 04:42:47

    Empat hal berharga: harga entry PERSIS, status posisi (Holding/Closed),
    arah, dan leverage.

JEBAKAN YANG HARUS DIHINDARI
    ROI di kartu itu SUDAH DIKALI LEVERAGE. +189,55% pada 75x hanya berarti
    harga bergerak 2,67% (82,279 -> 80,081). Menampilkan 189% sebagai imbal
    hasil akan melebih-lebihkan hampir tujuh puluh kali lipat. Karena itu
    modul ini selalu menghitung ulang gerak harga dari entry dan last price,
    dan ROI mentahnya disimpan terpisah.

PEMASANGAN
    Buat kunci gratis di https://aistudio.google.com/apikey (tanpa kartu kredit),
    lalu pilih SALAH SATU:

    a) Hanya proyek ini — buat berkas .env di folder ini berisi satu baris:
           GEMINI_API_KEY=kunci-anda
       Tidak menyentuh proyek lain, dan langsung berlaku tanpa buka ulang terminal.

    b) Semua proyek di mesin ini:
           setx GEMINI_API_KEY "kunci-anda"
       Lalu tutup dan buka ulang terminalnya. Perhatikan: ini MENIMPA nilai lama
       kalau nama variabelnya sama dengan yang dipakai proyek lain.

    Tingkat gratisnya sekitar 15 permintaan per menit. Hasil setiap gambar
    disinggah permanen di kartu_singgahan.json, jadi satu gambar tidak pernah
    dibaca dua kali walau skripnya dijalankan berulang.
"""
import base64
import json
import os
import re
import time
import urllib.error
import urllib.request
from pathlib import Path

import env_lokal  # noqa: F401  (mengisi environment dari .env)

HERE = Path(__file__).resolve().parent
SINGGAH = HERE / "kartu_singgahan.json"
KEY = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY", "")
PANGKAL = "https://generativelanguage.googleapis.com/v1beta"
# Model TIDAK dipatok. Ini pensiun model ketiga yang menghentikan proyek ini —
# setelah llama-3.3-70b-versatile di Groq (dua kali). Gemini bahkan menolak
# model lama khusus untuk pengguna baru: "gemini-2.5-flash is no longer
# available to new users". Jadi daftarnya ditanyakan, bukan ditebak.
MODEL = os.environ.get("GEMINI_MODEL", "")
# Urutan pilihan: flash lebih dulu (cepat dan murah, cukup untuk membaca kartu
# yang teksnya bersih), pro hanya kalau flash tidak ada.
SUKA = ("flash-latest", "3.6-flash", "flash-lite-latest", "flash", "pro-latest")
_habis = set()                     # model yang kuota hariannya sudah habis
_urut = []                         # daftar model layak, diisi sekali
# BATAS SESUNGGUHNYA, dibaca dari pesan galat Google sendiri:
#   GenerateRequestsPerDayPerProjectPerModel-FreeTier = 20
#
# Dua puluh permintaan PER HARI, bukan per menit. Anggapan awal "15 per menit"
# keliru, dan akibatnya fatal: skrip menunggu 60 detik lalu MELEWATI gambar,
# sehingga 29 gambar hilang diam-diam dan setengah jam terbuang.
#
# Yang menyelamatkan: batas itu dihitung PER MODEL. Empat model bisa dipakai,
# jadi tersedia sekitar 80 permintaan sehari kalau digilir. Karena batasnya
# harian, jeda antar permintaan tidak lagi berguna — cukup sopan saja.
JEDA = 1.0
_terakhir = 0.0

ARAHAN = """Gambar ini adalah kartu posisi dari bursa kripto (biasanya Gate.io).
Baca APA ADANYA dan pulangkan HANYA JSON, tanpa penjelasan, tanpa pagar kode:

{"simbol":"HYPEUSDT","arah":"short","leverage":75,"status":"holding",
 "roi":189.55,"entry":82.279,"terakhir":80.081,"waktu":"2026-08-26 04:42:47"}

Aturan:
- "status" hanya boleh "holding" atau "closed", ikuti kata di kartunya.
- "arah" hanya boleh "long" atau "short".
- "roi" angka persen apa adanya, boleh negatif.
- Kalau sebuah nilai tidak terlihat di gambar, tulis null. JANGAN menebak.
- Kalau gambar ini BUKAN kartu posisi (misalnya grafik biasa), pulangkan {"bukan_kartu":true}."""


def _daftar_model():
    """Model yang benar-benar dilayani kunci ini, urut sesuai preferensi."""
    global _urut
    if _urut:
        return _urut
    try:
        d = json.loads(urllib.request.urlopen(
            f"{PANGKAL}/models?key={KEY}", timeout=30).read().decode("utf-8"))
    except Exception:                                        # noqa: BLE001
        _urut = ["gemini-3.6-flash"]
        return _urut
    ada = [m["name"].split("/")[-1] for m in d.get("models", [])
           if "generateContent" in (m.get("supportedGenerationMethods") or [])
           and "tts" not in m["name"] and "image" not in m["name"]
           and "embedding" not in m["name"]]
    urut = []
    for pola in SUKA:
        for m in ada:
            if m.endswith(pola) and m not in urut:
                urut.append(m)
    for m in ada:                  # sisanya sebagai cadangan terakhir
        if m not in urut:
            urut.append(m)
    _urut = urut
    return _urut


def _pilih_model():
    """Model pertama yang kuota hariannya belum habis; None kalau habis semua."""
    if MODEL:                      # dipaksa lewat GEMINI_MODEL
        return None if MODEL in _habis else MODEL
    for m in _daftar_model():
        if m not in _habis:
            return m
    return None


class KuotaHabis(RuntimeError):
    """Semua model kehabisan jatah harian; bukan kegagalan yang bisa diulang."""


def _muat():
    if SINGGAH.exists():
        try:
            return json.loads(SINGGAH.read_text(encoding="utf-8"))
        except Exception:                                    # noqa: BLE001
            pass
    return {}


def _simpan(d):
    SINGGAH.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")


def _unduh(url):
    # CDN Discord membalas 403 tanpa User-Agent — terukur.
    r = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(r, timeout=40) as f:
        return f.read()


def _kunci(url):
    """Nama berkas Discord tetap walau tanda tangan URL-nya berganti."""
    return url.split("?")[0].rsplit("/", 2)[-2:][0] + "/" + url.split("?")[0].rsplit("/", 1)[-1]


def _tanya(gambar, mime="image/png", coba=4):
    """Satu pintu ke Gemini, dengan penanganan dua kegagalan yang terukur.

    503 Service Unavailable sering muncul di tingkat gratis — bukan kesalahan
    permintaan, hanya server sedang penuh, dan berhasil pada percobaan
    berikutnya. Menyerah di percobaan pertama akan membuang kartu tanpa alasan.

    Balasan KOSONG punya sebab lain: model Gemini 3.x menalar lebih dulu, dan
    penalaran itu memakan jatah maxOutputTokens. Kalau jatahnya sempit, seluruh
    anggaran habis sebelum satu huruf jawaban keluar — persis kegagalan yang
    dulu terjadi pada gpt-oss di Groq. Karena itu jatahnya dilonggarkan dan
    penalarannya diminta seminimal mungkin.
    """
    global _terakhir
    body = json.dumps({
        "contents": [{"parts": [
            {"text": ARAHAN},
            {"inline_data": {"mime_type": mime,
                             "data": base64.b64encode(gambar).decode()}}]}],
        "generationConfig": {"temperature": 0, "maxOutputTokens": 1200,
                             "responseMimeType": "application/json",
                             "thinkingConfig": {"thinkingBudget": 0}},
    }).encode()
    for i in range(coba):
        m = _pilih_model()
        if not m:
            raise KuotaHabis("kuota harian semua model Gemini sudah terpakai")
        tunggu = JEDA - (time.time() - _terakhir)
        if tunggu > 0:
            time.sleep(tunggu)
        try:
            r = urllib.request.Request(
                f"{PANGKAL}/models/{m}:generateContent?key={KEY}",
                data=body, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(r, timeout=90) as f:
                d = json.loads(f.read().decode("utf-8"))
            _terakhir = time.time()
        except urllib.error.HTTPError as e:
            _terakhir = time.time()
            if e.code == 429:
                # Kuota HARIAN model ini habis. Menunggu tidak menolong; yang
                # menolong adalah pindah ke model lain yang jatahnya terpisah.
                _habis.add(m)
                if _pilih_model():
                    continue
                raise KuotaHabis(
                    "kuota harian semua model Gemini sudah terpakai "
                    f"({len(_habis)} model dicoba). Coba lagi besok, atau "
                    "sisa gambarnya akan dibaca pada jalan berikutnya.")
            if e.code in (500, 503) and i < coba - 1:
                time.sleep(8 * (i + 1))
                continue
            if e.code == 400 and b"thinkingConfig" in body:
                # Model lama tidak mengenal thinkingConfig; coba lagi tanpa itu.
                b2 = json.loads(body.decode())
                b2["generationConfig"].pop("thinkingConfig", None)
                b2["generationConfig"].pop("responseMimeType", None)
                body = json.dumps(b2).encode()
                continue
            raise
        teks = ""
        for c in d.get("candidates", []):
            for p in (c.get("content") or {}).get("parts", []):
                teks += p.get("text") or ""
        m = re.search(r"\{.*\}", teks, re.S)
        if m:
            try:
                return json.loads(m.group(0))
            except json.JSONDecodeError:
                pass
        if i < coba - 1:
            time.sleep(3)
    return None


def gerak_harga(k):
    """Gerak harga SESUNGGUHNYA, bukan ROI berleverage.

    Inilah satu-satunya angka yang boleh dibandingkan dengan imbal hasil dari
    kline. ROI kartu tidak sebanding karena sudah dikali leverage.
    """
    e, t = k.get("entry"), k.get("terakhir")
    if not e or not t:
        return None
    gerak = (t / e - 1) * 100
    return round(-gerak if (k.get("arah") or "").lower() == "short" else gerak, 2)


def baca(urls, diam=False):
    """{url: hasil} untuk setiap gambar; yang sudah pernah dibaca diambil dari singgahan."""
    singgah = _muat()
    if not KEY:
        return {}, "GEMINI_API_KEY belum diset"
    # Dibuat unik lebih dulu. Satu gambar bisa muncul berkali-kali dalam daftar
    # karena satu balasan menempel ke beberapa panggilan sekaligus; tanpa ini,
    # gambar yang sama dikirim ke Gemini berulang dan kuota habis untuk jawaban
    # yang sudah ada. Terukur: dari 91 gambar, tiga permintaan pertama semuanya
    # gambar yang sama.
    unik, lihat = [], set()
    for u in urls:
        k = _kunci(u)
        if k not in lihat:
            lihat.add(k)
            unik.append(u)
    baru = [u for u in unik if _kunci(u) not in singgah]
    if not diam and baru:
        print(f"  membaca {len(baru)} kartu baru "
              f"({len(unik) - len(baru)} dari singgahan, "
              f"{len(urls) - len(unik)} duplikat dilewati)...")
    for i, u in enumerate(baru, 1):
        try:
            g = _unduh(u)
            mime = "image/jpeg" if u.split("?")[0].lower().endswith((".jpg", ".jpeg")) else "image/png"
            hasil = _tanya(g, mime)
        except KuotaHabis as e:
            # Berhenti rapi. Yang sudah terbaca tetap tersimpan, dan sisanya
            # dibaca pada jalan berikutnya — JANGAN dilewati diam-diam.
            if not diam:
                print(f"    berhenti di {i}/{len(baru)}: {e}")
            return ({u: singgah.get(_kunci(u)) for u in urls},
                    f"{len(baru) - i + 1} gambar belum terbaca ({e})")
        except urllib.error.HTTPError as e:
            hasil = {"galat": f"HTTP {e.code}"}
        except Exception as e:                               # noqa: BLE001
            hasil = {"galat": str(e)[:120]}
        if hasil and not hasil.get("galat"):
            hasil["gerak"] = gerak_harga(hasil)
        singgah[_kunci(u)] = hasil or {"galat": "tidak terbaca"}
        _simpan(singgah)
        if not diam:
            h = singgah[_kunci(u)]
            ket = (f"{h.get('simbol')} {h.get('arah')} {h.get('leverage')}x "
                   f"{h.get('status')} gerak={h.get('gerak')}%"
                   if not h.get("galat") and not h.get("bukan_kartu")
                   else (h.get("galat") or "bukan kartu posisi"))
            print(f"    {i}/{len(baru)} {ket}")
    return {u: singgah.get(_kunci(u)) for u in urls}, None


def _demo():
    """Pemeriksaan mandiri: hitungan gerak harga harus benar dan tidak berleverage."""
    k = {"entry": 82.279, "terakhir": 80.081, "arah": "short", "roi": 189.55}
    g = gerak_harga(k)
    assert 2.6 < g < 2.8, g          # ~2,67%, BUKAN 189%
    assert gerak_harga({"entry": 100, "terakhir": 110, "arah": "long"}) == 10.0
    assert gerak_harga({"entry": 100, "terakhir": 110, "arah": "short"}) == -10.0
    assert gerak_harga({"entry": None, "terakhir": 1, "arah": "long"}) is None
    print("gerak_harga ok — ROI berleverage tidak ikut terbawa")


if __name__ == "__main__":
    import sys
    if "--demo" in sys.argv:
        _demo()
    elif not KEY:
        print(__doc__.split("PEMASANGAN")[1])
    else:
        print(f"model terpilih: {_pilih_model()}")
        print(f"sudah tersinggah: {len(_muat())} kartu")
