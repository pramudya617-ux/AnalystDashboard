"use client";

import { useEffect, useRef, useState } from "react";

/* Angka yang berjalan naik/turun saat nilainya berubah - dipakai untuk win rate
 * dan jumlah panggilan supaya pergantian analis terasa, bukan sekadar berkedip.
 *
 * Menghormati prefers-reduced-motion: kalau pengguna meminta gerak dikurangi,
 * angkanya langsung melompat ke nilai akhir tanpa animasi.
 */
/* Hook-nya dipisah supaya angka yang sama bisa dipakai di dalam SVG.
 * Membungkus komponen HTML dengan <foreignObject> sempat dicoba dan GAGAL:
 * Chromium tidak menggambar ulang isi foreignObject saat HTML di dalamnya
 * berubah, jadi angkanya membeku di nilai analis sebelumnya sementara teks SVG
 * di sebelahnya ikut berganti. */
export function useAngkaBerjalan(nilai, durasi = 650) {
  const [tampil, setTampil] = useState(nilai ?? 0);
  const dari = useRef(nilai ?? 0);
  const rafRef = useRef(0);

  useEffect(() => {
    if (typeof nilai !== "number" || !Number.isFinite(nilai)) return;

    const kurangiGerak =
      typeof window !== "undefined" &&
      window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;

    /* requestAnimationFrame DIBEKUKAN di tab yang tersembunyi, jadi animasi di
       sana tidak pernah berjalan dan angkanya akan tertinggal di nilai lama.
       Kalau halaman tidak terlihat, langsung lompat ke nilai akhir. */
    const tersembunyi = typeof document !== "undefined" && document.hidden;

    if (kurangiGerak || tersembunyi || durasi <= 0) {
      dari.current = nilai;
      setTampil(nilai);
      return;
    }

    const awal = dari.current;
    const selisih = nilai - awal;
    if (selisih === 0) return;

    const mulai = performance.now();
    /* easeOutCubic: cepat di awal lalu melambat, jadi angka akhirnya terbaca
       tenang alih-alih berhenti mendadak. */
    const mudah = (t) => 1 - Math.pow(1 - t, 3);

    const langkah = (sekarang) => {
      const t = Math.min(1, (sekarang - mulai) / durasi);
      setTampil(awal + selisih * mudah(t));
      if (t < 1) rafRef.current = requestAnimationFrame(langkah);
      else dari.current = nilai;
    };

    cancelAnimationFrame(rafRef.current);
    rafRef.current = requestAnimationFrame(langkah);
    return () => cancelAnimationFrame(rafRef.current);
  }, [nilai, durasi]);

  return tampil;
}

export default function Angka({ nilai, desimal = 0, akhiran = "", kosong = "—", durasi = 650 }) {
  const tampil = useAngkaBerjalan(nilai, durasi);
  if (typeof nilai !== "number" || !Number.isFinite(nilai)) return <>{kosong}</>;
  return (
    <span style={{ fontVariantNumeric: "tabular-nums" }}>
      {tampil.toFixed(desimal)}
      {akhiran}
    </span>
  );
}
