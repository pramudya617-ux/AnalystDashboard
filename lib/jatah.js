/* Pembatas percobaan per IP - jendela geser satu menit.
 *
 * Meniru lewat_jatah() di serve.py dashboard lama, dengan alasan yang sama:
 * tanpa ini, kata sandi halaman koreksi bisa ditebak berulang-ulang tanpa henti,
 * dan sandi sepanjang apa pun akhirnya jatuh kalau penebaknya tidak pernah
 * dihentikan.
 *
 * Bukan token bucket, bukan Redis: satu proses, satu Map. Railway menjalankan
 * satu replika (numReplicas: 1), jadi hitungannya utuh. Kalau suatu saat
 * replikanya lebih dari satu, jatahnya jadi per replika - masih jauh lebih baik
 * daripada tanpa jatah sama sekali.
 */
const JENDELA_MS = 60_000;
const _jatah = new Map();

/* IP pemanggil. Di belakang proxy Railway, alamat soket selalu proxy itu
 * sendiri, jadi jatah per IP tanpa membaca X-Forwarded-For akan menghukum semua
 * pengunjung sebagai satu orang. */
export function klien(req) {
  const maju = req.headers.get("x-forwarded-for") || "";
  return maju.split(",")[0].trim() || req.headers.get("x-real-ip") || "tak diketahui";
}

export function lewatJatah(ip, batas) {
  const now = Date.now();

  /* Pangkas sesekali supaya IP yang datang sekali lalu hilang tidak menumpuk
     sampai memakan memori. */
  if (_jatah.size > 2000) {
    for (const [k, v] of _jatah) {
      if (!v.length || now - v[v.length - 1] > JENDELA_MS) _jatah.delete(k);
    }
  }

  const d = (_jatah.get(ip) || []).filter((t) => now - t < JENDELA_MS);
  if (d.length >= batas) {
    _jatah.set(ip, d);
    return false;
  }
  d.push(now);
  _jatah.set(ip, d);
  return true;
}
