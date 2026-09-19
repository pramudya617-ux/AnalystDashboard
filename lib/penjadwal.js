/* Penjadwal penarikan Zora.
 *
 * Polanya meniru penjadwal.py dashboard lama, dengan aturan yang sama:
 *
 *   1. Satu pekerjaan pada satu waktu. Dua penarikan sekaligus menulis berkas
 *      yang sama dan berbagi kuota API yang sama.
 *   2. Kunci yang tidak ada berarti DILEWATI, bukan gagal berulang. Tanpa
 *      DISCORD_BOT_TOKEN penarikan tidak akan pernah berhasil, jadi mencobanya
 *      tiap jam hanya mengotori log.
 *   3. Jam terakhir jalan disimpan ke berkas. Server dimulai ulang jauh lebih
 *      sering daripada yang disangka orang - saat pengembangan bahkan tiap kali
 *      berkas diubah - dan tanpa ini tiap restart memicu penarikan baru.
 */
import fs from "node:fs";
import path from "node:path";
import { execFile } from "node:child_process";
import { promisify } from "node:util";

const jalankan = promisify(execFile);

const DATA = path.join(process.cwd(), "data");
const BERKAS = path.join(DATA, "jadwal_zora.json");

/* 30 menit. Penarikannya ringan - belasan pesan Discord plus beberapa panggilan
   klines - jadi jarak sependek ini tidak membebani kuota API mana pun. */
const JEDA_MENIT = Number(process.env.ZORA_JEDA_MENIT || 30);
const PERIKSA_MENIT = 5; // seberapa sering jatuh tempo diperiksa

let sedangJalan = false;

function baca() {
  try {
    return JSON.parse(fs.readFileSync(BERKAS, "utf8"));
  } catch {
    return {};
  }
}

function simpan(d) {
  try {
    fs.mkdirSync(DATA, { recursive: true });
    fs.writeFileSync(BERKAS, JSON.stringify(d, null, 2), "utf8");
  } catch (e) {
    console.warn("[zora] status jadwal gagal disimpan:", e.message);
  }
}

export function statusJadwal() {
  const s = baca();
  return {
    terakhir: s.terakhir || null,
    hasil: s.hasil || null,
    galat: s.galat || null,
    jedaMenit: JEDA_MENIT,
    sedangJalan,
  };
}

function jatuhTempo() {
  const s = baca();
  if (!s.terakhir) return true;
  return Date.now() - s.terakhir >= JEDA_MENIT * 60_000;
}

export async function tarikSekarang(alasan = "jadwal") {
  if (sedangJalan) return { lewat: "sedang berjalan" };
  if (!process.env.DISCORD_BOT_TOKEN) {
    return { lewat: "DISCORD_BOT_TOKEN tidak ada" };
  }

  sedangJalan = true;
  const mulai = Date.now();
  try {
    const { stdout } = await jalankan("python", ["tarik_zora.py"], {
      cwd: process.cwd(),
      env: { ...process.env, PYTHONIOENCODING: "utf-8" },
      timeout: 280000,
      maxBuffer: 4 * 1024 * 1024,
    });
    const baris = stdout.trim().split("\n");
    const hasil = baris[baris.length - 1] || "selesai";
    simpan({ terakhir: Date.now(), hasil, detik: (Date.now() - mulai) / 1000 });
    console.log(`[zora] penarikan ${alasan} selesai: ${hasil}`);
    return { ok: true, hasil };
  } catch (e) {
    const galat = (e.stderr || e.message || "gagal").slice(0, 300);
    /* Waktu terakhir tetap dicatat meski gagal, supaya kegagalan yang menetap
       (mis. channel dicabut izinnya) tidak memicu percobaan tiap sepuluh menit. */
    simpan({ terakhir: Date.now(), galat });
    console.warn(`[zora] penarikan ${alasan} gagal: ${galat}`);
    return { error: galat };
  } finally {
    sedangJalan = false;
  }
}

export function mulaiPenjadwal() {
  if (!process.env.DISCORD_BOT_TOKEN) {
    console.log("[zora] penjadwal dilewati: DISCORD_BOT_TOKEN tidak ada");
    return;
  }

  const periksa = () => {
    if (jatuhTempo()) tarikSekarang("jadwal").catch(() => {});
  };

  /* Jeda kecil di awal supaya penarikan tidak beradu dengan proses startup
     server saat halaman pertama sedang dikompilasi. */
  setTimeout(periksa, 8000);
  const t = setInterval(periksa, PERIKSA_MENIT * 60_000);
  t.unref?.(); // jangan menahan proses tetap hidup hanya karena timer ini
  console.log(`[zora] penjadwal aktif, tiap ${JEDA_MENIT} menit`);
}
