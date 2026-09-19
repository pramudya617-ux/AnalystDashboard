"use client";

import { useEffect, useRef } from "react";

/* Chart TradingView penuh.
 *
 * MEMAKAI WIDGET EMBED, BUKAN tv.js.
 *
 * Versi pertama memakai `new TradingView.widget()` dari s3.tradingview.com/tv.js
 * seperti dashboard lama, dan hasilnya halaman 403 dari CloudFront: konstruktor
 * itu memuat chart-nya dari www.tradingview.com, yang diblokir di jaringan sini.
 * Widget embed memuat isinya dari www.tradingview-widget.com - host yang sama
 * dengan pratinjau mini yang selama ini jalan normal.
 *
 * hide_side_toolbar sengaja false: analis menulis entry sebagai "CMP" lalu
 * MENGGAMBAR target dan stop di chart, jadi alat gambar di sisi kiri itu bagian
 * yang berguna, bukan hiasan.
 */
export default function GrafikTradingView({
  pair, pasar, aset, arah, waktu, tinggi = 420, tanpaKepala = false,
}) {
  const wadah = useRef(null);
  const simbol = pair ? `BINANCE:${pair}${pasar === "futures" ? ".P" : ""}` : null;

  useEffect(() => {
    const el = wadah.current;
    if (!el || !simbol) return;
    el.innerHTML = "";

    const kotak = document.createElement("div");
    kotak.className = "tradingview-widget-container";
    const isi = document.createElement("div");
    isi.className = "tradingview-widget-container__widget";
    kotak.appendChild(isi);

    const s = document.createElement("script");
    s.src = "https://s3.tradingview.com/external-embedding/embed-widget-advanced-chart.js";
    s.async = true;
    /* Tinggi diberikan lewat konfigurasi, BUKAN lewat CSS wadahnya: skrip widget
       menulis ulang gaya wadahnya sendiri, dan tinggi yang diset dari luar
       berakhir tertimpa jadi ~150px. */
    s.innerHTML = JSON.stringify({
      autosize: false,
      width: "100%",
      height: tinggi,
      symbol: simbol,
      interval: "240",            // 4 jam, sama seperti dashboard lama
      timezone: "Asia/Jakarta",
      theme: "dark",
      style: "1",
      locale: "id",
      hide_side_toolbar: false,   // alat gambar dipakai untuk menandai TP/SL
      allow_symbol_change: false,
      withdateranges: true,
      save_image: false,
      backgroundColor: "rgba(15,17,21,1)",
      gridColor: "rgba(255,255,255,0.06)",
    });
    kotak.appendChild(s);
    el.appendChild(kotak);

    return () => { el.innerHTML = ""; };
  }, [simbol, tinggi]);

  if (!pair) {
    return (
      <div className="kosong">
        <b>{aset || "Aset ini"}</b> tidak diperdagangkan di Binance, jadi tidak ada chart
        yang bisa ditampilkan. Biasanya token yang hanya ada di DEX, di bursa lain, atau
        tikernya sudah delisting.
      </div>
    );
  }

  return (
    <div style={{ padding: "0 10px 10px" }}>
      {!tanpaKepala && (
        <div style={{ display: "flex", alignItems: "baseline", gap: 8, padding: "0 4px 8px" }}>
          <b style={{ fontSize: 13.5 }}>
            {aset}
            <span style={{ color: "var(--ink-3)", fontWeight: 400 }}>/USDT</span>
          </b>
          <span style={{ fontSize: 11, color: "var(--ink-3)" }}>
            {arah ? `${arah} · ` : ""}
            {waktu ? waktu.slice(0, 16).replace("T", " ") : ""}
          </span>
        </div>
      )}
      <div ref={wadah} />
    </div>
  );
}
