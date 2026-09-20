/** Dashboard analis: hanya baca berkas lokal, tanpa layanan luar saat build. */
const nextConfig = {
  experimental: { serverActions: { bodySizeLimit: "4mb" } },

  /* "x-powered-by: Next.js" mengumumkan stack yang dipakai kepada siapa pun yang
     mengetuk. Tidak berbahaya sendirian, tapi memudahkan orang mencocokkan
     exploit Next.js yang kebetulan sedang beredar. Tidak ada yang bergantung
     padanya, jadi dimatikan. */
  poweredByHeader: false,

  /* Header keamanan.
   *
   * SENGAJA TANPA Content-Security-Policy DULU. CSP adalah yang paling
   * protektif sekaligus paling gampang mematikan halaman: chart TradingView
   * dimuat dari s3.tradingview.com lalu membingkai www.tradingview-widget.com,
   * dan avatar analis datang dari cdn.discordapp.com. Satu asal terlewat dan
   * chart-nya blank TANPA pesan galat - jenis kerusakan yang baru ketahuan
   * setelah ada member yang mengeluh. Jadi CSP diuji terpisah di layar
   * sungguhan; lima header di bawah ini tidak bisa merusak apa pun.
   */
  async headers() {
    const dev = process.env.NODE_ENV !== "production";
    return [
      {
        source: "/:path*",
        headers: [
          /* Paksa HTTPS untuk kunjungan berikutnya. Railway sudah HTTPS, tapi
             ketikan pertama "drc.up.railway.app" di jaringan asing masih bisa
             dicegat sebelum pengalihannya terjadi.
             TANPA "preload": daftar preload browser sulit sekali dicabut, dan
             itu keputusan yang tidak boleh diambil diam-diam oleh berkas ini. */
          { key: "Strict-Transport-Security", value: "max-age=31536000; includeSubDomains" },

          /* Larang browser menebak tipe berkas dari isinya. */
          { key: "X-Content-Type-Options", value: "nosniff" },

          /* Anti-clickjacking. Bukan kehati-hatian berlebihan: halaman koreksi
             punya tombol Hapus, dan itu persis yang tidak boleh diklik orang
             tanpa sadar lewat iframe tak terlihat milik situs lain. */
          { key: "X-Frame-Options", value: "SAMEORIGIN" },

          /* Jaring pengaman untuk KOREKSI_JALUR. Tautan keluar di halaman itu
             sudah memakai rel="noreferrer", tapi ini menutup jalur yang belum
             terpikirkan: cross-origin hanya menerima origin, tanpa path, jadi
             alamat rahasianya tidak pernah ikut terkirim. */
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },

          { key: "Content-Security-Policy", value: [
            "default-src 'self'",
            /* 'unsafe-inline' TIDAK BISA DIHINDARI tanpa middleware nonce, dan
               middleware berarti runtime Edge - yang sudah dua kali menggagalkan
               build di proyek ini. Yang tetap didapat: skrip dari asal LUAR
               ditolak, jadi <script src="jahat.com"> tidak akan pernah jalan. */
            /* 'unsafe-eval' HANYA saat pengembangan: webpack memakai eval untuk
               source map, produksi tidak. Membiarkannya menyala di produksi
               melemahkan CSP tanpa menukar apa pun. */
            `script-src 'self' 'unsafe-inline'${dev ? " 'unsafe-eval'" : ""} https://s3.tradingview.com`,
            "style-src 'self' 'unsafe-inline'",
            "img-src 'self' data: blob: https://cdn.discordapp.com https://*.tradingview.com",
            "font-src 'self' data:",
            "connect-src 'self' https://*.tradingview.com",
            /* Widget embed memuat chart-nya dari tradingview-widget.com, BUKAN
               dari www.tradingview.com - yang diblokir di jaringan sini. */
            "frame-src https://*.tradingview.com https://*.tradingview-widget.com",
            "object-src 'none'",
            "base-uri 'self'",
            "form-action 'self'",
            "frame-ancestors 'self'",
          ].join("; ") },
          /* Dashboard ini tidak pernah butuh kamera, mikrofon, atau lokasi. */
          { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=()" },
        ],
      },
    ];
  },

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
