/* Penarikan analis (Neil, Lynx, Jaxx, Anthony) lewat fetch_discord.py.
 *
 * DIJAGA KETAT, dan ini bukan kehati-hatian berlebihan: penarikan ini pernah
 * memangkas data dari 245 baris dan 4 analis menjadi 198 baris dan 2 analis
 * ketika dijalankan dengan argumen keliru, dan hanya bisa dipulihkan karena
 * berkasnya kebetulan ada di git. Di server tidak ada git, dan tidak ada yang
 * menonton. Jadi:
 *
 *   1. Isi lama disalin ke .bak SEBELUM penarikan.
 *   2. Hasilnya diperiksa. Kalau jumlah analis menyusut atau barisnya anjlok,
 *      hasilnya DITOLAK dan cadangannya dikembalikan.
 *   3. Jendela selalu enam bulan penuh; bawaan skrip cuma 24 jam, dan itu yang
 *      dulu menghapus analis yang kebetulan sedang tidak menulis.
 */

/* Modul Node dimuat lewat require yang DISEMBUNYIKAN dari webpack.
 *
 * Next mengompilasi instrumentation.js untuk semua runtime termasuk bundel
 * klien, dan webpack menolak impor "node:*" di sana dengan UnhandledSchemeError
 * - meski kodenya tidak pernah benar-benar berjalan di peramban. Alias resolve
 * dan impor dinamis sama-sama tidak menolong karena keduanya masih ditelusuri
 * secara statis. eval("require") tidak bisa ditelusuri, jadi modul ini lewat
 * begitu saja di sisi klien dan tetap utuh di sisi server.
 */
const _req = eval("require");
const fs = _req("fs");
const path = _req("path");

/* Tidak mengimpor lib/data.js supaya modul ini berdiri sendiri dan tidak
   menambah tautan ke graf modul halaman. */
const DATA_TULIS = (() => {
  const d = process.env.DATA_DIR;
  try {
    return d && fs.statSync(d).isDirectory() ? d : path.join(process.cwd(), "data");
  } catch {
    return path.join(process.cwd(), "data");
  }
})();

/* child_process SENGAJA diimpor di dalam fungsi, bukan di puncak berkas.
   Webpack menelusuri impor statis apa adanya dan menarik modul ini ke bundel
   klien saat pengembangan, lalu gagal dengan "UnhandledSchemeError:
   node:child_process" - padahal modulnya hanya pernah dipakai di sisi server. */
function jalankan(perintah, argumen, opsi) {
  const { execFile } = _req("child_process");
  const { promisify } = _req("util");
  return promisify(execFile)(perintah, argumen, opsi);
}

const JEDA_JAM = Number(process.env.ANALIS_JEDA_JAM || 24);
const BERKAS_JADWAL = path.join(DATA_TULIS, "jadwal_analis.json");
const RINGKAS = path.join(DATA_TULIS, "discord_ringkas.json");
const CADANGAN = path.join(DATA_TULIS, "discord_ringkas.bak.json");

/* Ambang penolakan. Baris boleh turun sedikit (panggilan kembar dibuang, data
   lewat masa simpan), tapi tidak boleh anjlok. */
const BATAS_SUSUT_BARIS = 0.8;

let sedangJalan = false;

function bacaJson(f, fallback) {
  try {
    return JSON.parse(fs.readFileSync(f, "utf8"));
  } catch {
    return fallback;
  }
}

function ukur(file) {
  const d = bacaJson(file, null);
  if (!d) return null;
  return { baris: (d.baris || []).length, analis: (d.analis || []).length };
}

function jatuhTempo() {
  const s = bacaJson(BERKAS_JADWAL, {});
  return !s.terakhir || Date.now() - s.terakhir >= JEDA_JAM * 3600_000;
}

function catat(isi) {
  try {
    fs.mkdirSync(DATA_TULIS, { recursive: true });
    fs.writeFileSync(BERKAS_JADWAL, JSON.stringify(isi, null, 2), "utf8");
  } catch { /* status gagal disimpan tidak boleh menggagalkan penarikan */ }
}

export function statusAnalis() {
  return { ...bacaJson(BERKAS_JADWAL, {}), jedaJam: JEDA_JAM, sedangJalan };
}

export async function tarikAnalis(alasan = "jadwal") {
  if (sedangJalan) return { lewat: "sedang berjalan" };
  if (!process.env.DISCORD_BOT_TOKEN) return { lewat: "DISCORD_BOT_TOKEN tidak ada" };
  if (!process.env.LLM_KEY && !process.env.XAI_API_KEY) {
    return { lewat: "kunci LLM tidak ada" };
  }

  sedangJalan = true;
  /* Penanda mulai: penarikan ini bisa berjalan puluhan menit, dan halaman perlu
     bisa mengatakan "menunggu LLM" alih-alih diam. */
  catat({ ...bacaJson(BERKAS_JADWAL, {}), berjalanSejak: Date.now() });
  const sebelum = ukur(RINGKAS);
  try {
    if (sebelum) fs.copyFileSync(RINGKAS, CADANGAN);

    await jalankan("python", ["fetch_discord.py", "--bulan", "6"], {
      cwd: process.cwd(),
      env: { ...process.env, PYTHONIOENCODING: "utf-8" },
      timeout: 45 * 60_000, // sama dengan batas di penjadwal dashboard lama
      maxBuffer: 16 * 1024 * 1024,
    });

    const sesudah = ukur(RINGKAS);
    if (!sesudah) throw new Error("hasil penarikan tidak terbaca");

    if (sebelum) {
      const analisSusut = sesudah.analis < sebelum.analis;
      const barisAnjlok = sesudah.baris < sebelum.baris * BATAS_SUSUT_BARIS;
      if (analisSusut || barisAnjlok) {
        fs.copyFileSync(CADANGAN, RINGKAS);
        const pesan =
          `hasil DITOLAK dan dikembalikan: ${sebelum.baris} baris/${sebelum.analis} analis ` +
          `-> ${sesudah.baris}/${sesudah.analis}. ` +
          `Biasanya izin bot ke sebuah channel dicabut.`;
        catat({ terakhir: Date.now(), galat: pesan });
        console.warn(`[analis] ${pesan}`);
        return { error: pesan };
      }
    }

    const hasil = `${sesudah.baris} baris, ${sesudah.analis} analis`;
    catat({ terakhir: Date.now(), hasil });
    console.log(`[analis] penarikan ${alasan} selesai: ${hasil}`);
    return { ok: true, hasil };
  } catch (e) {
    /* Kegagalan di tengah jalan bisa meninggalkan berkas setengah tertulis. */
    try {
      if (fs.existsSync(CADANGAN)) fs.copyFileSync(CADANGAN, RINGKAS);
    } catch { /* cadangan tidak ada: biarkan apa adanya */ }
    const galat = (e.stderr || e.message || "gagal").slice(0, 300);
    catat({ terakhir: Date.now(), galat });
    console.warn(`[analis] penarikan ${alasan} gagal: ${galat}`);
    return { error: galat };
  } finally {
    sedangJalan = false;
  }
}

export function mulaiPenarikAnalis() {
  if (!process.env.DISCORD_BOT_TOKEN || (!process.env.LLM_KEY && !process.env.XAI_API_KEY)) {
    console.log("[analis] penjadwal dilewati: DISCORD_BOT_TOKEN atau kunci LLM belum diset");
    return;
  }
  const periksa = () => {
    if (jatuhTempo()) tarikAnalis("jadwal").catch(() => {});
  };
  setTimeout(periksa, 60_000); // beri ruang startup; penarikan ini berat
  const t = setInterval(periksa, 30 * 60_000);
  t.unref?.();
  console.log(`[analis] penjadwal aktif, tiap ${JEDA_JAM} jam`);
}
