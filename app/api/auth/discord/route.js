import { NextResponse } from "next/server";
import { cookies } from "next/headers";
import crypto from "node:crypto";
import {
  NAMA_COOKIE_STATE,
  alamatBalik,
  dikonfigurasi,
  lupakanRole,
  periksaRole,
  siapa,
  tukarKode,
  urlOtorisasi,
} from "@/lib/discord";
import { NAMA_COOKIE_MEMBER, UMUR_SESI, buatTiketMember } from "@/lib/sesi";
import { klien, lewatJatah } from "@/lib/jatah";

/* Satu rute untuk dua arah perjalanan OAuth, dan itu bukan penghematan asal:
 * alamat baliknya memang harus /api/auth/discord, jadi membuat rute "mulai"
 * yang terpisah berarti satu berkas lagi yang alamatnya harus dijaga tetap
 * cocok dengan yang didaftarkan di Discord.
 *
 *   GET tanpa ?code  -> berangkat ke Discord
 *   GET dengan ?code -> pulang dari Discord, tukar kode, periksa role
 *   DELETE           -> keluar
 */
export const dynamic = "force-dynamic";

/* Percobaan per menit per IP. Yang dijaga bukan tebakan sandi - tidak ada sandi
   di sini - melainkan pemanggilan berulang ke API Discord lewat kode palsu. */
const BATAS_PER_MENIT = 20;

function keLayarMasuk(galat) {
  const u = new URL("/", alamatBalik());
  if (galat) u.searchParams.set("galat", galat.slice(0, 300));
  return NextResponse.redirect(u, { status: 303 });
}

export async function GET(req) {
  if (!dikonfigurasi()) return keLayarMasuk("Login Discord belum dikonfigurasi di server.");

  if (!lewatJatah(klien(req), BATAS_PER_MENIT)) {
    return keLayarMasuk("Terlalu banyak percobaan masuk. Tunggu semenit.");
  }

  const sp = new URL(req.url).searchParams;
  const kode = sp.get("code");

  /* ------------------------------------------------------------ berangkat */
  if (!kode) {
    /* State CSRF DIIKAT KE PERAMBAN lewat cookie, bukan sekadar ditandatangani.
       State yang cuma ditandatangani bisa diambil siapa saja dengan membuka
       halaman ini, lalu dipakai untuk menyeret orang lain masuk ke akun
       Discord milik penyerang. Nilai acaknya harus datang dari peramban yang
       sama yang nanti pulang membawa kodenya. */
    const state = crypto.randomBytes(16).toString("hex");
    const res = NextResponse.redirect(urlOtorisasi(state), { status: 303 });
    res.cookies.set(NAMA_COOKIE_STATE, state, {
      httpOnly: true,
      /* HARUS lax, bukan strict: kepulangan dari Discord adalah navigasi lintas
         situs, dan strict akan menahan cookie-nya persis saat dibutuhkan. */
      sameSite: "lax",
      path: "/",
      maxAge: 600,
      secure: process.env.NODE_ENV === "production",
    });
    return res;
  }

  /* --------------------------------------------------------------- pulang */
  const jar = await cookies();
  const harap = jar.get(NAMA_COOKIE_STATE)?.value;
  const ada = sp.get("state");
  if (!harap || !ada || harap !== ada) {
    return keLayarMasuk("Sesi login kedaluwarsa atau tidak cocok. Coba masuk lagi.");
  }

  /* Discord bisa pulang membawa kegagalan alih-alih kode - paling sering
     access_denied karena prompt=none pada orang yang belum pernah mengizinkan
     aplikasinya. Dikirim balik ke layar masuk tanpa prompt=none. */
  if (sp.get("error")) {
    return keLayarMasuk(
      sp.get("error") === "access_denied"
        ? "Izin dibatalkan. Klik masuk sekali lagi untuk menyetujuinya."
        : `Discord menolak: ${sp.get("error_description") || sp.get("error")}`
    );
  }

  let hasil;
  try {
    const token = await tukarKode(kode);
    const orang = await siapa(token);
    /* Singgahan dibuang supaya member yang rolenya baru saja diberikan tidak
       tertolak oleh jawaban lama yang belum kedaluwarsa. */
    lupakanRole(orang.id);
    const role = await periksaRole(orang.id);
    hasil = { orang, role };
  } catch (e) {
    return keLayarMasuk(e.message || "Login gagal.");
  }

  if (!hasil.role.boleh) {
    return keLayarMasuk(
      `Akun @${hasil.orang.nama} ${hasil.role.alasan}. ` +
        "Kalau kamu punya lebih dari satu akun Discord, pastikan peramban ini masuk ke akun yang benar."
    );
  }

  const res = NextResponse.redirect(new URL("/", alamatBalik()), { status: 303 });
  res.cookies.set(NAMA_COOKIE_MEMBER, buatTiketMember(hasil.orang.id), {
    httpOnly: true,
    sameSite: "lax",
    path: "/",
    maxAge: UMUR_SESI,
    secure: process.env.NODE_ENV === "production",
  });
  res.cookies.set(NAMA_COOKIE_STATE, "", { path: "/", maxAge: 0 });
  return res;
}

export async function DELETE() {
  const res = NextResponse.json({ ok: true });
  res.cookies.set(NAMA_COOKIE_MEMBER, "", { path: "/", maxAge: 0 });
  return res;
}
