"use client";

import { useMemo, useState } from "react";
import { useRouter } from "next/navigation";

const MENANG = ["untung", "target tersentuh"];
const KALAH = ["rugi", "invalidasi tersentuh"];
/* Pilihan koreksi memakai kosakata dashboard lama: level TP dan SL, bukan hanya
   kata "untung"/"rugi". Tiap pilihan menetapkan hasil DAN level TP sekaligus,
   karena keduanya harus konsisten - "TP2" tanpa hasil menang akan janggal. */
const PILIHAN_HASIL = [
  { nilai: "TP1", label: "TP 1 tersentuh", hasil: "target tersentuh", tpKe: "TP1" },
  { nilai: "TP2", label: "TP 2 tersentuh", hasil: "target tersentuh", tpKe: "TP2" },
  { nilai: "TP3", label: "TP 3 tersentuh", hasil: "target tersentuh", tpKe: "TP3" },
  { nilai: "FULLTP", label: "Full TP", hasil: "target tersentuh", tpKe: "Full TP" },
  { nilai: "SL", label: "SL kena", hasil: "invalidasi tersentuh", tpKe: null },
  { nilai: "untung", label: "untung", hasil: "untung", tpKe: null },
  { nilai: "rugi", label: "rugi", hasil: "rugi", tpKe: null },
  { nilai: "impas", label: "impas (BE)", hasil: "impas", tpKe: null },
  { nilai: "ditutup", label: "ditutup", hasil: "ditutup", tpKe: null },
  { nilai: "belum", label: "belum tersentuh", hasil: "belum tersentuh", tpKe: null },
];
const HPENDEK = {
  untung: "untung", rugi: "rugi", impas: "impas", ditutup: "ditutup",
  "target tersentuh": "target kena", "invalidasi tersentuh": "stop kena",
  "belum tersentuh": "belum kena", "tidak ada di Binance": "tak ada data",
  "harga tidak terambil": "tak ada data", "target tidak valid": "target tak valid",
};

const kelasHasil = (h) =>
  MENANG.includes(h) ? "untung" : KALAH.includes(h) ? "rugi" : "netral";
const tgl = (s) => (s ? new Date(s).toLocaleDateString("id-ID", { day: "2-digit", month: "short", year: "2-digit" }) : "—");
const kunciCall = (c) => c.sumber || `${c.aset}|${c.waktu}`;

/* Segmen koreksi. Hidup di laman rahasia, terpisah dari dashboard yang dilihat
   orang lain, karena di sini angka bisa diubah dan panggilan bisa dihapus. */
export default function TabelKoreksi({ data }) {
  const router = useRouter();
  const [terpilih, setTerpilih] = useState(
    () => data.analis.find((a) => a.calls.length)?.id || data.analis[0]?.id
  );
  const [cari, setCari] = useState("");
  const [edit, setEdit] = useState(null);
  const [sibuk, setSibuk] = useState(false);

  const analis = data.analis.find((a) => a.id === terpilih) || data.analis[0];

  const calls = useMemo(() => {
    const q = cari.trim().toLowerCase();
    const l = analis?.calls || [];
    return q ? l.filter((c) => `${c.aset} ${c.arah}`.toLowerCase().includes(q)) : l;
  }, [analis, cari]);

  async function kirim(muatan) {
    setSibuk(true);
    try {
      const r = await fetch("/api/koreksi", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(muatan),
      });
      const j = await r.json();
      if (!r.ok) throw new Error(j.error || "gagal menyimpan");
      setEdit(null);
      router.refresh();
    } catch (e) {
      alert(`Koreksi gagal: ${e.message}`);
    } finally {
      setSibuk(false);
    }
  }

  function hapus(c) {
    const alasan = prompt(
      `Hapus panggilan ${c.aset} (${tgl(c.waktu)})?\n\nAlasan wajib diisi dan tersimpan sebagai jejak:`
    );
    if (!alasan || !alasan.trim()) return;
    kirim({ kunci: kunciCall(c), dihapus: true, alasan });
  }

  return (
    <div className="layar">
      <div className="isi">
        <header className="kaca kepala">
          <div className="merek">Koreksi</div>
          <span className="tanda-ringkasan">laman internal</span>
          <div className="cari">
            <input value={cari} onChange={(e) => setCari(e.target.value)} placeholder="Cari aset…" />
          </div>
          <a className="pil" href="/">← dashboard</a>
        </header>

        <section className="kaca" style={{ marginBottom: 14 }}>
          <div className="panel-kepala">
            <div>
              <div className="judul">Pilih analis</div>
              <div className="judul-sub">{data.jumlahKoreksi} koreksi tersimpan</div>
            </div>
          </div>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 8, padding: "12px 16px 16px" }}>
            {data.analis.map((a) => (
              <button
                key={a.id}
                className={`pil ${a.id === terpilih ? "on" : ""}`}
                onClick={() => setTerpilih(a.id)}
              >
                {a.nama} · {a.ringkasanSaja ? "ringkasan" : `${a.calls.length}`}
              </button>
            ))}
          </div>
        </section>

        <section className="kaca">
          <div className="panel-kepala">
            <div>
              <div className="judul">{analis?.nama}</div>
              <div className="judul-sub">{calls.length} panggilan bisa dikoreksi</div>
            </div>
          </div>

          {calls.length === 0 ? (
            <div className="kosong">
              {analis?.ringkasanSaja
                ? "Analis ini hanya menampilkan ringkasan obrolan, jadi tidak ada panggilan untuk dikoreksi."
                : "Tidak ada panggilan pada rentang ini."}
            </div>
          ) : (
            <div className="tabel-bungkus">
              <table className="calls">
                <thead>
                  <tr>
                    <th>Aset</th><th>Arah</th><th>Masuk</th><th>Hasil</th>
                    <th>Imbal</th><th>Waktu</th><th>Sumber</th><th>Aksi</th>
                  </tr>
                </thead>
                <tbody>
                  {calls.map((c) => (
                    <tr key={kunciCall(c)}>
                      <td className="aset">{c.aset}</td>
                      <td><span className={`arah ${c.arah}`}>{c.arah}</span></td>
                      <td>{c.masuk ?? "—"}</td>
                      <td>
                        <span className={`hasil ${kelasHasil(c.hasilAkhir)}`}>
                          <i className={`titik ${c.sumberHasil === "harga" ? "lubang" : ""}`} />
                          {c.tpKe && MENANG.includes(c.hasilAkhir)
                            ? String(c.tpKe).toUpperCase()
                            : HPENDEK[c.hasilAkhir] || c.hasilAkhir || "—"}
                        </span>
                      </td>
                      <td className={`imbal ${(c.imbal ?? 0) >= 0 ? "plus" : "minus"}`}>
                        {typeof c.imbal === "number" ? `${c.imbal.toFixed(2)}%` : "—"}
                      </td>
                      <td style={{ color: "var(--ink-3)" }}>{tgl(c.waktu)}</td>
                      <td>
                        {c.sumber ? (
                          <a className="tautan-sumber" href={c.sumber} target="_blank" rel="noreferrer">
                            buka pesan
                          </a>
                        ) : <span style={{ color: "var(--ink-3)" }}>—</span>}
                      </td>
                      <td>
                        <div className="aksi">
                          <button onClick={() => setEdit(c)}>Koreksi</button>
                          <button className="bahaya" onClick={() => hapus(c)}>Hapus</button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
      </div>

      {edit && <Modal call={edit} sibuk={sibuk} onBatal={() => setEdit(null)} onSimpan={kirim} />}
    </div>
  );
}

function Modal({ call, onBatal, onSimpan, sibuk }) {
  const [pilihan, setPilihan] = useState("");
  const [imbal, setImbal] = useState(typeof call.imbal === "number" ? String(call.imbal) : "");
  const [alasan, setAlasan] = useState("");

  return (
    <div className="tirai" onClick={(e) => e.target === e.currentTarget && onBatal()}>
      <div className="modal">
        <h3>Koreksi {call.aset}</h3>
        <p className="ket">
          Alasan wajib diisi dan tersimpan bersama cap waktu, jadi setiap perubahan angka tetap
          bisa ditelusuri.
        </p>

        {/* Sumber panggilan: satu-satunya cara memastikan koreksi menyasar pesan
            yang benar sebelum angkanya diubah. */}
        <div className="baris-form">
          <label>Sumber panggilan</label>
          {call.sumber ? (
            <a className="tautan-sumber" href={call.sumber} target="_blank" rel="noreferrer">
              {call.sumber}
            </a>
          ) : (
            <span style={{ fontSize: 11.5, color: "var(--ink-3)" }}>
              tidak ada tautan pesan untuk panggilan ini
            </span>
          )}
        </div>

        <div className="baris-form">
          <label>Hasil</label>
          <select value={pilihan} onChange={(e) => setPilihan(e.target.value)}>
            <option value="">— biarkan seperti semula —</option>
            {PILIHAN_HASIL.map((o) => (
              <option key={o.nilai} value={o.nilai}>{o.label}</option>
            ))}
          </select>
        </div>

        <div className="baris-form">
          <label>Persentase imbal (%)</label>
          <input type="number" step="0.01" value={imbal}
                 onChange={(e) => setImbal(e.target.value)}
                 placeholder="mis. 4.25 atau -3.1" />
        </div>

        <div className="baris-form">
          <label>Alasan koreksi</label>
          <textarea value={alasan} onChange={(e) => setAlasan(e.target.value)}
                    placeholder="mis. analis menutup manual di TP2, harga Binance tidak mencerminkan itu" />
        </div>

        <div className="modal-aksi">
          <button className="btn-batal" onClick={onBatal}>Batal</button>
          <button className="btn-simpan" disabled={sibuk || !alasan.trim()}
                  onClick={() => {
                    const o = PILIHAN_HASIL.find((x) => x.nilai === pilihan);
                    onSimpan({
                      kunci: kunciCall(call),
                      hasil: o ? o.hasil : undefined,
                      tpKe: o ? o.tpKe : undefined,
                      imbal: imbal === "" ? undefined : imbal,
                      alasan,
                    });
                  }}>
            {sibuk ? "Menyimpan…" : "Simpan koreksi"}
          </button>
        </div>
      </div>
    </div>
  );
}
