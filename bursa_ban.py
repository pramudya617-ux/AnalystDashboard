"""Pelacak ban Binance, dipakai bersama fetch_discord.py dan tarik_zora.py.

KENAPA ADA

    Binance membalas HTTP 418 ketika sebuah IP terlalu sering melanggar batas
    laju, dan balasannya menyebut sampai kapan:

        {"code":-1003,"msg":"Way too many requests; IP(208.77.246.133)
         banned until 1791391775197. Please use the websocket ..."}

    Durasi ban itu NAIK untuk pelanggar berulang. Tanpa berkas ini, penarikan
    harian tetap menghantam host yang sedang diblokir, ban-nya diperpanjang,
    lalu besoknya diulang - lingkaran yang memberi makan dirinya sendiri. Itu
    yang terjadi di produksi: data analis membeku 18 hari, dan tiap penarikan
    justru memperpanjang sebabnya.

    Jadi "sampai kapan" itu DISIMPAN, dan selama belum lewat, permintaan ke host
    itu ditolak di sini - tanpa menyentuh jaringan sama sekali.

PER HOST, BUKAN SATU TANDA UNTUK SEMUA

    api.binance.com dan fapi.binance.com punya jatah laju SENDIRI-SENDIRI. Di
    produksi hanya fapi yang terkena, sementara spot melayani 196 dari 252 baris
    dengan normal. Satu tanda untuk semua akan membuang 196 baris sehat itu
    tanpa alasan.

Simpanannya ikut DATA_DIR supaya selamat dari redeploy; tanpa itu tiap deploy
melupakan ban yang sedang berjalan dan lingkarannya dimulai lagi.
"""
import json
import os
import re
import time
import urllib.parse
from pathlib import Path

_HERE = Path(__file__).resolve().parent

# "banned until 1791391775197" - milidetik sejak epoch
RE_SAMPAI = re.compile(r"banned until (\d{10,16})")

# Kalau Binance menolak tanpa menyebut sampai kapan. Lima belas menit: cukup
# lama untuk melewati jendela batas laju, cukup pendek untuk tidak membuang
# penarikan sehari penuh karena satu gangguan sesaat.
JEDA_BAWAAN = 15 * 60


class Diblokir(RuntimeError):
    """Permintaan tidak dikirim karena host-nya sedang kena ban."""


def _berkas():
    d = os.environ.get("DATA_DIR")
    dasar = Path(d) if d and Path(d).is_dir() else _HERE / "data"
    return dasar / "bursa_ban.json"


def _muat():
    try:
        return json.loads(_berkas().read_text(encoding="utf-8"))
    except Exception:                                        # noqa: BLE001
        return {}


def _simpan(d):
    """Gagal menyimpan TIDAK boleh menggagalkan penarikan.

    Dipanggil dari beberapa thread sekaligus, tapi hanya saat kena 418 - jadi
    praktis tidak pernah berebut. Kalau pun tulisannya robek, _muat() memulangkan
    {} dan yang terjadi cuma satu permintaan sia-sia, bukan data yang rusak.
    """
    try:
        f = _berkas()
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(json.dumps(d, indent=1), encoding="utf-8")
    except Exception:                                        # noqa: BLE001
        pass


def _host(url):
    return (urllib.parse.urlsplit(url).hostname or "").lower()


def _diawasi(h):
    return h.endswith("binance.com") or h.endswith("binance.vision")


def sisa(url, sekarang=None):
    """Detik sebelum host url boleh dihubungi lagi. Nol berarti boleh."""
    h = _host(url)
    if not _diawasi(h):
        return 0
    sampai = _muat().get(h) or 0
    return max(0, int(sampai - (sekarang if sekarang is not None else time.time())))


def periksa(url):
    """Melempar Diblokir kalau host-nya sedang kena ban."""
    d = sisa(url)
    if d:
        raise Diblokir(f"{_host(url)} diblokir Binance, {d // 60} menit {d % 60} detik lagi")


def catat(url, galat):
    """Rekam ban dari HTTPError 418/429. Aman dipanggil untuk galat apa pun.

    Memulangkan detik ban yang tercatat, atau 0 kalau bukan ban.
    """
    h = _host(url)
    if not _diawasi(h) or getattr(galat, "code", None) not in (418, 429):
        return 0
    try:
        isi = galat.read().decode("utf-8", "replace")
    except Exception:                                        # noqa: BLE001
        isi = ""
    m = RE_SAMPAI.search(isi)
    sampai = int(m.group(1)) / 1000 if m else time.time() + JEDA_BAWAAN

    d = _muat()
    # Ban yang lebih lama menang: balasan kemudian bisa menyebut tenggat yang
    # lebih pendek, dan memakainya akan melepas blokir terlalu cepat.
    d[h] = max(sampai, d.get(h) or 0)
    _simpan(d)
    print(f"  [ban] {h} diblokir Binance sampai "
          f"{time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime(d[h]))} UTC - "
          f"permintaan ke host ini dilewati sampai saat itu")
    return int(d[h] - time.time())


def _uji():
    """python bursa_ban.py --uji"""
    import tempfile

    with tempfile.TemporaryDirectory() as t:
        os.environ["DATA_DIR"] = t

        class Palsu(Exception):
            def __init__(self, code, isi):
                self.code = code
                self._isi = isi.encode()

            def read(self):
                return self._isi

        F = "https://fapi.binance.com/fapi/v1/klines?symbol=BTCUSDT"
        S = "https://api.binance.com/api/v3/klines?symbol=BTCUSDT"

        assert sisa(F) == 0, "belum ada ban, harus boleh"

        sampai = int((time.time() + 600) * 1000)
        catat(F, Palsu(418, f'{{"code":-1003,"msg":"Way too many requests; '
                            f'IP(1.2.3.4) banned until {sampai}."}}'))

        assert 500 < sisa(F) <= 600, f"sisa ban meleset: {sisa(F)}"
        assert sisa(S) == 0, "ban fapi TIDAK boleh ikut memblokir spot"

        try:
            periksa(F)
            raise AssertionError("periksa() harus melempar untuk host yang kena ban")
        except Diblokir:
            pass
        periksa(S)                      # tidak boleh melempar

        # tenggat lebih pendek tidak boleh memperpendek ban yang sudah ada
        catat(F, Palsu(418, f'{{"msg":"banned until {int((time.time() + 60) * 1000)}."}}'))
        assert sisa(F) > 500, "ban yang lebih lama harus menang"

        # 418 tanpa tenggat -> pakai jeda bawaan
        os.environ["DATA_DIR"] = t + "x"
        Path(t + "x").mkdir()
        catat(F, Palsu(418, "ditolak tanpa keterangan"))
        assert JEDA_BAWAAN - 5 <= sisa(F) <= JEDA_BAWAAN, f"jeda bawaan meleset: {sisa(F)}"

        # galat yang bukan ban tidak boleh memblokir apa pun
        os.environ["DATA_DIR"] = t
        assert catat(F, Palsu(500, "galat server")) == 0
        assert catat("https://discord.com/api", Palsu(418, "x")) == 0, \
            "host di luar Binance tidak diawasi"

    print("bursa_ban: semua pemeriksaan lolos")


if __name__ == "__main__":
    import sys
    if "--uji" in sys.argv:
        _uji()
    else:
        d = _muat()
        if not d:
            print(f"{_berkas()}: tidak ada ban tercatat")
        for h, sampai in d.items():
            s = int(sampai - time.time())
            print(f"{h:28} {'bebas' if s <= 0 else f'diblokir {s // 60} menit lagi'}")
