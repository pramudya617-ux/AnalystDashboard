/* Dijalankan sekali saat server Next.js menyala.
 *
 * Penjagaan runtime penting: instrumentation juga dimuat di runtime Edge, yang
 * tidak punya child_process maupun akses berkas - mengimpor penjadwal di sana
 * akan gagal saat build.
 */
export async function register() {
  if (process.env.NEXT_RUNTIME !== "nodejs") return;
  const { mulaiPenjadwal } = await import("./lib/penjadwal");
  mulaiPenjadwal();
}
