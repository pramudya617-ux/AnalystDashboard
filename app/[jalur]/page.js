import { cookies } from "next/headers";
import { notFound } from "next/navigation";
import { muatDashboard } from "@/lib/data";
import { NAMA_COOKIE, sandi, tiketSah } from "@/lib/sesi";
import TabelKoreksi from "@/components/TabelKoreksi";
import FormMasuk from "@/components/FormMasuk";

export const dynamic = "force-dynamic";

/* Segmen koreksi, dilindungi kata sandi seperti halaman koreksi dashboard lama.
 *
 * ALAMATNYA BISA DIACAK. Berkas ini duduk di segmen dinamis, bukan di /koreksi,
 * supaya alamatnya ditentukan KOREKSI_JALUR di environment: isi "asdhjkl" dan
 * halaman ini hanya ada di /asdhjkl. Tanpa KOREKSI_JALUR, alamatnya /koreksi
 * seperti biasa supaya jalan apa adanya saat dikembangkan di laptop.
 *
 * Alamat acak BUKAN pengamanannya - kata sandi, batas percobaan, dan
 * pemeriksaan sesi di /api/koreksi yang menjaga isinya. Gunanya cuma satu:
 * pemindai alamat dan orang yang asal menebak tidak pernah sampai ke formulir
 * sandinya. Alamat bisa bocor lewat riwayat browser, catatan, atau header
 * Referer, jadi jangan pernah diperlakukan sebagai rahasia yang menjaga data.
 *
 * Tanpa KOREKSI_SANDI, halaman ini membalas 404 - bukan pesan "sandi belum
 * diset" yang justru mengumumkan keberadaannya.
 */
export default async function HalamanKoreksi({ params, searchParams }) {
  const { jalur } = await params;
  if (jalur !== (process.env.KOREKSI_JALUR || "koreksi")) notFound();
  if (!sandi()) notFound();

  const jar = await cookies();
  if (!tiketSah(jar.get(NAMA_COOKIE)?.value)) return <FormMasuk />;

  const sp = await searchParams;
  const mode = sp?.mode === "september" ? "september" : "6bulan";
  return <TabelKoreksi data={muatDashboard(mode)} />;
}
