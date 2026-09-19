import { NextResponse } from "next/server";
import { NAMA_COOKIE, UMUR_SESI, buatTiket, sandi, sandiCocok } from "@/lib/sesi";
import { klien, lewatJatah } from "@/lib/jatah";

/* Delapan percobaan per menit per IP. Cukup longgar untuk salah ketik beberapa
   kali, cukup ketat untuk membuat penebakan beruntun tidak ada gunanya. */
const BATAS_PER_MENIT = 8;

/* Rute masuk halaman koreksi.
 *
 * GAGAL KE ARAH TERTUTUP: tanpa KOREKSI_SANDI, rute ini membalas 404 seolah
 * tidak ada. Membalas "kata sandi belum diset" akan memberi tahu penyerang bahwa
 * halaman itu memang ada dan tinggal menunggu sandinya dipasang.
 */
export async function POST(req) {
  if (!sandi()) return new NextResponse("Not found", { status: 404 });

  if (!lewatJatah(klien(req), BATAS_PER_MENIT)) {
    return NextResponse.json(
      { error: "Terlalu banyak percobaan. Tunggu semenit." },
      { status: 429 }
    );
  }

  let body;
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ error: "body bukan JSON" }, { status: 400 });
  }

  if (!sandiCocok(body?.sandi)) {
    return NextResponse.json({ error: "Kata sandi salah" }, { status: 401 });
  }

  const res = NextResponse.json({ ok: true });
  res.cookies.set(NAMA_COOKIE, buatTiket(), {
    httpOnly: true,     // tidak terbaca JavaScript halaman
    sameSite: "lax",
    path: "/",
    maxAge: UMUR_SESI,
    secure: process.env.NODE_ENV === "production",
  });
  return res;
}

/* Keluar: hapus cookie-nya. */
export async function DELETE() {
  const res = NextResponse.json({ ok: true });
  res.cookies.set(NAMA_COOKIE, "", { path: "/", maxAge: 0 });
  return res;
}
