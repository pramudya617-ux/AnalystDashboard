/* Pembaca status penjadwal untuk halaman.
 *
 * SENGAJA terpisah dari lib/penjadwal.js dan lib/penarik_analis.js: keduanya
 * mengimpor node:child_process, dan begitu halaman mengimpornya, Next menarik
 * modul itu ke bundel klien saat pengembangan lalu gagal dengan
 * "UnhandledSchemeError: node:child_process". Halaman hanya perlu MEMBACA
 * status, bukan kemampuan menjalankan proses - jadi berkasnya dibaca langsung.
 */
import fs from "node:fs";
import path from "node:path";
import { DATA_TULIS } from "./data";

function baca(nama) {
  try {
    return JSON.parse(fs.readFileSync(path.join(DATA_TULIS, nama), "utf8"));
  } catch {
    return {};
  }
}

/* Penanda "sedang berjalan" ditulis penjadwal saat memulai dan dihapus saat
 * selesai. Batas waktu dipakai supaya proses yang mati mendadak tidak membuat
 * statusnya macet di "sedang berjalan" selamanya. */
function berjalan(s, batasMenit) {
  if (!s.berjalanSejak) return false;
  return Date.now() - s.berjalanSejak < batasMenit * 60_000;
}

export function statusPenarikan() {
  const z = baca("jadwal_zora.json");
  const a = baca("jadwal_analis.json");
  return {
    zora: { ...z, sedangJalan: berjalan(z, 10) },
    analis: { ...a, sedangJalan: berjalan(a, 50) },
  };
}
