import { NextResponse } from "next/server";
import { ambilJson } from "@/lib/doh";
import { gerbang } from "@/lib/gerbang";

/* Harga realtime Binance, spot maupun futures.
 *
 * Spot diambil dari data-api.binance.vision - domain data publik Binance yang
 * lolos blokir DNS di Indonesia. Futures TIDAK ada di domain itu, jadi diambil
 * dari fapi.binance.com lewat resolusi DNS-over-HTTPS (lib/doh.js).
 *
 * Parameter: ?pairs=AKEUSDT:futures,CFXUSDT:spot
 */
const SPOT = "https://data-api.binance.vision/api/v3";
const FUTURES = "https://fapi.binance.com/fapi/v1";

export const dynamic = "force-dynamic";

export async function GET(req) {
  /* Ikut dijaga. Isinya memang harga publik, tapi tanpa ini rute ini jadi
     penerus Binance gratis yang bisa dipanggil siapa saja - dan kuota yang
     terpakai kuota dashboard ini. */
  if (!(await gerbang()).boleh) {
    return NextResponse.json({ error: "Perlu masuk dulu" }, { status: 401 });
  }

  const mentah = (new URL(req.url).searchParams.get("pairs") || "")
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean)
    .slice(0, 30);

  if (!mentah.length) return NextResponse.json({ error: "parameter pairs kosong" }, { status: 400 });

  const hasil = {};
  await Promise.all(
    mentah.map(async (item) => {
      const [simbolMentah, pasarMentah] = item.split(":");
      const simbol = simbolMentah.toUpperCase();
      const pasar = pasarMentah === "futures" ? "futures" : "spot";
      const url = pasar === "futures"
        ? `${FUTURES}/ticker/24hr?symbol=${encodeURIComponent(simbol)}`
        : `${SPOT}/ticker/24hr?symbol=${encodeURIComponent(simbol)}`;

      try {
        const d = await ambilJson(url, 12000);
        hasil[simbol] = {
          ada: true,
          pasar,
          harga: Number(d.lastPrice),
          ubah24j: Number(d.priceChangePercent),
          tertinggi: Number(d.highPrice),
          terendah: Number(d.lowPrice),
        };
      } catch (e) {
        hasil[simbol] = {
          ada: false,
          pasar,
          alasan: e.status === 400 ? "simbol tidak dikenal" : e.message || "gagal",
        };
      }
    })
  );

  return NextResponse.json({ waktu: new Date().toISOString(), harga: hasil });
}
