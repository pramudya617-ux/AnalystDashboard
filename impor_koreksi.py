"""Impor koreksi manual dari dashboard lama (yang berjalan di Railway).

KENAPA PERLU ALAT INI:

  Dashboard lama menyimpan koreksinya dengan KUNCI dan KOSAKATA yang berbeda:

    lama  : {"<id pesan Discord>": {"klaim": "diaku TP kena", "tpKe": "TP2",
                                    "catatan": "...", "pada": "..."}}
    baru  : {"<tautan pesan Discord>": {"hasil": "target tersentuh",
                                        "tpKe": "TP2", "alasan": "...",
                                        "waktu": "..."}}

  Untungnya kuncinya bisa dipetakan PERSIS: id_pesan() di alat lama mengambil
  potongan terakhir tautan Discord, jadi id lama = ekor tautan baru. Tidak ada
  pencocokan kira-kira berdasarkan aset dan jam.

CARA MENGAMBIL BERKAS LAMANYA:

  Koreksi yang dibuat lewat halaman web tersimpan di VOLUME Railway, bukan di
  repo, dan tidak ada rute HTTP yang mengeluarkannya (/koreksi/status hanya
  melaporkan status pekerjaan latar). Jadi ambil lewat Railway CLI:

      railway ssh
      cat $DATA_DIR/koreksi_manual.json

  Simpan isinya ke sebuah berkas, lalu jalankan:

      python impor_koreksi.py koreksi_lama.json

Uji tanpa berkas:  python impor_koreksi.py --selftest
"""
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
TUJUAN = HERE / "data" / "koreksi_manual.json"
RINGKAS = HERE / "data" / "discord_ringkas.json"
ZORA = HERE / "data" / "zora.json"

# Kosakata alat lama -> kosakata proyek ini.
KLAIM = {
    "diaku TP kena": "target tersentuh",
    "diaku kena stop": "invalidasi tersentuh",
    "diaku BE": "impas",
    "diaku ditutup": "ditutup",
}


def peta_tautan():
    """id pesan Discord -> tautan lengkapnya, dari seluruh panggilan yang ada."""
    peta = {}
    for berkas in (RINGKAS, ZORA):
        try:
            d = json.loads(berkas.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
        for b in d.get("baris", []):
            s = b.get("sumber") or ""
            if s:
                peta[s.rsplit("/", 1)[-1]] = s
    return peta


def ubah(lama, peta):
    """Kembalikan (koreksi_baru, tak_dikenal, tanpa_pasangan)."""
    baru, tak_dikenal, tanpa_pasangan = {}, [], []

    for pid, v in (lama or {}).items():
        tautan = peta.get(pid)
        if not tautan:
            # Panggilannya tidak ada di data proyek ini - mungkin di luar rentang
            # enam bulan, atau milik analis yang tidak ikut disalin.
            tanpa_pasangan.append(pid)
            continue

        alasan = (v.get("catatan") or "").strip() or "diimpor dari dashboard lama"
        waktu = v.get("pada") or ""

        if v.get("hapus"):
            baru[tautan] = {"dihapus": True, "alasan": alasan, "waktu": waktu}
            continue

        hasil = KLAIM.get(v.get("klaim"))
        if not hasil:
            tak_dikenal.append((pid, v.get("klaim")))
            continue

        rekam = {"hasil": hasil, "alasan": alasan, "waktu": waktu}
        # tpKe hanya bermakna untuk target yang tersentuh. Spasinya dirapikan
        # karena data lama memuat "TP1" DAN "TP 1" untuk hal yang sama, dan dua
        # gaya penulisan di kolom yang sama terlihat seperti dua hal berbeda.
        if hasil == "target tersentuh" and v.get("tpKe"):
            rapi = " ".join(str(v["tpKe"]).split())
            if rapi.upper().startswith("TP ") and rapi[3:].strip().isdigit():
                rapi = "TP" + rapi[3:].strip()
            rekam["tpKe"] = rapi
        baru[tautan] = rekam

    return baru, tak_dikenal, tanpa_pasangan


def utama(sumber):
    lama = json.loads(pathlib.Path(sumber).read_text(encoding="utf-8"))
    peta = peta_tautan()
    baru, tak_dikenal, tanpa_pasangan = ubah(lama, peta)

    ada = {}
    if TUJUAN.exists():
        try:
            ada = json.loads(TUJUAN.read_text(encoding="utf-8")) or {}
        except Exception:  # noqa: BLE001
            ada = {}

    # Koreksi yang sudah ada di proyek ini TIDAK ditimpa: yang dibuat di sini
    # lebih baru daripada yang diimpor, dan menimpanya diam-diam akan membuang
    # pekerjaan tanpa jejak.
    ditambah = {k: v for k, v in baru.items() if k not in ada}
    ada.update(ditambah)

    TUJUAN.parent.mkdir(parents=True, exist_ok=True)
    TUJUAN.write_text(json.dumps(ada, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"dibaca dari lama   : {len(lama)}")
    print(f"cocok & diimpor    : {len(ditambah)}")
    print(f"sudah ada, dilewati: {len(baru) - len(ditambah)}")
    print(f"tanpa pasangan     : {len(tanpa_pasangan)}")
    if tak_dikenal:
        print(f"klaim tak dikenal  : {tak_dikenal[:5]}")
    print(f"total koreksi kini : {len(ada)} -> {TUJUAN}")


def selftest():
    # 555 SENGAJA dimasukkan ke peta: pencarian tautan terjadi lebih dulu, jadi
    # tanpa ini ia tersaring sebagai "tanpa pasangan" dan klaim tak dikenalnya
    # tidak pernah teruji.
    peta = {"999": "https://discord.com/channels/1/2/999",
            "888": "https://discord.com/channels/1/2/888",
            "777": "https://discord.com/channels/1/2/777",
            "555": "https://discord.com/channels/1/2/555"}
    lama = {
        "999": {"klaim": "diaku TP kena", "tpKe": "TP2", "catatan": "analis tutup di TP2",
                "pada": "2026-09-01T00:00:00Z"},
        "888": {"hapus": True, "catatan": "panggilan kembar", "pada": "2026-09-02T00:00:00Z"},
        "777": {"klaim": "diaku kena stop", "catatan": "kena stop", "pada": "2026-09-03T00:00:00Z"},
        "666": {"klaim": "diaku BE", "catatan": "di luar rentang", "pada": "2026-09-04T00:00:00Z"},
        "555": {"klaim": "entah apa", "catatan": "tidak dikenal", "pada": "2026-09-05T00:00:00Z"},
    }
    baru, tak_dikenal, tanpa_pasangan = ubah(lama, peta)

    assert baru[peta["999"]] == {"hasil": "target tersentuh", "alasan": "analis tutup di TP2",
                                 "waktu": "2026-09-01T00:00:00Z", "tpKe": "TP2"}, baru[peta["999"]]
    assert baru[peta["888"]]["dihapus"] is True
    assert baru[peta["777"]]["hasil"] == "invalidasi tersentuh"
    assert "tpKe" not in baru[peta["777"]]          # level TP tak bermakna untuk stop
    assert tanpa_pasangan == ["666"], tanpa_pasangan  # tidak ada di data proyek ini
    assert tak_dikenal == [("555", "entah apa")], tak_dikenal
    assert len(baru) == 3

    # "TP 1" dan "TP1" adalah hal yang sama; penulisannya harus seragam
    b3, _, _ = ubah({"999": {"klaim": "diaku TP kena", "tpKe": "TP 1", "catatan": "x"}}, peta)
    assert b3[peta["999"]]["tpKe"] == "TP1", b3[peta["999"]]
    b4, _, _ = ubah({"999": {"klaim": "diaku TP kena", "tpKe": "Full TP", "catatan": "x"}}, peta)
    assert b4[peta["999"]]["tpKe"] == "Full TP", b4[peta["999"]]

    # catatan kosong tetap menghasilkan alasan, karena alasan wajib ada
    b2, _, _ = ubah({"999": {"klaim": "diaku BE", "catatan": "  "}}, peta)
    assert b2[peta["999"]]["alasan"] == "diimpor dari dashboard lama"
    print("selftest ok: pemetaan kunci, kosakata klaim, hapus, dan alasan kosong")


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        selftest()
    elif len(sys.argv) > 1:
        utama(sys.argv[1])
    else:
        raise SystemExit("pakai: python impor_koreksi.py <koreksi_lama.json>")
