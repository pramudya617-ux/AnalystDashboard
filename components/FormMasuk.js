"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

/* Form masuk halaman koreksi. Sengaja tidak menyebut apa pun tentang isi
   halaman di baliknya, dan pesan galatnya tunggal - "kata sandi salah" - tanpa
   membedakan sebabnya. */
export default function FormMasuk() {
  const router = useRouter();
  const [sandi, setSandi] = useState("");
  const [galat, setGalat] = useState("");
  const [sibuk, setSibuk] = useState(false);

  async function kirim(e) {
    e.preventDefault();
    setSibuk(true);
    setGalat("");
    try {
      const r = await fetch("/api/koreksi-masuk", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ sandi }),
      });
      if (!r.ok) {
        const j = await r.json().catch(() => ({}));
        throw new Error(j.error || "Kata sandi salah");
      }
      router.refresh();
    } catch (e2) {
      setGalat(e2.message);
      setSandi("");
    } finally {
      setSibuk(false);
    }
  }

  return (
    <div style={{ display: "grid", placeItems: "center", minHeight: "100vh", padding: 20 }}>
      <form onSubmit={kirim} className="kaca" style={{ width: 300, padding: 24, borderRadius: 18 }}>
        <h1 style={{ fontSize: 16, margin: "0 0 14px" }}>Koreksi manual</h1>
        <div className="baris-form">
          <input
            type="password"
            value={sandi}
            onChange={(e) => setSandi(e.target.value)}
            placeholder="Kata sandi"
            autoFocus
          />
        </div>
        <button className="btn-simpan" style={{ width: "100%" }} disabled={sibuk || !sandi}>
          {sibuk ? "Memeriksa…" : "Masuk"}
        </button>
        {galat && (
          <p style={{ color: "#ff7b7b", fontSize: 12, margin: "10px 0 0" }}>{galat}</p>
        )}
      </form>
    </div>
  );
}
