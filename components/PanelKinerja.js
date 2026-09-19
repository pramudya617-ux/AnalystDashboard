"use client";

import { useMemo, useState } from "react";
import { useAngkaBerjalan } from "./Angka";

const MENANG = ["untung", "target tersentuh"];
const KALAH = ["rugi", "invalidasi tersentuh"];

const BULAN_ID = ["Januari", "Februari", "Maret", "April", "Mei", "Juni",
  "Juli", "Agustus", "September", "Oktober", "November", "Desember"];

/* Panel kinerja dengan dua wajah, ditukar lewat tombol putar:
 *   corong  - berapa panggilan yang jadi untung dan rugi
 *   riwayat - kalender enam bulan, satu sel satu tanggal
 */
export default function PanelKinerja({ calls, mode }) {
  const [tampil, setTampil] = useState("corong");

  const hitung = useMemo(() => {
    const untung = calls.filter((c) => MENANG.includes(c.hasilAkhir)).length;
    const rugi = calls.filter((c) => KALAH.includes(c.hasilAkhir)).length;
    return { total: calls.length, untung, rugi, pasti: untung + rugi };
  }, [calls]);

  return (
    <section className="kaca">
      <div className="panel-kepala">
        <div>
          <div className="judul">
            {tampil === "corong" ? "Panggilan, untung, dan rugi" : "Riwayat 6 bulan"}
          </div>
          <div className="judul-sub">
            {tampil === "corong"
              ? "tiap tahap bagian dari tahap sebelumnya"
              : `${Object.keys(kalender(calls).isi).length} hari terisi`}
          </div>
        </div>
        <div className="kanan">
          <button
            className={`putar ${tampil === "riwayat" ? "berbalik" : ""}`}
            title={tampil === "corong" ? "Lihat riwayat trade" : "Lihat corong untung-rugi"}
            onClick={() => setTampil(tampil === "corong" ? "riwayat" : "corong")}
          >
            <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor"
                 strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M21 12a9 9 0 1 1-3-6.7" />
              <path d="M21 3v5h-5" />
            </svg>
          </button>
        </div>
      </div>

      {tampil === "corong" ? <Corong h={hitung} /> : <Kalender calls={calls} />}
    </section>
  );
}

/* --------------------------------------------------------------- corong */
/* Bentuk dan gaya teksnya mengikuti corong dashboard lama: tiap tahap adalah
   BAGIAN dari tahap sebelumnya (bukan kategori sejajar), jadi corong lebih jujur
   daripada diagram batang. Angka dan label diberi garis luar gelap supaya tetap
   terbaca di atas pita biru. */
function Corong({ h }) {
  const [buka, setBuka] = useState(false);
  const W = 1000, H = 190, pad = 16;
  const belum = h.total - h.pasti;

  const tahap = [
    { n: h.total, k: "Panggilan", dari: null },
    { n: h.untung, k: "Untung", dari: h.pasti },
    { n: h.rugi, k: "Rugi", dari: h.pasti },
  ];

  const maks = Math.max(...tahap.map((t) => t.n), 1);
  const lebar = W / (tahap.length - 1);
  const tengah = (H - pad) / 2 + pad / 2;
  const tinggi = (v) => Math.max(8, (v / maks) * (H - pad - 52));

  const atas = [], bawah = [];
  tahap.forEach((t, i) => {
    const x = i * lebar, ht = tinggi(t.n);
    atas.push([x, tengah - ht / 2]);
    bawah.push([x, tengah + ht / 2]);
  });

  const kurva = (titik) => {
    let d = `M${titik[0][0]},${titik[0][1]}`;
    for (let i = 0; i < titik.length - 1; i++) {
      const [x1, y1] = titik[i], [x2, y2] = titik[i + 1], xm = (x1 + x2) / 2;
      d += `C${xm},${y1} ${xm},${y2} ${x2},${y2}`;
    }
    return d;
  };
  const jalur =
    kurva(atas) +
    `L${bawah.at(-1)[0]},${bawah.at(-1)[1]}` +
    kurva([...bawah].reverse()).replace(/^M[^C]*/, "") +
    "Z";

  return (
    <div className="corong">
      <svg viewBox={`0 0 ${W} ${H}`} role="img"
           aria-label="Corong panggilan menjadi untung dan rugi">
        <defs>
          <linearGradient id="cgrad" x1="0" y1="0" x2="1" y2="0">
            <stop offset="0%" stopColor="var(--biru)" stopOpacity="0.92" />
            <stop offset="55%" stopColor="var(--biru)" stopOpacity="0.55" />
            <stop offset="100%" stopColor="var(--biru)" stopOpacity="0.18" />
          </linearGradient>
          <filter id="cglow" x="-25%" y="-60%" width="150%" height="220%">
            <feGaussianBlur stdDeviation="13" result="b" />
            <feMerge><feMergeNode in="b" /><feMergeNode in="SourceGraphic" /></feMerge>
          </filter>
        </defs>

        {tahap.map((t, i) => {
          const x = Math.min(W - 1, Math.max(1, i * lebar));
          return <line className="cbatas" key={`g${i}`} x1={x} y1={pad} x2={x} y2={H - 26} />;
        })}

        <path d={jalur} fill="url(#cgrad)" filter="url(#cglow)" />

        {tahap.map((t, i) => {
          /* Tahap terakhir menempel di tepi kanan, jadi teksnya digeser ke dalam
             supaya tidak terpotong. */
          const x = i * lebar + (i === tahap.length - 1 ? -190 : 14);
          return (
            <g key={t.k}>
              <AngkaSvg className="cn" x={x} y={tengah - 14} nilai={t.n} />
              <text className="cg" x={x} y={tengah + 18}>{t.k}</text>
              {t.dari ? (
                <text className="cs" x={x} y={tengah + 44}>
                  {Math.round((t.n / t.dari) * 100)}% dari yang pasti
                </text>
              ) : null}
            </g>
          );
        })}
      </svg>

      <div className="corong-ket">
        <button className="ket-buka" onClick={() => setBuka(!buka)} aria-expanded={buka}>
          <svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor"
               strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round"
               style={{ transform: buka ? "rotate(90deg)" : "none", transition: "transform .2s" }}>
            <path d="M9 6l6 6-6 6" />
          </svg>
          <span>
            <b style={{ color: "var(--ink-2)" }}>{belum}</b> belum pasti · win rate dari{" "}
            <b style={{ color: "var(--ink-2)" }}>{h.pasti}</b>
          </span>
        </button>

        {buka && (
          <p style={{ margin: "8px 0 0", lineHeight: 1.6 }}>
            Untung + Rugi tidak berjumlah sama dengan Panggilan. Yang belum pasti biasanya
            masih berjalan, ditutup manual tanpa menyebut hasil, atau berakhir BEP — dan
            sebagian kecil asetnya tidak diperdagangkan di Binance sehingga tidak ada harga
            pembanding.
          </p>
        )}
      </div>
    </div>
  );
}

/* Angka berjalan sebagai <text> SVG biasa - bukan foreignObject, yang tidak
   digambar ulang oleh Chromium saat isinya berubah. */
function AngkaSvg({ nilai, ...sisa }) {
  const tampil = useAngkaBerjalan(nilai);
  return <text {...sisa}>{Math.round(tampil)}</text>;
}

/* ------------------------------------------------------------- kalender */
function kalender(calls) {
  const isi = {};
  for (const c of calls) {
    const t = (c.waktu || "").slice(0, 10);
    if (!t) continue;
    if (!isi[t]) isi[t] = { tp: 0, sl: 0, lain: 0 };
    if (MENANG.includes(c.hasilAkhir)) isi[t].tp++;
    else if (KALAH.includes(c.hasilAkhir)) isi[t].sl++;
    else isi[t].lain++;
  }
  return { isi };
}

function Kalender({ calls }) {
  const { isi } = kalender(calls);
  const kunci = [...new Set(Object.keys(isi).map((d) => d.slice(0, 7)))].sort().reverse().slice(0, 6);

  if (!kunci.length) return <div className="kosong">Belum ada panggilan pada rentang ini.</div>;

  return (
    <div className="hm">
      {kunci.map((k) => {
        const [th, bl] = k.split("-").map(Number);
        const jumlahHari = new Date(th, bl, 0).getDate();
        return (
          <div className="hm-baris" key={k}>
            <span className="hm-bulan">{BULAN_ID[bl - 1]} {String(th).slice(2)}</span>
            {Array.from({ length: 31 }, (_, i) => {
              const d = i + 1;
              if (d > jumlahHari) return <span className="hm-sel luar" key={d} />;
              const tgl = `${k}-${String(d).padStart(2, "0")}`;
              const v = isi[tgl];
              let kls = "";
              let judul = `${tgl}: tidak ada panggilan`;
              if (v) {
                const bagian = [];
                if (v.tp) bagian.push(`${v.tp} untung`);
                if (v.sl) bagian.push(`${v.sl} rugi`);
                if (v.lain) bagian.push(`${v.lain} belum selesai`);
                judul = `${tgl}: ${bagian.join(", ")}`;
                kls = v.tp && v.sl ? "dua" : v.tp ? "tp" : v.sl ? "sl" : "belum";
              }
              return <span className={`hm-sel ${kls}`} key={d} title={judul} />;
            })}
          </div>
        );
      })}
      <div className="hm-legenda">
        <span><i className="hm-sel tp" style={{ width: 11, height: 11 }} /> untung</span>
        <span><i className="hm-sel sl" style={{ width: 11, height: 11 }} /> rugi</span>
        <span><i className="hm-sel dua" style={{ width: 11, height: 11 }} /> keduanya</span>
        <span><i className="hm-sel belum" style={{ width: 11, height: 11 }} /> belum selesai</span>
        <span><i className="hm-sel" style={{ width: 11, height: 11 }} /> tidak ada panggilan</span>
      </div>
    </div>
  );
}
