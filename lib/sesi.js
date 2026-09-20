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

function tandaTangan(pesan, rahasia) {
  return crypto.createHmac("sha256", rahasia).update(String(pesan)).digest("hex");
}

/* Perbandingan tanda tangan yang bertempo tetap. */
function tandaCocok(harapStr, adaStr) {
  const harap = Buffer.from(harapStr, "utf8");
  const ada = Buffer.from(String(adaStr || ""), "utf8");
  if (harap.length !== ada.length) return false;
  return crypto.timingSafeEqual(harap, ada);
}

export function buatTiket() {
  const kedaluwarsa = Math.floor(Date.now() / 1000) + UMUR_SESI;
  return `${kedaluwarsa}.${tandaTangan(kedaluwarsa, sandi())}`;
}

export function tiketSah(tiket) {
  if (!sandi() || !tiket) return false;
  const [kedaluwarsa, tanda] = String(tiket).split(".");
  if (!kedaluwarsa || !tanda) return false;
  if (Number(kedaluwarsa) * 1000 < Date.now()) return false;
  return tandaCocok(tandaTangan(kedaluwarsa, sandi()), tanda);
}

/* ------------------------------------------------------- sesi member Discord
 *
 * Tiket member DITANDATANGANI DENGAN KUNCI BERBEDA dari tiket koreksi, dan itu
 * bukan kerapian belaka: kalau kuncinya sama, cookie member tinggal disalin ke
 * nama cookie "koreksi" dan pemegangnya bisa mengubah hasil call. Kunci yang
 * berbeda membuat kedua tiket tidak pernah bisa saling dipakai.
 *
 * Kuncinya DISCORD_CLIENT_SECRET - yang memang sudah wajib ada untuk OAuth,
 * jadi tidak ada satu pun variabel environment tambahan yang bisa lupa diisi.
 * Efek sampingnya benar: memutar client secret akan mengeluarkan semua orang.
 */
export const NAMA_COOKIE_MEMBER = "member";

function rahasiaMember() {
  return process.env.DISCORD_CLIENT_SECRET || "";
}

export function buatTiketMember(userId) {
  const kedaluwarsa = Math.floor(Date.now() / 1000) + UMUR_SESI;
  const isi = `${kedaluwarsa}.${userId}`;
  return `${isi}.${tandaTangan(isi, rahasiaMember())}`;
}

/* Memulangkan user ID kalau tiketnya sah, atau null. Sengaja BUKAN boolean:
   pemanggilnya masih harus memeriksa role ke Discord, dan untuk itu ia butuh
   tahu ini siapa. Tiket sah sendirian tidak memberi akses apa pun. */
export function memberDariTiket(tiket) {
  if (!rahasiaMember() || !tiket) return null;
  const bagian = String(tiket).split(".");
  if (bagian.length !== 3) return null;
  const [kedaluwarsa, userId, tanda] = bagian;
  if (!kedaluwarsa || !userId || !tanda) return null;
  if (Number(kedaluwarsa) * 1000 < Date.now()) return null;
  if (!tandaCocok(tandaTangan(`${kedaluwarsa}.${userId}`, rahasiaMember()), tanda)) return null;
  return userId;
}
