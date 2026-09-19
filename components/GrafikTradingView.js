"use client";

import { useEffect, useRef, useState } from "react";

/* Chart TradingView penuh - konfigurasi disamakan dengan dashboard lama.
 *
 * hide_side_toolbar sengaja false: analis menulis entry sebagai "CMP" lalu
 * MENGGAMBAR target dan stop di chart, jadi alat gambar di sisi kiri itu justru
 * bagian yang berguna, bukan hiasan.
 *
 * Widget dibangun ulang tiap ganti simbol. Embed gratis TradingView tidak
 * menyediakan cara mengganti simbol pada widget yang sudah jadi, jadi membangun
 * ulang adalah satu-satunya jalan yang jujur.
 */
const TV_SRC = "https://s3.tradingview.com/tv.js";
let muatTv = null;

function siapkanTv() {
  if (typeof window === "undefined") return Promise.reject(new Error("tanpa window"));
  if (window.TradingView) return Promise.resolve();
  if (!muatTv) {
    muatTv = new Promise((selesai, gagal) => {
      const s = document.createElement("script");
      s.src = TV_SRC;
      s.async = true;
      s.onload = () => selesai();
      s.onerror = () => { muatTv = null; gagal(new Error("skrip tidak termuat")); };
      document.head.appendChild(s);
    });
  }
  return muatTv;
}

export default function GrafikTradingView({
  pair, pasar, aset, arah, waktu, tinggi = 420, tanpaKepala = false,
}) {
  const wadah = useRef(null);
  const [galat, setGalat] = useState("");
  const simbol = pair ? `BINANCE:${pair}${pasar === "futures" ? ".P" : ""}` : null;

  useEffect(() => {
    if (!simbol || !wadah.current) return;
    let batal = false;
    setGalat("");

    const id = `tvchart-${Math.random().toString(36).slice(2)}`;
    wadah.current.innerHTML = `<div id="${id}" style="height:${tinggi}px"></div>`;

    siapkanTv()
      .then(() => {
        if (batal || !document.getElementById(id)) return;
        /* eslint-disable no-undef */
        new window.TradingView.widget({
          container_id: id,
          autosize: true,
          symbol: simbol,
          interval: "240",              // 4 jam, sama seperti dashboard lama
          timezone: "Asia/Jakarta",
          style: "1",
          locale: "id",
          theme: "dark",
          backgroundColor: "rgba(15,17,21,1)",
          gridColor: "rgba(255,255,255,0.06)",
          hide_side_toolbar: false,     // alat gambar dipakai untuk menandai TP/SL
          allow_symbol_change: false,
          withdateranges: true,
        });
      })
      .catch(() => {
        if (!batal) setGalat("Widget TradingView tidak bisa dimuat. Panel ini butuh koneksi ke tradingview.com; sisa dashboard tetap jalan.");
      });

    return () => { batal = true; };
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
      {/* Kepala dilewati kalau panel pemanggilnya sudah punya judul sendiri,
          supaya aset dan waktunya tidak tertulis dua kali. */}
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
      {galat ? <div className="kosong">{galat}</div> : <div ref={wadah} />}
    </div>
  );
}
