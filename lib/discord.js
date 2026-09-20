/* Login member lewat Discord OAuth2, dan pemeriksaan role premium.
 *
 * KENAPA SCOPE-NYA HANYA "identify":
 *
 *   Yang dibutuhkan cuma satu hal - siapa orang ini. Role-nya TIDAK ditanyakan
 *   ke pengguna lewat scope guilds.members.read, melainkan dibaca oleh BOT yang
 *   sudah ada di server itu. Dua keuntungan: layar izin yang dilihat member
 *   hanya menyebut username dan avatar (jauh lebih tidak menakutkan), dan
 *   rolenya datang dari sumber yang tidak bisa dipengaruhi si pengguna sendiri.
 *
 * ROLE DIPERIKSA TIAP PERMINTAAN, BUKAN SEKALI SAAT LOGIN.
 *
 *   Cookie hidup 12 jam. Kalau role hanya diperiksa saat login, member yang
 *   berhenti berlangganan tetap bisa membaca dashboard sampai setengah hari
 *   berikutnya. Jadi tiketnya hanya menjawab "ini siapa"; yang menjawab "boleh
 *   masuk?" adalah Discord, tiap kali halaman dirender - dengan singgahan lima
 *   menit supaya tidak satu panggilan API per muat halaman.
 */
const API = "https://discord.com/api/v10";

export const NAMA_COOKIE_STATE = "oauth_state";

/* Umur singgahan role. Lima menit: cukup pendek supaya pencabutan role terasa
   hampir seketika, cukup panjang supaya membuka-tutup halaman tidak menghujani
   API Discord. */
const UMUR_SINGGAHAN = 5 * 60_000;

export function rolePremium() {
  return new Set(
    (process.env.PREMIUM_ROLE_IDS || "")
      .split(",")
      .map((s) => s.trim())
      .filter(Boolean)
  );
}

/* Alamat balik OAuth. HARUS sama persis dengan yang didaftarkan di tab OAuth2
 * aplikasi Discord - beda satu garis miring pun ditolak dengan
 * "invalid_redirect_uri".
 *
 * Di Railway, RAILWAY_PUBLIC_DOMAIN sudah disediakan sendiri, jadi alamatnya
 * tidak perlu diketik ulang sebagai variabel. APP_URL tetap ada untuk domain
 * sendiri atau kalau suatu saat pindah dari Railway.
 */
export function alamatBalik() {
  const dasar =
    process.env.APP_URL ||
    (process.env.RAILWAY_PUBLIC_DOMAIN && `https://${process.env.RAILWAY_PUBLIC_DOMAIN}`) ||
    "http://localhost:3100";
  return `${dasar.replace(/\/+$/, "")}/api/auth/discord`;
}

/* Apa saja yang belum diisi. Memulangkan DAFTAR, bukan boolean, supaya layar
   masuk bisa menyebutkan yang kurang alih-alih cuma bilang "belum siap". */
export function yangKurang() {
  const perlu = {
    DISCORD_CLIENT_ID: process.env.DISCORD_CLIENT_ID,
    DISCORD_CLIENT_SECRET: process.env.DISCORD_CLIENT_SECRET,
    DISCORD_GUILD_ID: process.env.DISCORD_GUILD_ID,
    DISCORD_BOT_TOKEN: process.env.DISCORD_BOT_TOKEN,
  };
  const kurang = Object.keys(perlu).filter((k) => !perlu[k]);
  if (!rolePremium().size) kurang.push("PREMIUM_ROLE_IDS");
  return kurang;
}

export function dikonfigurasi() {
  return yangKurang().length === 0;
}

export function urlOtorisasi(state) {
  const p = new URLSearchParams({
    client_id: process.env.DISCORD_CLIENT_ID || "",
    redirect_uri: alamatBalik(),
    response_type: "code",
    scope: "identify",
    state,
    /* prompt=none melewati layar izin kalau orangnya sudah pernah mengizinkan.
       Inilah yang membuat masuk ulang setelah sesi habis terasa seperti tidak
       ada login sama sekali: satu klik, langsung kembali. Yang belum pernah
       mengizinkan tetap melihat layar izinnya seperti biasa. */
    prompt: "none",
  });
  return `https://discord.com/oauth2/authorize?${p}`;
}

export async function tukarKode(code) {
  const badan = new URLSearchParams({
    client_id: process.env.DISCORD_CLIENT_ID || "",
    client_secret: process.env.DISCORD_CLIENT_SECRET || "",
    grant_type: "authorization_code",
    code,
    redirect_uri: alamatBalik(),
  });
  const r = await fetch(`${API}/oauth2/token`, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: badan,
    cache: "no-store",
  });
  if (!r.ok) {
    const t = await r.text().catch(() => "");
    throw new Error(`Discord menolak kode login (HTTP ${r.status}) ${t.slice(0, 160)}`);
  }
  const j = await r.json();
  if (!j.access_token) throw new Error("Discord tidak memulangkan access_token");
  return j.access_token;
}

export async function siapa(accessToken) {
  const r = await fetch(`${API}/users/@me`, {
    headers: { Authorization: `Bearer ${accessToken}` },
    cache: "no-store",
  });
  if (!r.ok) throw new Error(`Gagal membaca identitas Discord (HTTP ${r.status})`);
  const u = await r.json();
  return { id: u.id, nama: u.global_name || u.username || u.id };
}

/* --------------------------------------------------------------- singgahan */
const _singgah = new Map();

function dariSinggahan(userId) {
  const c = _singgah.get(userId);
  return c && c.kedaluwarsa > Date.now() ? c : null;
}

function keSinggahan(userId, nilai) {
  /* Pangkas kalau menumpuk, pola yang sama dengan lib/jatah.js. Member premium
     jumlahnya kecil, jadi batas ini praktis tidak pernah tersentuh. */
  if (_singgah.size > 1000) {
    const now = Date.now();
    for (const [k, v] of _singgah) if (v.kedaluwarsa <= now) _singgah.delete(k);
  }
  _singgah.set(userId, { ...nilai, kedaluwarsa: Date.now() + UMUR_SINGGAHAN });
}

/* Buang singgahan satu orang - dipanggil tepat setelah login supaya member yang
   baru saja dibelikan role tidak perlu menunggu lima menit. */
export function lupakanRole(userId) {
  _singgah.delete(userId);
}

/* Memulangkan { boleh, nama, alasan }.
 *
 * MELEMPAR kalau Discord tidak bisa dihubungi, dan itu disengaja: gangguan
 * jaringan sesaat TIDAK BOLEH disinggahi sebagai "tidak punya role", karena itu
 * akan mengunci seluruh member selama lima menit ke depan. Pemanggilnya
 * membedakan "ditolak" dari "tidak bisa diperiksa".
 */
export async function periksaRole(userId) {
  const c = dariSinggahan(userId);
  if (c) return { boleh: c.boleh, nama: c.nama, alasan: c.alasan };

  const r = await fetch(
    `${API}/guilds/${process.env.DISCORD_GUILD_ID}/members/${userId}`,
    {
      headers: { Authorization: `Bot ${process.env.DISCORD_BOT_TOKEN}` },
      cache: "no-store",
    }
  );

  /* 404 = orangnya bukan anggota server. Jawaban yang pasti, jadi boleh
     disinggahi seperti penolakan lain. */
  if (r.status === 404) {
    const hasil = { boleh: false, nama: "", alasan: "bukan anggota server Discord DRC" };
    keSinggahan(userId, hasil);
    return hasil;
  }
  if (r.status === 403) {
    /* Hampir selalu berarti SERVER MEMBERS INTENT di tab Bot belum dinyalakan.
       Disebut terang-terangan supaya tidak dikira role member yang bermasalah. */
    throw new Error(
      "Bot tidak diizinkan membaca daftar member. Nyalakan SERVER MEMBERS INTENT " +
        "di Discord Developer Portal > aplikasi > Bot."
    );
  }
  if (!r.ok) throw new Error(`Gagal memeriksa role (HTTP ${r.status})`);

  const m = await r.json();
  const premium = rolePremium();
  const boleh = (m.roles || []).some((id) => premium.has(id));
  const hasil = {
    boleh,
    nama: m.nick || m.user?.global_name || m.user?.username || "",
    alasan: boleh ? "" : "belum punya role premium",
  };
  keSinggahan(userId, hasil);
  return hasil;
}
