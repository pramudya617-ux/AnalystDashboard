import { NextResponse } from "next/server";
import { cookies } from "next/headers";
import { bacaKoreksi, tulisKoreksi } from "@/lib/data";
import { NAMA_COOKIE, sandi, tiketSah } from "@/lib/sesi";

/* Koreksi manual disimpan di berkas proyek INI (data/koreksi_manual.json, atau
 * volume kalau DATA_DIR diset). Berkas dashboard lama tidak pernah ditulis dari
 * sini.
 *
 * Tiap koreksi wajib menyertakan alasan dan dicap waktu, supaya perubahan angka
 * selalu bisa ditelusuri dan tidak menjadi keputusan tanpa jejak.
 *
 * WAJIB BERSESI. Rute ini sempat terbuka tanpa pemeriksaan apa pun: halaman
 * /koreksi meminta sandi, tapi API di belakangnya tidak, sehingga siapa pun yang
 * tahu alamatnya bisa mengubah hasil call, mengganti persentase, atau
 * menyembunyikan baris di dashboard yang sudah tayang. Penjagaan pintu depan
 * tidak ada gunanya kalau pintu belakangnya terbuka.
 */
async function ditolak() {
  if (!sandi()) return new NextResponse("Not found", { status: 404 });
  const jar = await cookies();
  if (!tiketSah(jar.get(NAMA_COOKIE)?.value)) {
    return NextResponse.json(
      { error: "Perlu masuk dulu lewat halaman /koreksi" },
      { status: 401 }
    );
  }
  return null;
}

export async function POST(req) {
  const tolak = await ditolak();
  if (tolak) return tolak;

  let body;
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ error: "body bukan JSON" }, { status: 400 });
  }

  const { kunci, hasil, tpKe, imbal, alasan, dihapus } = body || {};
  if (!kunci) return NextResponse.json({ error: "kunci call wajib diisi" }, { status: 400 });

  /* Minimal empat karakter, mengikuti aturan alat koreksi dashboard lama:
     maksudnya alasan yang sungguhan, bukan satu ketukan asal supaya lolos. */
  if (!alasan || String(alasan).trim().length < 4) {
    return NextResponse.json(
      { error: "alasan koreksi wajib diisi, minimal 4 karakter" },
      { status: 400 }
    );
  }

  const kor = bacaKoreksi();
  const lama = kor[kunci] || {};
  const baru = { ...lama, alasan: String(alasan).trim(), waktu: new Date().toISOString() };

  if (dihapus !== undefined) baru.dihapus = !!dihapus;
  if (hasil !== undefined && hasil !== null && hasil !== "") baru.hasil = String(hasil);
  /* null dipakai untuk MENGOSONGKAN level TP (mis. saat hasilnya diubah jadi SL),
     jadi null harus dibedakan dari undefined yang berarti "jangan diutak-atik". */
  if (tpKe !== undefined) baru.tpKe = tpKe === null || tpKe === "" ? null : String(tpKe);
  if (imbal !== undefined && imbal !== null && imbal !== "") {
    const n = Number(imbal);
    if (!Number.isFinite(n)) return NextResponse.json({ error: "persentase tidak valid" }, { status: 400 });
    baru.imbal = n;
  }

  kor[kunci] = baru;
  tulisKoreksi(kor);
  return NextResponse.json({ ok: true, kunci, koreksi: baru });
}

/* Batalkan koreksi: kembalikan call ke angka asli hasil hitungan mesin. */
export async function DELETE(req) {
  const tolak = await ditolak();
  if (tolak) return tolak;

  const kunci = new URL(req.url).searchParams.get("kunci");
  if (!kunci) return NextResponse.json({ error: "kunci call wajib diisi" }, { status: 400 });
  const kor = bacaKoreksi();
  if (!(kunci in kor)) return NextResponse.json({ error: "koreksi tidak ditemukan" }, { status: 404 });
  delete kor[kunci];
  tulisKoreksi(kor);
  return NextResponse.json({ ok: true, kunci });
}
