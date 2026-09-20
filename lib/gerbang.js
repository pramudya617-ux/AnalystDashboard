import { cookies } from "next/headers";
import { NAMA_COOKIE_MEMBER, memberDariTiket } from "./sesi";
import { dikonfigurasi, periksaRole, yangKurang } from "./discord";

/* SATU pintu untuk seluruh dashboard.
 *
 * Halaman dan rute API sama-sama memanggil ini, bukan menulis pemeriksaannya
 * sendiri-sendiri. Alasannya sudah terbukti mahal sekali di proyek ini: rute
 * /api/koreksi pernah terbuka lebar sementara halamannya meminta sandi, karena
 * penjagaannya ditulis dua kali dan yang satu ketinggalan. Selama semua lewat
 * sini, tidak ada pintu belakang yang bisa lupa dikunci.
 *
 * Memulangkan { boleh } atau { boleh: false, galat, ... }:
 *
 *   sebab "belum-masuk"    - belum ada sesi, tampilkan tombol masuk
 *   sebab "ditolak"        - sesinya sah tapi rolenya tidak memenuhi
 *   sebab "gangguan"       - Discord tidak bisa dihubungi; BUKAN penolakan
 *   sebab "belum-siap"     - environment di server belum lengkap
 */
export async function gerbang() {
  /* Jalan pintas pengembangan di laptop. Dikunci ganda: harus diminta secara
     eksplisit DAN tidak boleh produksi, jadi tidak mungkin menyala di Railway
     walau variabelnya ikut tersalin ke sana. */
  if (process.env.TANPA_LOGIN === "1" && process.env.NODE_ENV !== "production") {
    return { boleh: true, userId: "dev" };
  }

  if (!dikonfigurasi()) {
    return {
      boleh: false,
      sebab: "belum-siap",
      galat: `Login Discord belum dikonfigurasi. Yang belum diisi: ${yangKurang().join(", ")}.`,
    };
  }

  const jar = await cookies();
  const userId = memberDariTiket(jar.get(NAMA_COOKIE_MEMBER)?.value);
  if (!userId) return { boleh: false, sebab: "belum-masuk" };

  /* Tiket yang sah hanya menjawab "ini siapa". Yang menjawab "boleh masuk?"
     tetap Discord, tiap permintaan, supaya role yang dicabut langsung terasa. */
  let role;
  try {
    role = await periksaRole(userId);
  } catch (e) {
    return {
      boleh: false,
      sebab: "gangguan",
      galat: e.message || "Tidak bisa memeriksa role ke Discord saat ini.",
    };
  }

  if (!role.boleh) {
    return { boleh: false, sebab: "ditolak", galat: `Akses ditolak: ${role.alasan}.` };
  }
  return { boleh: true, userId, nama: role.nama };
}
