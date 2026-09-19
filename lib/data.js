/* Lapisan data dashboard analis.
 *
 * Sumber aslinya berkas hasil build dashboard lama (discord_ringkas.json). Berkas
 * itu HANYA DIBACA; dashboard lama tidak pernah ditulis dari sini. Koreksi manual
 * disimpan terpisah di data/koreksi_manual.json milik proyek ini sendiri.
 */
import fs from "node:fs";
import path from "node:path";

const DATA = path.join(process.cwd(), "data");
const RINGKAS = path.join(DATA, "discord_ringkas.json");
const ZORA_FILE = path.join(DATA, "zora.json");
const KOREKSI = path.join(DATA, "koreksi_manual.json");

/* Hasil yang dihitung menang / kalah saat menyusun win rate. Daftar ini disalin
 * apa adanya dari dashboard lama supaya angkanya bisa dibandingkan langsung. */
export const MENANG = ["untung", "target tersentuh"];
export const KALAH = ["rugi", "invalidasi tersentuh"];

/* Alamat segmen koreksi: /rahasia/<token>. Ganti lewat env KOREKSI_TOKEN kalau
 * alamatnya sudah terlanjur diketahui orang lain. */
export const TOKEN_KOREKSI = process.env.KOREKSI_TOKEN || "drc-koreksi-2026";

/* Zora belum ada di berkas lama; dia ditarik terpisah lewat channel-nya sendiri. */
export const ZORA = {
  nama: "Zora",
  id: "1548790432006152202",
  channelId: "1548792499810598932",
};

function bacaJson(file, fallback) {
  try {
    return JSON.parse(fs.readFileSync(file, "utf8"));
  } catch {
    return fallback;
  }
}

export function bacaKoreksi() {
  const k = bacaJson(KOREKSI, {});
  return k && typeof k === "object" ? k : {};
}

export function tulisKoreksi(obj) {
  fs.mkdirSync(DATA, { recursive: true });
  fs.writeFileSync(KOREKSI, JSON.stringify(obj, null, 2), "utf8");
}

/* Kunci sebuah call. Tautan pesan Discord unik per panggilan, jadi dipakai apa
 * adanya; kalau tautannya kosong (data lama), jatuh ke gabungan aset+waktu. */
export function kunciCall(c) {
  return c.sumber || `${c.aset}|${c.waktu}`;
}

/* Rentang waktu untuk dua mode yang diminta:
 *   "6bulan"    - enam bulan terakhir, WR ikut dihitung atas rentang yang sama
 *   "september" - hanya sejak 1 September 2026
 */
export function batasMode(mode, bulanDaftar = []) {
  if (mode === "september") return new Date("2026-09-01T00:00:00Z");
  const kunci = bulanDaftar.map((b) => b.kunci).filter(Boolean).sort();
  const awal = kunci.length >= 6 ? kunci[kunci.length - 6] : kunci[0];
  return awal ? new Date(`${awal}-01T00:00:00Z`) : new Date(0);
}

/* Terapkan koreksi manual ke satu baris call. Koreksi bisa: menandai terhapus,
 * mengganti hasil, atau mengganti persentase imbal. Jejaknya ikut dibawa supaya
 * antarmuka bisa menunjukkan bahwa angka itu hasil koreksi, bukan hitungan mesin. */
function terapkanKoreksi(c, kor) {
  const k = kor[kunciCall(c)];
  if (!k) return { ...c, dikoreksi: false };
  return {
    ...c,
    dihapus: !!k.dihapus,
    hasilAkhir: k.hasil ?? c.hasilAkhir,
    tpKe: k.tpKe !== undefined ? k.tpKe : c.tpKe,
    imbal: k.imbal ?? c.imbal,
    sumberHasil: k.hasil ? "manual" : c.sumberHasil,
    imbalSumber: k.imbal != null ? "manual" : c.imbalSumber,
    dikoreksi: true,
    alasanKoreksi: k.alasan || "",
    waktuKoreksi: k.waktu || "",
  };
}

export function hitungMetrik(calls) {
  const dinilai = calls.filter((c) => MENANG.includes(c.hasilAkhir) || KALAH.includes(c.hasilAkhir));
  const menang = dinilai.filter((c) => MENANG.includes(c.hasilAkhir)).length;
  const berimbal = calls.filter((c) => typeof c.imbal === "number");
  const rata = berimbal.length
    ? berimbal.reduce((s, c) => s + c.imbal, 0) / berimbal.length
    : null;
  return {
    nCall: calls.length,
    nDinilai: dinilai.length,
    menang,
    kalah: dinilai.length - menang,
    wr: dinilai.length ? (menang / dinilai.length) * 100 : null,
    imbalRata: rata,
  };
}

/* Susun seluruh data yang dibutuhkan halaman untuk satu mode rentang waktu. */
export function muatDashboard(mode = "6bulan") {
  const d = bacaJson(RINGKAS, { analis: [], baris: [], bulan: [], harian: {} });
  const kor = bacaKoreksi();
  const batas = batasMode(mode, d.bulan || []);

  /* Zora ditarik terpisah oleh tarik_zora.py karena formatnya pasti dan tidak
     butuh LLM. Barisnya melewati saringan koreksi dan rentang yang sama. */
  const z = bacaJson(ZORA_FILE, null);
  const barisMentah = [...(d.baris || []), ...((z && z.baris) || [])];

  const semuaBaris = barisMentah
    .map((c) => terapkanKoreksi(c, kor))
    .filter((c) => !c.dihapus)
    .filter((c) => (c.waktu ? new Date(c.waktu) >= batas : true));

  const daftarAnalis = [...(d.analis || [])];
  if (z) {
    daftarAnalis.push({
      id: z.id, nama: z.nama, avatar: z.avatar || null, bot: false,
      kanal: [`channel ${z.channelId}`], jumlah: z.jumlahPesan || 0,
      ringkasan: "", ringkasanDulu: false, ditarik: z.ditarik || null,
    });
  }

  const analis = daftarAnalis.map((a) => {
    /* Anthony dan Jaxx tampil sebagai ringkasan obrolan saja - riwayat panggilan
     * mereka sengaja tidak ditampilkan, sesuai penanda ringkasanDulu. */
    const ringkasanSaja = !!a.ringkasanDulu;
    const calls = ringkasanSaja
      ? []
      : semuaBaris.filter((c) => (c.penulis || "").toLowerCase() === (a.nama || "").toLowerCase());
    return {
      id: a.id,
      nama: a.nama,
      avatar: a.avatar || null,
      bot: !!a.bot,
      kanal: a.kanal || [],
      jumlahPesan: a.jumlah || 0,
      ringkasan: a.ringkasan || "",
      dari: a.dari || null,
      sampai: a.sampai || null,
      ringkasanSaja,
      ditarik: a.ditarik || null,
      calls,
      metrik: ringkasanSaja ? null : hitungMetrik(calls),
    };
  });

  return {
    dibuat: d.dibuat || null,
    mode,
    batas: batas.toISOString(),
    bulan: d.bulan || [],
    harian: d.harian || {},
    analis,
    /* Hanya panggilan yang benar-benar bisa dilihat. Memakai semuaBaris.length
       akan ikut menghitung milik Jaxx dan Anthony, yang segmennya sengaja berupa
       ringkasan obrolan - angka yang menghitung hal tersembunyi itu menyesatkan. */
    totalCall: analis.reduce((n, a) => n + a.calls.length, 0),
    jumlahKoreksi: Object.keys(kor).length,
  };
}
