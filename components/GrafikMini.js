"use client";

import { useEffect, useRef } from "react";

/* Grafik ringkas untuk kolom kanan - tampilan awal sebelum chart penuh dibuka.
 *
 * Widget ini iframe, dan iframe menelan klik. Jadi yang menangkap klik adalah
 * lapisan transparan di atasnya (lihat Dashboard), bukan elemen ini.
 */
export default function GrafikMini({ pair, pasar, tinggi = 210 }) {
  const wadah = useRef(null);

  useEffect(() => {
    const el = wadah.current;
    if (!el || !pair) return;
    el.innerHTML = "";

    const s = document.createElement("script");
    s.src = "https://s3.tradingview.com/external-embedding/embed-widget-mini-symbol-overview.js";
    s.async = true;
    s.innerHTML = JSON.stringify({
      symbol: `BINANCE:${pair}${pasar === "futures" ? ".P" : ""}`,
      width: "100%",
      height: tinggi,
      locale: "id",
      dateRange: "3M",
      colorTheme: "dark",
      isTransparent: true,
      autosize: false,
    });
    el.appendChild(s);

    return () => { el.innerHTML = ""; };
  }, [pair, pasar, tinggi]);

  if (!pair) return <div className="kosong">Aset ini tidak ada di Binance.</div>;
  return <div ref={wadah} />;
}
