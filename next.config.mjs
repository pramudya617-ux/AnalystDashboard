/** Dashboard analis: hanya baca berkas lokal, tanpa layanan luar saat build. */
const nextConfig = {
  experimental: { serverActions: { bodySizeLimit: "4mb" } },

  webpack: (config, { isServer, dev }) => {
    /* instrumentation.js dikompilasi Next untuk SEMUA runtime, termasuk bundel
       fallback klien saat pengembangan. Penjadwal yang diimpornya memakai
       child_process dan fs, dan webpack menolaknya dengan
       "UnhandledSchemeError: node:child_process" - padahal modul itu tidak
       pernah benar-benar dijalankan di peramban (register() keluar lebih dulu
       kalau runtime-nya bukan nodejs).
       Jadi di sisi klien modul-modul itu dipetakan ke false. */
    if (!isServer) {
      config.resolve.alias = {
        ...config.resolve.alias,
        "node:child_process": false,
        "node:fs": false,
        "node:path": false,
        "node:util": false,
        "node:module": false,
      };
    }
    /* Cache berkas webpack dimatikan saat pengembangan. Di Windows, penggantian
       nama berkas cache-nya sering berebut dengan proses lain dan gagal dengan
       ENOENT "0.pack.gz_" -> "0.pack.gz", lalu kompilasinya jadi tak menentu.
       Rebuild memang sedikit lebih lambat, tapi hasilnya bisa dipercaya. */
    if (dev) config.cache = false;

    return config;
  },
};

export default nextConfig;
