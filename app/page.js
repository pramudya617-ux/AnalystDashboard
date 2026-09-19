import { muatDashboard, ZORA } from "@/lib/data";
import Dashboard from "@/components/Dashboard";

export const dynamic = "force-dynamic"; // koreksi tersimpan di berkas, jangan di-cache

export default async function Halaman({ searchParams }) {
  const sp = await searchParams;
  const mode = sp?.mode === "september" ? "september" : "6bulan";
  const data = muatDashboard(mode);

  /* Zora belum punya data tarikan; tampil sebagai kartu menunggu supaya
     keberadaannya terlihat tanpa memalsukan angka apa pun. */
  const adaZora = data.analis.some((a) => a.id === ZORA.id);
  if (!adaZora) {
    data.analis.push({
      id: ZORA.id,
      nama: ZORA.nama,
      avatar: null,
      bot: false,
      kanal: [`channel ${ZORA.channelId}`],
      jumlahPesan: 0,
      ringkasan: "",
      ringkasanSaja: false,
      belumDitarik: true,
      calls: [],
      metrik: null,
    });
  }

  return <Dashboard data={data} />;
}
