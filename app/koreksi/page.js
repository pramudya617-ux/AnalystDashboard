import { cookies } from "next/headers";
import { notFound } from "next/navigation";
import { muatDashboard } from "@/lib/data";
import { NAMA_COOKIE, sandi, tiketSah } from "@/lib/sesi";
import TabelKoreksi from "@/components/TabelKoreksi";
import FormMasuk from "@/components/FormMasuk";

export const dynamic = "force-dynamic";

/* Segmen koreksi, dilindungi kata sandi seperti halaman koreksi dashboard lama.
 *
 * Tanpa KOREKSI_SANDI di environment, halaman ini membalas 404 - bukan pesan
 * "sandi belum diset" yang justru mengumumkan keberadaannya.
 */
export default async function HalamanKoreksi({ searchParams }) {
  if (!sandi()) notFound();

  const jar = await cookies();
  if (!tiketSah(jar.get(NAMA_COOKIE)?.value)) return <FormMasuk />;

  const sp = await searchParams;
  const mode = sp?.mode === "september" ? "september" : "6bulan";
  return <TabelKoreksi data={muatDashboard(mode)} />;
}
