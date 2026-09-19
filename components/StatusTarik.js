"use client";

import { useEffect, useState } from "react";

/* Baris status penarikan di kepala halaman.
 *
 * Bergantian antara kabar Zora dan kabar analis lain, dengan pudar di antaranya,
 * karena keduanya punya irama sendiri: Zora tiap 30 menit (aturan tetap, murah),
 * analis lain harian (perlu LLM). Satu baris tetap akan menyembunyikan salah
 * satunya.
 *
 * Isinya mengikuti keadaan sebenarnya - "menunggu LLM" hanya muncul kalau
 * penarikannya memang sedang berjalan, bukan sebagai hiasan.
 */
function sejak(ms) {
  const detik = (Date.now() - ms) / 1000;
  if (!Number.isFinite(detik) || detik < 0) return "baru saja";
  if (detik < 90) return "baru saja";
  const menit = Math.round(detik / 60);
  if (menit < 60) return `${menit} menit lalu`;
  const jam = Math.round(menit / 60);
  if (jam < 24) return `${jam} jam lalu`;
  return `${Math.round(jam / 24)} hari lalu`;
}

export default function StatusTarik({ jadwal, namaAnalis = [] }) {
  const [ke, setKe] = useState(0);
  const [tampak, setTampak] = useState(true);
  const [, paksa] = useState(0);

  /* Hitung ulang tiap menit supaya "20 menit lalu" tidak membeku. */
  useEffect(() => {
    const t = setInterval(() => paksa((n) => n + 1), 60_000);
    return () => clearInterval(t);
  }, []);

  const baris = [];
  const z = jadwal?.zora;
  if (z?.sedangJalan) baris.push("Zora sedang ditarik…");
  else if (z?.terakhir) baris.push(`Zora diperbarui ${sejak(z.terakhir)}`);

  const a = jadwal?.analis;
  const daftar = namaAnalis.length
    ? namaAnalis.slice(0, 2).join(", ") + (namaAnalis.length > 2 ? `, +${namaAnalis.length - 2}` : "")
    : "Analis lain";
  if (a?.sedangJalan) baris.push(`${daftar} menunggu LLM…`);
  else if (a?.galat) baris.push(`${daftar}: penarikan terakhir gagal`);
  else if (a?.terakhir) baris.push(`${daftar} diperbarui ${sejak(a.terakhir)}`);
  else baris.push(`${daftar} belum pernah ditarik`);

  /* Berganti tiap 6 detik, dengan 400 ms pudar sebelum teksnya ditukar. */
  useEffect(() => {
    if (baris.length < 2) return;
    const t = setInterval(() => {
      setTampak(false);
      setTimeout(() => {
        setKe((n) => (n + 1) % baris.length);
        setTampak(true);
      }, 400);
    }, 6000);
    return () => clearInterval(t);
  }, [baris.length]);

  if (!baris.length) return null;

  return (
    <span
      style={{
        fontSize: 11,
        color: "var(--ink-3)",
        whiteSpace: "nowrap",
        opacity: tampak ? 1 : 0,
        transition: "opacity .4s",
      }}
      title="Zora ditarik tiap 30 menit; analis lain harian karena perlu LLM"
    >
      {baris[ke % baris.length]}
    </span>
  );
}
