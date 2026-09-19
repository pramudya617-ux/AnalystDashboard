"""Tarik panggilan Zora dari Discord, urai TP/SL-nya, lalu nilai hasilnya dengan
harga Binance.

Berbeda dari analis lain yang formatnya bebas dan butuh LLM, Zora menulis dengan
pola tetap, jadi penguraiannya memakai aturan pasti - lebih murah dan hasilnya
tidak pernah berubah-ubah:

    $AKE | SPOT/PERPS
    Plan: Swing || Long/BUY
    Entry: CMP (Current Market Price) or 0,02400
    TP 1: 0,02900
    TP 2: 0,03300
    TP 3: 0,03800
    SL: 0,02060 (20%)

Jalankan:  python tarik_zora.py
Keluaran:  data/zora.json  (dibaca lib/data.js)

Uji tanpa jaringan:  python tarik_zora.py --selftest
"""
import json
import os
from datetime import datetime, timezone
import pathlib
import re
import sys
import time
import urllib.error
import urllib.request

# Binance diblokir di lapis DNS di Indonesia: resolver jaringan memulangkan IP
# internetpositif yang membalas 403. dns_doh menambal resolusi nama lewat
# DNS-over-HTTPS sehingga sambungannya sampai ke server aslinya.
import dns_doh  # noqa: F401  (efeknya lewat impor)

HERE = pathlib.Path(__file__).resolve().parent
# DATA_DIR menunjuk volume permanen Railway. Tanpa itu (mis. di laptop), hasilnya
# ditulis ke folder data/ biasa.
_vol = os.environ.get("DATA_DIR")
KELUARAN = (pathlib.Path(_vol) if _vol and pathlib.Path(_vol).is_dir()
            else HERE / "data") / "zora.json"

ZORA_USER = "1548790432006152202"
ZORA_CHANNEL = "1548792499810598932"

API = "https://discord.com/api/v10"
BINANCE = "https://api.binance.com/api/v3"
UA = {"User-Agent": "DiscordBot (https://localhost, 1.0)"}

# Horizon penilaian: kalau dalam 14 hari tidak ada TP maupun SL tersentuh,
# panggilan dianggap belum selesai, bukan menang atau kalah.
HORIZON_HARI = 14


def ke_ms(stempel):
    """Stempel Discord SELALU UTC. time.mktime menafsirkannya sebagai waktu lokal,
    dan di WIB itu meleset tujuh jam - cukup untuk mengambil lilin yang salah dan
    memberi harga masuk yang keliru. Jadi zona waktunya dipasang eksplisit."""
    return int(datetime.strptime(stempel[:19], "%Y-%m-%dT%H:%M:%S")
               .replace(tzinfo=timezone.utc).timestamp() * 1000)


# ----------------------------------------------------------------- penguraian
def angka(teks):
    """'0,02400' -> 0.024. Zora memakai koma sebagai pemisah desimal; titik
    dipakai sebagai pemisah ribuan, jadi urutan pembersihannya penting."""
    if teks is None:
        return None
    t = str(teks).strip().replace(" ", "")
    if "," in t:
        t = t.replace(".", "").replace(",", ".")
    try:
        n = float(t)
    except ValueError:
        return None
    return n if n > 0 else None


RE_ASET = re.compile(r"\$([A-Z0-9]{2,15})\b")
RE_ARAH = re.compile(r"\b(long|buy|short|sell)\b", re.I)
RE_ENTRY = re.compile(r"entry\s*:?[^\n]*?(?:or|atau|@)?\s*([\d.,]+)\s*$", re.I | re.M)
RE_TP = re.compile(r"\btp\s*([1-4])\s*:?\s*([\d.,]+)", re.I)
RE_SL = re.compile(r"\bsl\s*:?\s*([\d.,]+)", re.I)


def urai(teks):
    """Kembalikan dict panggilan, atau None kalau pesan ini bukan panggilan."""
    if not teks:
        return None
    aset = RE_ASET.search(teks)
    if not aset:
        return None

    tp = {}
    for m in RE_TP.finditer(teks):
        n = angka(m.group(2))
        if n:
            tp[int(m.group(1))] = n
    sl = angka(RE_SL.search(teks).group(1)) if RE_SL.search(teks) else None
    if not tp and not sl:
        return None  # tanpa target maupun stop, tidak ada yang bisa dinilai

    m_entry = RE_ENTRY.search(teks)
    entry = angka(m_entry.group(1)) if m_entry else None

    arah = "long"
    m_arah = RE_ARAH.search(teks)
    if m_arah and m_arah.group(1).lower() in ("short", "sell"):
        arah = "short"

    return {
        "aset": aset.group(1).upper(),
        "arah": arah,
        "entry": entry,
        "tp": dict(sorted(tp.items())),
        "sl": sl,
    }


# -------------------------------------------------------------------- Discord
def discord(url, token):
    req = urllib.request.Request(url, headers={**UA, "Authorization": f"Bot {token}"})
    with urllib.request.urlopen(req, timeout=40) as r:
        return json.load(r)


def profil(token, user=ZORA_USER):
    """Nama tampilan dan URL avatar Zora, supaya kartunya tidak memakai kotak kosong."""
    try:
        u = discord(f"{API}/users/{user}", token)
    except Exception:  # noqa: BLE001
        return {"nama": "Zora", "avatar": None}
    av = u.get("avatar")
    ext = "gif" if str(av).startswith("a_") else "png"
    return {
        "nama": u.get("global_name") or u.get("username") or "Zora",
        "avatar": (f"https://cdn.discordapp.com/avatars/{user}/{av}.{ext}?size=128"
                   if av else None),
    }


def ambil_pesan(token, channel=ZORA_CHANNEL, penulis=ZORA_USER, maks=1000):
    """Semua pesan channel, dari yang terbaru mundur, disaring ke satu penulis."""
    keluar, sebelum = [], None
    while len(keluar) < maks:
        url = f"{API}/channels/{channel}/messages?limit=100"
        if sebelum:
            url += f"&before={sebelum}"
        batch = discord(url, token)
        if not batch:
            break
        keluar += [m for m in batch if str(m.get("author", {}).get("id")) == penulis]
        sebelum = batch[-1]["id"]
        if len(batch) < 100:
            break
        time.sleep(0.4)  # jangan memancing rate limit Discord
    return keluar


# -------------------------------------------------------------------- Binance
# Nama yang ditulis analis tidak selalu sama dengan tiker bursanya.
ALIAS = {"SOLANA": "SOL", "BITCOIN": "BTC", "ETHEREUM": "ETH", "ETHER": "ETH",
         "RIPPLE": "XRP", "DOGECOIN": "DOGE", "PUMPFUN": "PUMP"}

_simbol_cache = None
_simbol_lengkap = False   # apakah daftar spot DAN futures sama-sama terambil


def simbol_binance():
    """Peta simbol -> 'spot' / 'futures'.

    Futures ikut dimasukkan karena banyak aset kecil hanya ada di sana; kalau
    hanya spot, panggilan yang sah akan salah dicap 'tidak ada di Binance'.

    Mengembalikan None kalau KEDUA sumber gagal dihubungi. Itu dibedakan dari
    'tidak listed' dengan sengaja: gagal jaringan pernah membuat seluruh
    panggilan dicap tidak ada di Binance, dan itu kesimpulan yang salah.

    SEPARUH juga bukan lengkap. Railway tidak bisa menghubungi fapi.binance.com
    (Binance menolak IP pusat data), jadi hanya daftar spot yang terambil - dan
    setiap aset futures-saja lalu dicap 'tidak diperdagangkan' dengan yakin.
    Itu menghapus hasil AKE, BULLA, dan ARIA di produksi. Sekarang keadaan
    'daftarnya tidak utuh' dicatat lewat _simbol_lengkap, dan pasangan()
    menjawab '?' alih-alih menyimpulkan yang tidak dia ketahui."""
    global _simbol_cache, _simbol_lengkap
    if _simbol_cache is None:
        peta, berhasil, gagal = {}, False, 0
        for url, jenis in ((f"{BINANCE}/exchangeInfo?permissions=SPOT", "spot"),
                           ("https://fapi.binance.com/fapi/v1/exchangeInfo", "futures")):
            try:
                with urllib.request.urlopen(
                        urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"}),
                        timeout=60) as r:
                    info = json.load(r)
                for x in info.get("symbols", []):
                    if x.get("status") == "TRADING" and x["symbol"] not in peta:
                        peta[x["symbol"]] = jenis
                berhasil = True
            except Exception as e:  # noqa: BLE001
                gagal += 1
                print(f"  [peringatan] daftar simbol {jenis} gagal: {type(e).__name__}")
        _simbol_lengkap = gagal == 0
        _simbol_cache = peta if berhasil else None
    return _simbol_cache


def pasangan(aset):
    """(simbol, pasar) untuk sebuah aset; (None, None) kalau tidak diperdagangkan.

    Pasarnya ikut dikembalikan karena lilin spot dan futures dilayani endpoint
    yang berbeda - meminta lilin spot untuk simbol futures-saja membalas galat."""
    a = (aset or "").upper().lstrip("$").strip()
    for akhiran in ("USDT", "USDC", "PERP"):
        if len(a) > len(akhiran) and a.endswith(akhiran):
            a = a[: -len(akhiran)]
            break
    a = ALIAS.get(a, a)
    ada = simbol_binance()
    if ada is None:
        return ("?", None)  # daftar simbol tidak terambil; jangan menyimpulkan apa pun
    for kandidat in (a + "USDT", "1000" + a + "USDT", a + "USDC"):
        if kandidat in ada:
            return (kandidat, ada[kandidat])
    # Tidak ketemu. Itu hanya berarti 'tidak diperdagangkan' kalau daftarnya utuh.
    return (None, None) if _simbol_lengkap else ("?", None)


def klines(pair, pasar, mulai_ms, selesai_ms):
    dasar = ("https://fapi.binance.com/fapi/v1" if pasar == "futures" else BINANCE)
    url = (f"{dasar}/klines?symbol={pair}&interval=1h"
           f"&startTime={mulai_ms}&endTime={selesai_ms}&limit=1000")
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        print(f"  [peringatan] lilin {pair} ({pasar}) gagal: HTTP {e.code}")
        return []
    except Exception as e:  # noqa: BLE001
        print(f"  [peringatan] lilin {pair} ({pasar}) gagal: {type(e).__name__}")
        return []


def nilai(call, waktu_ms):
    """Tentukan hasil satu panggilan: TP keberapa yang tersentuh lebih dulu, atau
    SL. Mana yang lebih dulu ditentukan bar demi bar, bukan dari harga tertinggi
    sepanjang periode - kalau SL kena duluan, TP setelahnya tidak dihitung."""
    pair, pasar = pasangan(call["aset"])
    if pair == "?":
        return {"pair": None, "hasil": "daftar simbol tidak terambil", "imbal": None, "tpKe": None}
    if not pair:
        return {"pair": None, "hasil": "tidak ada di Binance", "imbal": None, "tpKe": None}

    selesai = waktu_ms + HORIZON_HARI * 86400_000
    bars = klines(pair, pasar, waktu_ms, min(selesai, int(time.time() * 1000)))
    if not bars:
        return {"pair": pair, "pasar": pasar, "hasil": "harga tidak terambil", "imbal": None, "tpKe": None}

    entry = call["entry"] or float(bars[0][1])  # tanpa entry tertulis: harga buka bar pertama
    naik = call["arah"] == "long"

    # Target hanya sah kalau berada di sisi yang benar terhadap harga masuk:
    # di ATAS entry untuk long, di BAWAH entry untuk short. Tanpa saringan ini,
    # panggilan yang harganya sudah lewat target saat masuk akan langsung
    # tercatat "target tersentuh" padahal merugi - dan win rate ikut naik palsu.
    tps = sorted((n, h) for n, h in call["tp"].items()
                 if (naik and h > entry) or (not naik and h < entry))
    tp_diabaikan = len(call["tp"]) - len(tps)
    sl = call["sl"]
    if sl is not None and ((naik and sl >= entry) or (not naik and sl <= entry)):
        sl = None  # stop di sisi yang salah juga diabaikan
    if not tps and sl is None:
        return {"pair": pair, "pasar": pasar, "hasil": "target tidak valid",
                "imbal": None, "tpKe": None, "entry": entry,
                "tpDiabaikan": tp_diabaikan}

    tp_kena = None
    for b in bars:
        tinggi, rendah = float(b[2]), float(b[3])
        # SL diperiksa lebih dulu di dalam bar yang sama: asumsi konservatif,
        # karena urutan sentuhan di dalam satu jam tidak bisa diketahui.
        if sl is not None and ((naik and rendah <= sl) or (not naik and tinggi >= sl)):
            if tp_kena is None:
                imbal = (sl / entry - 1) * 100 * (1 if naik else -1)
                return {"pair": pair, "pasar": pasar, "hasil": "invalidasi tersentuh",
                        "imbal": round(imbal, 2), "tpKe": None, "entry": entry,
                        "tpDiabaikan": tp_diabaikan}
            break
        for n, harga in tps:
            if (naik and tinggi >= harga) or (not naik and rendah <= harga):
                tp_kena = max(tp_kena or 0, n)
    if tp_kena:
        harga = call["tp"][tp_kena]
        imbal = (harga / entry - 1) * 100 * (1 if naik else -1)
        return {"pair": pair, "pasar": pasar, "hasil": "target tersentuh",
                "imbal": round(imbal, 2), "tpKe": tp_kena, "entry": entry,
                "tpDiabaikan": tp_diabaikan}

    akhir = float(bars[-1][4])
    imbal = (akhir / entry - 1) * 100 * (1 if naik else -1)
    return {"pair": pair, "pasar": pasar, "hasil": "belum tersentuh",
            "imbal": round(imbal, 2), "tpKe": None, "entry": entry,
            "tpDiabaikan": tp_diabaikan}


# ----------------------------------------------------------------------- utama
def pertahankan_hasil_lama(baru):
    """Jangan biarkan penarikan yang gagal menghapus hasil yang sudah benar.

    Satu penarikan yang tidak bisa menghubungi Binance menghasilkan baris tanpa
    harga: tanpa pasangan, tanpa level TP, tanpa imbal. Menulisnya apa adanya
    membuat panggilan yang sudah kena TP 3 berubah jadi 'tak ada data' di layar,
    dan itu persis yang terjadi di produksi. Jadi baris lama yang sudah punya
    hasil dipertahankan, dan penarikan berikutnya yang sehat akan memperbaruinya
    sendiri. Panggilan yang benar-benar baru tetap masuk seperti biasa."""
    if not KELUARAN.exists():
        return baru
    try:
        lama = {b.get("sumber"): b
                for b in json.loads(KELUARAN.read_text(encoding="utf-8")).get("baris", [])
                if b.get("sumber")}
    except Exception as e:  # noqa: BLE001
        print(f"  [peringatan] berkas lama tidak terbaca ({type(e).__name__}), dilewati")
        return baru

    def kosong(b):
        return b.get("pair") in (None, "?")

    hasil, dipertahankan = [], 0
    for b in baru:
        l = lama.get(b.get("sumber"))
        if l and kosong(b) and not kosong(l):
            hasil.append(l)
            dipertahankan += 1
        else:
            hasil.append(b)
    if dipertahankan:
        print(f"  [jaga] {dipertahankan} baris mempertahankan hasil lama "
              f"karena penarikan ini tidak mendapat harga")
    return hasil


def utama():
    token = os.environ.get("DISCORD_BOT_TOKEN", "")
    if not token:
        raise SystemExit("DISCORD_BOT_TOKEN belum diset di environment")

    pr = profil(token)
    pesan = ambil_pesan(token)
    print(f"{len(pesan)} pesan dari {pr['nama']}"
          f"{' (avatar ada)' if pr['avatar'] else ' (tanpa avatar)'}")

    baris = []
    for m in pesan:
        c = urai(m.get("content") or "")
        if not c:
            continue
        waktu = m["timestamp"]
        waktu_ms = ke_ms(waktu)
        h = nilai(c, waktu_ms)
        baris.append({
            "aset": c["aset"], "penulis": pr["nama"], "arah": c["arah"],
            "entry": c["entry"], "masuk": h.get("entry"),
            "target": c["tp"].get(1), "stop": c["sl"],
            "tpSemua": c["tp"], "tpKe": h["tpKe"],
            "pair": h["pair"], "bursa": h.get("pasar"), "hasilAkhir": h["hasil"], "imbal": h["imbal"],
            "tpDiabaikan": h.get("tpDiabaikan", 0),
            "sumberHasil": "harga", "imbalSumber": "harga",
            "waktu": waktu,
            "sumber": f"https://discord.com/channels/{m.get('guild_id','@me')}/{ZORA_CHANNEL}/{m['id']}",
            "kutipan": (m.get("content") or "").split("\n")[1][:160] if "\n" in (m.get("content") or "") else "",
        })
        print(f"  {c['aset']:8} {c['arah']:5} -> {h['hasil']}"
              f"{'' if h['tpKe'] is None else ' TP' + str(h['tpKe'])}"
              f" ({h['imbal']}%)")

    baris = pertahankan_hasil_lama(baris)

    KELUARAN.parent.mkdir(parents=True, exist_ok=True)
    KELUARAN.write_text(json.dumps({
        "nama": pr["nama"], "avatar": pr["avatar"],
        "id": ZORA_USER, "channelId": ZORA_CHANNEL,
        "ditarik": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "jumlahPesan": len(pesan), "baris": baris,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n{len(baris)} panggilan tersimpan ke {KELUARAN}")


# ------------------------------------------------------------------- selftest
def selftest():
    contoh = """Daily Rekom Crypto
$AKE | SPOT/PERPS
Plan: Swing || Long/BUY
Conviction: 70%
Entry: CMP (Current Market Price) or 0,02400
TP 1: 0,02900
TP 2: 0,03300
TP 3: 0,03800
SL: 0,02060 (20%)"""
    c = urai(contoh)
    assert c["aset"] == "AKE", c
    assert c["arah"] == "long", c
    assert abs(c["entry"] - 0.024) < 1e-9, c
    assert c["tp"] == {1: 0.029, 2: 0.033, 3: 0.038}, c
    assert abs(c["sl"] - 0.0206) < 1e-9, c

    # koma sebagai desimal, titik sebagai ribuan
    assert abs(angka("0,02400") - 0.024) < 1e-9
    assert abs(angka("1.000,50") - 1000.5) < 1e-9
    assert abs(angka("986.8") - 986.8) < 1e-9
    assert angka("bukan angka") is None and angka(None) is None

    # pesan tanpa TP/SL bukan panggilan
    assert urai("Daily Rekom Crypto\n$BTC mantap nih") is None
    assert urai("") is None and urai(None) is None

    # short terbaca
    s = urai("$ETH | Plan: Swing || Short/SELL\nEntry: 4000\nTP 1: 3800\nSL: 4200")
    assert s["arah"] == "short" and s["tp"] == {1: 3800.0} and s["sl"] == 4200.0, s

    # SL lebih dulu di bar pertama harus menang atas TP di bar berikutnya
    call = {"aset": "X", "arah": "long", "entry": 100.0, "tp": {1: 120.0}, "sl": 90.0}
    global _simbol_cache
    _simbol_cache = {"XUSDT": "spot"}
    globals()["klines"] = lambda *a, **k: [
        [0, "100", "105", "89", "95", 0],    # SL kena di bar ini
        [0, "95", "130", "94", "125", 0],    # TP kena setelahnya, tidak boleh dihitung
    ]
    h = nilai(call, 0)
    assert h["hasil"] == "invalidasi tersentuh", h
    assert abs(h["imbal"] - (-10.0)) < 1e-9, h
    # Target di sisi yang salah tidak boleh dihitung sebagai kemenangan.
    globals()["klines"] = lambda *a, **k: [[0, "0.0671", "0.080", "0.060", "0.070", 0]]
    _simbol_cache.clear(); _simbol_cache["BULLAUSDT"] = "futures"
    salah = {"aset": "BULLA", "arah": "short", "entry": None,
             "tp": {1: 0.104, 2: 0.09, 3: 0.074}, "sl": 0.1497}
    hs = nilai(salah, 0)
    # Ketiga target ada di sisi yang salah dan diabaikan; stop-nya masih sah
    # (di atas entry untuk short), jadi posisinya belum selesai - bukan menang.
    assert hs["hasil"] == "belum tersentuh", hs
    assert hs["tpDiabaikan"] == 3, hs
    assert hs["tpKe"] is None, hs

    # Short yang benar (target di bawah entry) tetap dinilai untung.
    globals()["klines"] = lambda *a, **k: [[0, "100", "101", "88", "90", 0]]
    _simbol_cache.clear(); _simbol_cache["YUSDT"] = "spot"
    benar = {"aset": "Y", "arah": "short", "entry": 100.0, "tp": {1: 90.0}, "sl": 110.0}
    hb = nilai(benar, 0)
    assert hb["hasil"] == "target tersentuh" and hb["imbal"] == 10.0, hb
    assert hb["tpDiabaikan"] == 0, hb

    # Waktu Discord adalah UTC; hasilnya tidak boleh bergeser oleh zona waktu mesin.
    assert ke_ms("2026-09-18T11:49:11.000000+00:00") == 1789732151000, ke_ms("2026-09-18T11:49:11")
    assert ke_ms("1970-01-01T00:00:00") == 0

    # Daftar simbol yang cuma separuh terambil tidak boleh dipakai untuk
    # menyimpulkan 'tidak diperdagangkan' - inilah yang menghapus hasil aset
    # futures di produksi saat fapi.binance.com tidak bisa dihubungi.
    global _simbol_lengkap
    _simbol_cache.clear(); _simbol_cache["METUSDT"] = "spot"
    _simbol_lengkap = False
    assert pasangan("MET") == ("METUSDT", "spot"), pasangan("MET")
    assert pasangan("ARIA") == ("?", None), pasangan("ARIA")
    _simbol_lengkap = True
    assert pasangan("ARIA") == (None, None), pasangan("ARIA")

    # Penarikan tanpa harga tidak boleh menghapus hasil yang sudah ada.
    import tempfile
    global KELUARAN
    simpan_keluaran = KELUARAN
    with tempfile.TemporaryDirectory() as d:
        KELUARAN = pathlib.Path(d) / "zora.json"
        KELUARAN.write_text(json.dumps({"baris": [
            {"sumber": "m1", "aset": "AKE", "pair": "AKEUSDT", "tpKe": 3, "imbal": 58.33},
        ]}), encoding="utf-8")
        hasil = pertahankan_hasil_lama([
            {"sumber": "m1", "aset": "AKE", "pair": None, "tpKe": None, "imbal": None},
            {"sumber": "m2", "aset": "BARU", "pair": None, "tpKe": None, "imbal": None},
        ])
        assert hasil[0]["tpKe"] == 3, hasil[0]          # hasil lama dipertahankan
        assert hasil[1]["aset"] == "BARU", hasil[1]     # panggilan baru tetap masuk
    KELUARAN = simpan_keluaran

    print("selftest ok: penguraian, angka koma, short, urutan SL-sebelum-TP, "
          "penolakan target salah sisi, waktu UTC, daftar simbol separuh, "
          "dan penjagaan hasil lama")


if __name__ == "__main__":
    selftest() if "--selftest" in sys.argv else utama()
