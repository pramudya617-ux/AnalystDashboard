"use client";

import { useEffect, useState } from "react";

/* Harga langsung dari Binance untuk aset yang sedang ditampilkan.
 *
 * Diambil lewat /api/harga karena host Binance biasa diblokir di lapis DNS di
 * Indonesia; jalur server memakai domain data publik yang tidak ikut diblokir.
 *
 * Pasangan yang hanya ada di futures tidak punya harga di host itu, dan itu
 * ditulis terang-terangan sebagai "hanya futures" - bukan ditampilkan nol.
 */
export default function HargaLangsung({ pairs, jeda = 20000 }) {
  const [data, setData] = useState(null);
  const [galat, setGalat] = useState(null);
  /* pairs berbentuk [[simbol, pasar], ...]; pasarnya ikut dikirim supaya server
     tahu harus bertanya ke endpoint spot atau futures. */
  const kunci = pairs.map(([p, pasar]) => `${p}:${pasar || "spot"}`).join(",");

  useEffect(() => {
    if (!kunci) return;
    let hidup = true;

    async function tarik() {
      try {
        const r = await fetch(`/api/harga?pairs=${encodeURIComponent(kunci)}`, { cache: "no-store" });
        const j = await r.json();
        if (!hidup) return;
        if (!r.ok) throw new Error(j.error || "gagal");
        setData(j);
        setGalat(null);
      } catch (e) {
        if (hidup) setGalat(e.message);
      }
    }

    tarik();
    const t = setInterval(tarik, jeda);
    return () => { hidup = false; clearInterval(t); };
  }, [kunci, jeda]);

  if (!kunci) return <div className="kosong">Tidak ada aset untuk dipantau.</div>;

  return (
    <div className="daftar">
      {galat && <div className="kosong">Harga tidak terambil: {galat}</div>}
      {!data && !galat && <div className="kosong">Mengambil harga…</div>}
      {data &&
        pairs.map(([p, pasar]) => {
          const h = data.harga[p];
          return (
            <div className="daftar-baris" key={p}>
              <span className="daftar-nama">
                {p.replace("USDT", "")}
                {pasar === "futures" && (
                  <i style={{ fontSize: 9, color: "var(--ink-3)", marginLeft: 4, fontStyle: "normal" }}>
                    PERP
                  </i>
                )}
              </span>
              {h?.ada ? (
                <>
                  <span style={{ flex: 1, fontVariantNumeric: "tabular-nums" }}>
                    {h.harga < 1 ? h.harga.toFixed(5) : h.harga.toFixed(2)}
                  </span>
                  <span className={`daftar-nilai ${h.ubah24j >= 0 ? "imbal plus" : "imbal minus"}`}>
                    {h.ubah24j >= 0 ? "+" : ""}
                    {h.ubah24j.toFixed(2)}%
                  </span>
                </>
              ) : (
                <span style={{ flex: 1, fontSize: 11, color: "var(--ink-3)" }}>
                  {h?.alasan || "—"}
                </span>
              )}
            </div>
          );
        })}
      {data && (
        <div style={{ fontSize: 10.5, color: "var(--ink-3)", textAlign: "right" }}>
          diperbarui {new Date(data.waktu).toLocaleTimeString("id-ID")}
        </div>
      )}
    </div>
  );
}
