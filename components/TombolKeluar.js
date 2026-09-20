"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

/* Tombol keluar.
 *
 * Rute DELETE-nya sudah ada sejak login dipasang, tapi TIDAK ADA satu pun
 * tombol yang memanggilnya - jadi member tidak punya cara keluar sama sekali.
 * Dua keadaan yang membuatnya perlu, dan keduanya nyata:
 *
 *   1. Salah akun Discord. Layar penolakan menyuruh "coba akun lain", padahal
 *      cookie-nya masih menempel: tanpa tombol ini nasihat itu tidak bisa
 *      dijalankan.
 *   2. Komputer bersama. Sesi hidup 12 jam dan menempel di peramban orang lain.
 *
 * Memakai location.assign, BUKAN router.refresh(): cookie dihapus lewat header
 * balasan, dan router.refresh() hanya mengambil ulang muatan server tanpa
 * membuang keadaan komponen yang sudah dirender. Muat ulang penuh memastikan
 * layar yang tampak benar-benar layar orang yang sudah keluar.
 */
export default function TombolKeluar({ label = "Keluar", className = "pil" }) {
  const router = useRouter();
  const [sibuk, setSibuk] = useState(false);

  async function keluar() {
    setSibuk(true);
    try {
      await fetch("/api/auth/discord", { method: "DELETE" });
    } catch {
      /* Gagal jaringan pun tetap muat ulang: kalau cookie-nya ternyata sudah
         terhapus, halaman berikutnya yang akan memberitahukannya. */
    }
    window.location.assign("/");
  }

  return (
    <button className={className} onClick={keluar} disabled={sibuk} title="Keluar dari dashboard">
      {sibuk ? "Keluar…" : label}
    </button>
  );
}
