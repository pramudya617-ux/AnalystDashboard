import { muatDashboard, ZORA } from "@/lib/data";
import { statusPenarikan } from "@/lib/status";
import { gerbang } from "@/lib/gerbang";
import Dashboard from "@/components/Dashboard";
import MasukDiscord from "@/components/MasukDiscord";

export const dynamic = "force-dynamic"; // koreksi tersimpan di berkas, jangan di-cache

export default async function Halaman({ searchParams }) {
  const sp = await searchParams;

  /* Seluruh dashboard ada di balik login. Pemeriksaannya mendahului pembacaan
     data supaya yang belum berhak tidak pernah membuat server membaca berkas
     panggilan sama sekali - bukan sekadar tidak menampilkannya. */
  const izin = await gerbang();
  if (!izin.boleh) {
    return <MasukDiscord sebab={izin.sebab} galat={izin.galat || sp?.galat} />;
  }

  const mode = sp?.mode === "september" ? "september" : "6bulan";
  const data = muatDashboard(mode);
  /* Status penjadwal ikut dikirim supaya baris kabar di kepala halaman
     memberitakan keadaan sebenarnya, bukan tebakan dari cap waktu berkas. */
  data.jadwal = statusPenarikan();

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
