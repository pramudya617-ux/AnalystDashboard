"""Memuat .env di folder proyek, dipakai bersama semua skrip di sini.

KENAPA ADA
    Variabel environment hanya diwarisi proses yang dijalankan dari terminal
    yang sama. Server atau skrip yang diluncurkan alat lain — peluncur IDE,
    panel pratinjau, penjadwal — kerap memulai dari environment bersih, dan di
    situ semua kunci hilang tanpa jejak selain "birdeye: false".

    Dulu hanya serve.py yang memuatnya. Akibatnya kunci yang ditaruh di .env
    terlihat oleh server tetapi TIDAK oleh fetch_discord.py maupun
    baca_kartu.py — kegagalan yang membingungkan karena separuh sistem bekerja.

DUA CARA MENYIMPAN KUNCI, DAN BEDANYA
    setx NAMA "nilai"   -> tingkat PENGGUNA, berlaku untuk SEMUA proyek di
                           mesin ini. Menjalankannya lagi akan MENIMPA nilai
                           lama, termasuk milik proyek lain.
    .env di folder ini  -> hanya proyek ini. Tidak menyentuh proyek lain.

    Environment asli selalu menang atas .env (setdefault, bukan penimpaan),
    jadi kalau keduanya ada, yang dari setx yang dipakai.

BERKAS .env TIDAK DIBUAT OTOMATIS. Menaruh rahasia di dalam folder proyek
adalah keputusan Anda, bukan keputusan skrip ini. serve.py sudah memblokir
akses HTTP ke dotfile, tetapi berkas itu tetap ada di disk.
"""
import os
from pathlib import Path

HERE = Path(__file__).resolve().parent


def muat(berkas=None):
    """Isi environment dari .env; nilai yang sudah ada tidak ditimpa."""
    f = Path(berkas) if berkas else HERE / ".env"
    if not f.exists():
        return 0
    n = 0
    for baris in f.read_text(encoding="utf-8").splitlines():
        baris = baris.strip()
        if not baris or baris.startswith("#") or "=" not in baris:
            continue
        k, v = baris.split("=", 1)
        k, v = k.strip(), v.strip().strip('"').strip("'")
        if k and v and k not in os.environ:
            os.environ[k] = v
            n += 1
    return n


muat()


def _demo():
    """Pemeriksaan mandiri: environment asli harus menang atas .env."""
    import tempfile
    os.environ["UJI_ENV_ADA"] = "asli"
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / ".env"
        p.write_text('UJI_ENV_ADA=dari_env\n'
                     'UJI_ENV_BARU="dari_env"\n'
                     '# komentar diabaikan\n'
                     'tanpa_sama_dengan\n', encoding="utf-8")
        muat(p)
    assert os.environ["UJI_ENV_ADA"] == "asli", "nilai asli tidak boleh tertimpa"
    assert os.environ["UJI_ENV_BARU"] == "dari_env", "nilai baru harus terisi"
    print("env_lokal ok — environment asli menang, kutip dan komentar ditangani")


if __name__ == "__main__":
    import sys
    if "--demo" in sys.argv:
        _demo()
    else:
        f = HERE / ".env"
        print(f"{f}: {'ada' if f.exists() else 'tidak ada'}")
        for k in ("GEMINI_API_KEY", "LLM_KEY", "LLM_MODEL", "DISCORD_BOT_TOKEN",
                  "BIRDEYE_API_KEY", "HELIUS_API_KEY"):
            v = os.environ.get(k, "")
            print(f"  {k:20} {'terisi (' + str(len(v)) + ' karakter)' if v else 'kosong'}")


# --------------------------------------------------------------- koreksi
import os as _os                            # noqa: E402
from pathlib import Path as _Path            # noqa: E402
import json as _json                         # noqa: E402

_HERE = _Path(__file__).resolve().parent


def berkas_koreksi():
    """Tempat koreksi manual disimpan saat MENULIS.

    Cakram kontainer Railway sementara, dan penjadwal membangun ulang
    discord_ringkas.json dari nol tiap hari, jadi apa pun yang ditulis ke
    folder aplikasi akan hilang pada deploy berikutnya tanpa bunyi. DATA_DIR
    menunjuk ke volume permanen Railway; tanpa itu, dipakai folder repo seperti
    biasa di laptop.
    """
    d = _os.environ.get("DATA_DIR")
    if d and _Path(d).is_dir():
        return _Path(d) / "koreksi_manual.json"
    return _HERE / "koreksi_manual.json"


def muat_koreksi():
    """Gabungan koreksi dari repo dan dari volume.

    Keduanya dibaca, bukan salah satu: koreksi lewat halaman web tersimpan di
    volume, sedangkan koreksi lewat alat lokal ikut repo. Kalau hanya satu yang
    dibaca, salah satu jalur akan tampak tidak berpengaruh dan itu jenis
    kebingungan yang mahal. Volume menang kalau id-nya sama, karena itu yang
    paling baru disunting.
    """
    out = {}
    for f in (_HERE / "koreksi_manual.json", berkas_koreksi()):
        try:
            if f.exists():
                out.update(_json.loads(f.read_text(encoding="utf-8")) or {})
        except Exception:                                    # noqa: BLE001
            pass
    return out
