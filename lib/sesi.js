/* Sesi halaman koreksi.
 *
 * Meniru serve.py dashboard lama: sandi hanya hidup di environment, tidak pernah
 * masuk kode atau repo, dan perbandingannya bertempo tetap supaya lama
 * pemeriksaan tidak bocor lewat waktu balasan.
 *
 * Bedanya, cookie di sini DITANDATANGANI (HMAC) alih-alih disimpan di memori
 * server. Daftar sesi di memori akan hangus tiap kali Next.js memuat ulang modul
 * saat pengembangan, dan itu membuat pengguna terlempar keluar tanpa sebab.
 */
import crypto from "node:crypto";

export const NAMA_COOKIE = "koreksi";
export const UMUR_SESI = 12 * 3600; // detik, sama seperti dashboard lama

export function sandi() {
  return process.env.KOREKSI_SANDI || "";
}

/* Perbandingan bertempo tetap. Panjang yang berbeda harus ditangani lebih dulu
 * karena timingSafeEqual melempar galat kalau panjangnya tidak sama. */
export function sandiCocok(diberikan) {
  const asli = sandi();
  if (!asli) return false;
  const a = Buffer.from(String(diberikan || ""), "utf8");
  const b = Buffer.from(asli, "utf8");
  if (a.length !== b.length) {
    crypto.timingSafeEqual(b, b); // tetap bekerja supaya waktunya seragam
    return false;
  }
  return crypto.timingSafeEqual(a, b);
}

function tandaTangan(kedaluwarsa) {
  return crypto.createHmac("sha256", sandi()).update(String(kedaluwarsa)).digest("hex");
}

export function buatTiket() {
  const kedaluwarsa = Math.floor(Date.now() / 1000) + UMUR_SESI;
  return `${kedaluwarsa}.${tandaTangan(kedaluwarsa)}`;
}

export function tiketSah(tiket) {
  if (!sandi() || !tiket) return false;
  const [kedaluwarsa, tanda] = String(tiket).split(".");
  if (!kedaluwarsa || !tanda) return false;
  if (Number(kedaluwarsa) * 1000 < Date.now()) return false;

  const harap = Buffer.from(tandaTangan(kedaluwarsa), "utf8");
  const ada = Buffer.from(tanda, "utf8");
  if (harap.length !== ada.length) return false;
  return crypto.timingSafeEqual(harap, ada);
}
