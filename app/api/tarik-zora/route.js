import { NextResponse } from "next/server";
import { cookies } from "next/headers";
import { execFile } from "node:child_process";
import { promisify } from "node:util";
import { NAMA_COOKIE, sandi, tiketSah } from "@/lib/sesi";

const jalankan = promisify(execFile);

/* Menjalankan tarik_zora.py dari dashboard.
 *
 * Dilindungi sesi yang sama dengan halaman koreksi. Alasannya: ini menulis
 * data/zora.json dan memanggil Discord serta Binance, jadi bukan tombol baca
 * saja - siapa pun yang bisa membuka dashboard tidak boleh bisa memicunya
 * berulang-ulang.
 */
export const dynamic = "force-dynamic";
export const maxDuration = 300;

export async function POST() {
  if (!sandi()) return new NextResponse("Not found", { status: 404 });

  const jar = await cookies();
  if (!tiketSah(jar.get(NAMA_COOKIE)?.value)) {
    return NextResponse.json(
      { error: "Perlu masuk dulu lewat halaman /koreksi" },
      { status: 401 }
    );
  }

  try {
    const { stdout } = await jalankan("python", ["tarik_zora.py"], {
      cwd: process.cwd(),
      env: { ...process.env, PYTHONIOENCODING: "utf-8" },
      timeout: 280000,
      maxBuffer: 4 * 1024 * 1024,
    });

    const baris = stdout.trim().split("\n");
    /* Baris terakhir skrip berbunyi "N panggilan tersimpan ke ..." */
    const ringkas = baris[baris.length - 1] || "selesai";
    return NextResponse.json({ ok: true, ringkas, keluaran: baris.slice(-12) });
  } catch (e) {
    return NextResponse.json(
      { error: (e.stderr || e.message || "gagal menjalankan skrip").slice(0, 500) },
      { status: 500 }
    );
  }
}
