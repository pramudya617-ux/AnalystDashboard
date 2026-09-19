"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import HargaLangsung from "./HargaLangsung";
import GrafikTradingView from "./GrafikTradingView";
import GrafikMini from "./GrafikMini";
import Angka from "./Angka";
import StatusTarik from "./StatusTarik";
import PanelKinerja from "./PanelKinerja";

/* Disalin dari lib/data.js. Tidak bisa diimpor langsung karena modul itu memakai
   node:fs dan hanya hidup di sisi server. */
const MENANG = ["untung", "target tersentuh"];
const KALAH = ["rugi", "invalidasi tersentuh"];

const HPENDEK = {
  untung: "untung", rugi: "rugi", impas: "impas", ditutup: "ditutup",
  "target tersentuh": "target kena", "invalidasi tersentuh": "stop kena",
  "tidak ada di Binance": "tak ada data", "terlalu baru untuk dinilai": "terlalu baru",
  "harga tidak terambil": "tak ada data", "belum tersentuh": "belum kena", datar: "datar",
};

/* Dashboard lama menampilkan LEVEL TP di sel hasil (TP1/TP2/Full TP), bukan
   sekadar "target kena". Level itu jauh lebih informatif, jadi ditiru di sini. */
function labelHasil(c) {
  if (c.tpKe && MENANG.includes(c.hasilAkhir)) return String(c.tpKe).toUpperCase();
  return HPENDEK[c.hasilAkhir] || c.hasilAkhir || "—";
}

function kelasHasil(h) {
  if (MENANG.includes(h)) return "untung";
  if (KALAH.includes(h)) return "rugi";
  return "netral";
}

const pct = (n, d = 1) => (typeof n === "number" ? `${n.toFixed(d)}%` : "—");
const tgl = (s) => (s ? new Date(s).toLocaleDateString("id-ID", { day: "2-digit", month: "short" }) : "—");

/* ------------------------------------------------------------------ ikon */
const Ikon = ({ d, ...p }) => (
  <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor"
       strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round" {...p}>
    {d}
  </svg>
);
const iGrid = <><rect x="3" y="3" width="7" height="7" rx="2" /><rect x="14" y="3" width="7" height="7" rx="2" /><rect x="3" y="14" width="7" height="7" rx="2" /><rect x="14" y="14" width="7" height="7" rx="2" /></>;
const iChat = <path d="M21 11.5a8.4 8.4 0 0 1-9 8.4 8.9 8.9 0 0 1-4-.9L3 21l1.9-4.9A8.4 8.4 0 0 1 12 3a8.4 8.4 0 0 1 9 8.5z" />;
const iOrang = <><path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2" /><circle cx="9" cy="7" r="4" /><path d="M22 21v-2a4 4 0 0 0-3-3.87" /></>;
const iGrafik = <><path d="M3 3v18h18" /><path d="M7 15l4-4 3 3 5-6" /></>;
const iRoda = <><circle cx="12" cy="12" r="3" /><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.9l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-2.9 1.2V21a2 2 0 1 1-4 0v-.1A1.7 1.7 0 0 0 7 19.4a1.7 1.7 0 0 0-1.9.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0-1.2-2.9H1a2 2 0 1 1 0-4h.1A1.7 1.7 0 0 0 2.6 7a1.7 1.7 0 0 0-.3-1.9l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1A1.7 1.7 0 0 0 8 2.6h.1A2 2 0 1 1 12 1v.1A1.7 1.7 0 0 0 15 2.6a1.7 1.7 0 0 0 1.9-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0 1.2 2.9H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1.7z" /></>;
const iCari = <><circle cx="11" cy="11" r="7" /><path d="M20 20l-3.2-3.2" /></>;
const iKiri = <path d="M15 18l-6-6 6-6" />;
const iKanan = <path d="M9 18l6-6-6-6" />;
const iPanah = <path d="M7 17L17 7M9 7h8v8" />;

/* =========================================================== komponen utama */
export default function Dashboard({ data }) {
  const router = useRouter();
  const [terpilih, setTerpilih] = useState(
    () => data.analis.find((a) => !a.ringkasanSaja && a.calls.length)?.id || data.analis[0]?.id
  );
  const [cari, setCari] = useState("");
  const [callSorot, setCallSorot] = useState(null);
  const [chartPenuh, setChartPenuh] = useState(false);
  /* null = belum diketahui. Panel chart baru dirender setelah nilainya pasti,
     supaya server dan browser tidak merender susunan berbeda - React
     melaporkannya sebagai hydration mismatch. */
  const [layarKecil, setLayarKecil] = useState(null);
  useEffect(() => {
    const mq = window.matchMedia("(max-width: 820px)");
    const ubah = () => setLayarKecil(mq.matches);
    ubah();
    mq.addEventListener("change", ubah);
    return () => mq.removeEventListener("change", ubah);
  }, []);
  const [gabungan, setGabungan] = useState(false);

  /* Mode gabungan disusun sebagai "analis semu" berisi panggilan semua analis.
     Dengan begitu seluruh panel di bawahnya - corong, tabel, harga langsung,
     chart - bekerja apa adanya tanpa cabang khusus. */
  const semua = useMemo(() => {
    const calls = data.analis
      .filter((a) => !a.ringkasanSaja)
      .flatMap((a) => a.calls.map((c) => ({ ...c, _analis: a.nama })))
      .sort((x, y) => String(y.waktu || "").localeCompare(String(x.waktu || "")));
    const dinilai = calls.filter(
      (c) => MENANG.includes(c.hasilAkhir) || KALAH.includes(c.hasilAkhir)
    );
    const menang = dinilai.filter((c) => MENANG.includes(c.hasilAkhir)).length;
    const berimbal = calls.filter((c) => typeof c.imbal === "number");
    return {
      id: "__semua__",
      nama: "Semua panggilan",
      avatar: null,
      bot: false,
      ringkasanSaja: false,
      jumlahPesan: 0,
      calls,
      metrik: {
        nCall: calls.length,
        nDinilai: dinilai.length,
        menang,
        kalah: dinilai.length - menang,
        wr: dinilai.length ? (menang / dinilai.length) * 100 : null,
        imbalRata: berimbal.length
          ? berimbal.reduce((n, c) => n + c.imbal, 0) / berimbal.length
          : null,
      },
    };
  }, [data.analis]);

  /* Muat ulang data dari server tiap menit, supaya koreksi yang disimpan di
     halaman /koreksi dan hasil penarikan otomatis Zora muncul sendiri tanpa
     perlu menyegarkan halaman. router.refresh() hanya mengambil ulang data
     server, tidak membuang keadaan komponen seperti analis yang sedang dipilih. */
  useEffect(() => {
    const t = setInterval(() => router.refresh(), 60_000);
    return () => clearInterval(t);
  }, [router]);

  const analis = gabungan
    ? semua
    : data.analis.find((a) => a.id === terpilih) || data.analis[0];

  /* Tiga kartu atas: analis dengan panggilan terbanyak, seperti tiga kartu
     jejaring sosial di rancangan acuan. */
  const kartuAtas = useMemo(
    () => [...data.analis].filter((a) => !a.ringkasanSaja).sort((a, b) => b.calls.length - a.calls.length).slice(0, 3),
    [data.analis]
  );

  const callsTampil = useMemo(() => {
    const q = cari.trim().toLowerCase();
    const list = analis?.calls || [];
    return q ? list.filter((c) => `${c.aset} ${c.penulis} ${c.arah}`.toLowerCase().includes(q)) : list;
  }, [analis, cari]);

  /* Sebaran aset - menggantikan panel "Audience Location" di rancangan acuan. */
  const perAset = useMemo(() => {
    const peta = new Map();
    for (const c of analis?.calls || []) peta.set(c.aset, (peta.get(c.aset) || 0) + 1);
    const total = analis?.calls?.length || 1;
    return [...peta.entries()]
      .sort((a, b) => b[1] - a[1])
      .slice(0, 5)
      .map(([aset, n]) => ({ aset, n, persen: (n / total) * 100 }));
  }, [analis]);

  /* Pasangan unik milik analis ini, untuk panel harga langsung. Dibatasi sepuluh
     supaya satu putaran polling tetap ringan. */
  const pairs = useMemo(() => {
    const set = new Map();
    for (const c of analis?.calls || []) if (c.pair) set.set(c.pair, c.bursa || "spot");
    return [...set.entries()].slice(0, 10);
  }, [analis]);

  /* Call yang chartnya sedang dibuka. Kalau yang terpilih bukan milik analis
     ini (mis. baru berganti analis), jatuh ke panggilan pertamanya. */
  const call = useMemo(() => {
    const daftar = analis?.calls || [];
    if (callSorot && daftar.some((c) => c.sumber === callSorot.sumber)) return callSorot;
    return daftar.find((c) => c.pair) || daftar[0] || null;
  }, [callSorot, analis]);

  return (
    <div className="layar">
      {/* ------------------------------------------------------------ rail */}
      <nav className="rail">
        {/* Rail ini dulu cuma hiasan dari rancangan acuan. Sekarang isinya
            pintasan sungguhan: kembali ke ringkasan, lalu satu tombol untuk tiap
            analis yang segmennya berupa ringkasan obrolan (Jaxx dan Anthony). */}
        <button
          className={!analis?.ringkasanSaja ? "on" : ""}
          title="Kembali ke analis dengan panggilan"
          onClick={() => { setGabungan(false); setTerpilih(kartuAtas[0]?.id || data.analis[0]?.id); }}
        >
          <Ikon d={iGrid} />
        </button>

        {data.analis.filter((a) => a.ringkasanSaja).map((a) => (
          <button
            key={a.id}
            className={a.id === terpilih ? "on" : ""}
            title={`Ringkasan obrolan ${a.nama}`}
            onClick={() => setTerpilih(a.id)}
          >
            {a.avatar
              ? <img src={a.avatar} alt="" style={{ width: 24, height: 24, borderRadius: "50%" }} />
              : <Ikon d={iChat} />}
          </button>
        ))}

        <button
          className={gabungan ? "on" : ""}
          title={`Semua panggilan dari seluruh analis (${data.totalCall})`}
          onClick={() => setGabungan(!gabungan)}
        >
          <Ikon d={iGrafik} />
          <span className="lencana">{data.totalCall}</span>
        </button>
      </nav>

      <div className="isi">
        {/* -------------------------------------------------------- kepala */}
        <header className="kaca kepala">
          <div className="merek">Analyst</div>

          <button
            className={`pil ${data.mode === "6bulan" ? "on" : ""}`}
            onClick={() => router.push("/?mode=6bulan")}
            title="Riwayat enam bulan terakhir, win rate dihitung atas rentang yang sama"
          >
            6 bulan
          </button>
          <button
            className={`pil ${data.mode === "september" ? "on" : ""}`}
            onClick={() => router.push("/?mode=september")}
            title="Hanya panggilan sejak 1 September 2026"
          >
            Sejak September
          </button>

          <div className="cari">
            <Ikon d={iCari} width="15" height="15" style={{ color: "var(--ink-3)" }} />
            <input
              value={cari}
              onChange={(e) => setCari(e.target.value)}
              placeholder="Cari aset, arah, analis…"
            />
          </div>

          <StatusTarik
            jadwal={data.jadwal}
            /* Yang punya panggilan didahulukan: merekalah yang paling terasa
               kalau penarikan tertunda. */
            namaAnalis={data.analis
              .filter((x) => !x.ditarik)
              .sort((a, b) => b.calls.length - a.calls.length)
              .map((x) => x.nama)}
          />
        </header>

        <div className="kisi">
          {/* ================================================ kolom utama */}
          <div className="kolom">
            {/* kartu tiga analis teratas */}
            <div className="tiga">
              {kartuAtas.map((a) => (
                <button
                  key={a.id}
                  className="kaca kartu"
                  style={{ textAlign: "left", cursor: "pointer", border: a.id === terpilih ? "1px solid rgba(47,123,255,.4)" : undefined }}
                  onClick={() => { setGabungan(false); setTerpilih(a.id); }}
                >
                  <div className="kartu-kepala">
                    {a.avatar
                      ? <img className="lencana-avatar" src={a.avatar} alt="" />
                      : <div className="lencana-avatar" />}
                    <div>
                      <div className="kartu-nama">{a.nama}</div>
                      <div className="kartu-sub">
                        <Angka nilai={a.calls.length} /> panggilan
                      </div>
                    </div>
                    <span className="panah"><Ikon d={iPanah} width="15" height="15" /></span>
                  </div>
                  <div className="angka-besar">
                    <Angka nilai={a.metrik?.wr} desimal={1} akhiran="%" />
                    <span className="satuan">win rate</span>
                  </div>
                  <div className={`delta ${(a.metrik?.imbalRata ?? 0) >= 0 ? "naik" : "turun"}`}>
                    rata-rata imbal <Angka nilai={a.metrik?.imbalRata} desimal={2} akhiran="%" />
                  </div>
                </button>
              ))}
            </div>

            {!analis?.ringkasanSaja && (
              <PanelKinerja calls={analis?.calls || []} mode={data.mode} />
            )}

            {/* LAPTOP: chart penuh terbuka TEPAT DI BAWAH panel untung-rugi saat
                pratinjau di kolom kanan dipencet - posisi yang sama dengan mode
                ponsel, jadi tempat munculnya chart tidak berpindah-pindah
                tergantung lebar layar. */}
            {layarKecil === false && chartPenuh && call?.pair && (
              <section className="kaca">
                <div className="panel-kepala">
                  <div>
                    <div className="judul">
                      {call.aset}
                      <span style={{ color: "var(--ink-3)", fontWeight: 400 }}>/USDT</span>
                    </div>
                    <div className="judul-sub">
                      {call.arah} · {(call.waktu || "").slice(0, 16).replace("T", " ")}
                      {call.bursa === "futures" ? " · futures" : ""}
                    </div>
                  </div>
                  <div className="kanan">
                    <button className="nav-kecil" title="Tutup chart"
                            onClick={() => setChartPenuh(false)}>
                      <svg viewBox="0 0 24 24" width="14" height="14" fill="none"
                           stroke="currentColor" strokeWidth="2" strokeLinecap="round">
                        <path d="M18 6L6 18M6 6l12 12" />
                      </svg>
                    </button>
                  </div>
                </div>
                <GrafikTradingView
                  pair={call.pair} pasar={call.bursa} aset={call.aset}
                  arah={call.arah} waktu={call.waktu} tinggi={520} tanpaKepala
                />
              </section>
            )}


            {/* PONSEL: chart duduk TEPAT DI BAWAH panel untung-rugi. Di layar
                sempit kolom kanan jatuh ke paling bawah, jadi chart di sana
                praktis tidak pernah terlihat. */}
            {layarKecil === true && call?.pair && (
              <section className="kaca">
                <div className="panel-kepala">
                  <div>
                    <div className="judul">
                      {call.aset}
                      <span style={{ color: "var(--ink-3)", fontWeight: 400 }}>/USDT</span>
                    </div>
                    <div className="judul-sub">
                      {call.arah} · {(call.waktu || "").slice(0, 16).replace("T", " ")}
                      {call.bursa === "futures" ? " · futures" : ""}
                    </div>
                  </div>
                  <div className="kanan">
                    <button className="pil" onClick={() => setChartPenuh(!chartPenuh)}
                            title={chartPenuh ? "Kembali ke pratinjau" : "Buka chart TradingView"}>
                      {chartPenuh ? (
                        <svg viewBox="0 0 24 24" width="14" height="14" fill="none"
                             stroke="currentColor" strokeWidth="2" strokeLinecap="round"
                             strokeLinejoin="round">
                          <path d="M9 14L4 9l5-5" />
                          <path d="M20 20v-7a4 4 0 0 0-4-4H4" />
                        </svg>
                      ) : (
                        <svg viewBox="0 0 24 24" width="14" height="14" fill="none"
                             stroke="currentColor" strokeWidth="2" strokeLinecap="round"
                             strokeLinejoin="round">
                          <path d="M3 3v18h18" /><path d="M7 15l4-4 3 3 5-6" />
                        </svg>
                      )}
                      {chartPenuh ? "Pratinjau" : "TradingView"}
                    </button>
                  </div>
                </div>

                {chartPenuh ? (
                  <GrafikTradingView
                    pair={call.pair} pasar={call.bursa} aset={call.aset}
                    arah={call.arah} waktu={call.waktu} tinggi={380} tanpaKepala
                  />
                ) : (
                  <div style={{ position: "relative", padding: "0 10px 10px" }}>
                    <GrafikMini pair={call.pair} pasar={call.bursa} tinggi={190} />
                    <div
                      role="button" tabIndex={0}
                      title="Buka chart TradingView"
                      onClick={() => setChartPenuh(true)}
                      onKeyDown={(e) => e.key === "Enter" && setChartPenuh(true)}
                      style={{ position: "absolute", inset: 0, cursor: "pointer" }}
                    />
                  </div>
                )}
              </section>
            )}

            {/* isi analis: ringkasan saja ATAU tabel panggilan */}
            <section className="kaca">
              <div className="panel-kepala">
                <div>
                  <div className="judul">{analis?.nama}</div>
                  <div className="judul-sub">
                    {analis?.ringkasanSaja
                      ? "Ringkasan obrolan — riwayat panggilan sengaja tidak ditampilkan"
                      : `${callsTampil.length} panggilan ditampilkan`}
                  </div>
                </div>
                {analis?.ringkasanSaja && (
                  <div className="kanan">
                    <span className="tanda-ringkasan">ringkasan chat</span>
                  </div>
                )}
              </div>

              {analis?.belumDitarik ? (
                <div className="kosong">
                  Zora belum pernah ditarik. Jalankan <code>python tarik_zora.py</code> untuk
                  mengambil panggilannya dari channel {analis.kanal?.[0]}.
                </div>
              ) : analis?.ringkasanSaja ? (
                <div className="ringkasan-teks">{analis.ringkasan || "Belum ada ringkasan."}</div>
              ) : callsTampil.length === 0 ? (
                <div className="kosong">Tidak ada panggilan pada rentang ini.</div>
              ) : (
                <div className="tabel-bungkus">
                  <table className="calls">
                    <thead>
                      <tr>
                        {gabungan && <th>Analis</th>}
                        <th>Aset</th><th>Arah</th><th>Masuk</th><th>Hasil</th>
                        <th>Imbal</th><th>Waktu</th><th>Sumber</th>
                      </tr>
                    </thead>
                    <tbody>
                      {/* Indeks ikut masuk kunci karena ADA panggilan kembar dengan
                          tautan Discord yang sama persis; tanpa itu React membuang
                          salah satu barisnya. */}
                      {callsTampil.map((c, i) => (
                        <tr key={`${c.sumber || c.aset}-${c.waktu}-${i}`}>
                          {gabungan && (
                            <td style={{ color: "var(--ink-2)" }}>{c._analis}</td>
                          )}
                          <td
                            className="aset"
                            style={{ cursor: c.pair ? "pointer" : "default",
                                     color: c.sumber === call?.sumber ? "var(--biru-2)" : undefined }}
                            onClick={() => setCallSorot(c)}
                            title={c.pair ? "Tampilkan chart " + c.pair : "Aset ini tidak ada di Binance"}
                          >{c.aset}</td>
                          <td><span className={`arah ${c.arah}`}>{c.arah}</span></td>
                          <td>{c.masuk != null ? c.masuk : "—"}</td>
                          <td>
                            <span className={`hasil ${kelasHasil(c.hasilAkhir)}`}>
                              <i className={`titik ${c.sumberHasil === "harga" ? "lubang" : ""}`} />
                              {labelHasil(c)}
                            </span>
                          </td>
                          <td className={`imbal ${(c.imbal ?? 0) >= 0 ? "plus" : "minus"}`}>
                            {typeof c.imbal === "number" ? `${c.imbal.toFixed(2)}%` : "—"}
                          </td>
                          <td style={{ color: "var(--ink-3)" }}>{tgl(c.waktu)}</td>
                          <td>
                            {c.sumber ? (
                              <a className="tautan-sumber" href={c.sumber}
                                 target="_blank" rel="noreferrer" title="Buka pesan aslinya di Discord">
                                <svg viewBox="0 0 24 24" width="13" height="13" fill="none"
                                     stroke="currentColor" strokeWidth="2" strokeLinecap="round">
                                  <path d="M10 13a5 5 0 0 0 7 0l3-3a5 5 0 0 0-7-7l-1 1" />
                                  <path d="M14 11a5 5 0 0 0-7 0l-3 3a5 5 0 0 0 7 7l1-1" />
                                </svg>
                                Discord
                              </a>
                            ) : <span style={{ color: "var(--ink-3)" }}>—</span>}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </section>
          </div>

          {/* ================================================ kolom kanan */}
          <div className="kolom">
            <section className="kaca profil">
              {analis?.avatar
                ? <img src={analis.avatar} alt="" />
                : <div style={{ width: 62, height: 62, borderRadius: "50%", background: "rgba(255,255,255,.08)", margin: "0 auto" }} />}
              <div className="nama">{analis?.nama}</div>
              <div className="peran">{analis?.bot ? "Bot analis" : "Analis"}</div>
              <div className="metrik"><Angka nilai={analis?.jumlahPesan || 0} /> pesan</div>
            </section>

            <section className="kaca">
              <div className="panel-kepala">
                <div>
                  <div className="judul">Harga langsung</div>
                  <div className="judul-sub">Binance · perbarui tiap 20 detik</div>
                </div>
              </div>
              <HargaLangsung pairs={pairs} />
            </section>

            {layarKecil === false && call?.pair && (
              <section className="kaca">
                <div className="panel-kepala">
                  <div>
                    <div className="judul">{call.pair}</div>
                    <div className="judul-sub">
                      TradingView{call.bursa === "futures" ? " · futures" : ""}
                    </div>
                  </div>
                  <div className="kanan">
                    <button className="nav-kecil"
                            title={chartPenuh ? "Tutup chart besar" : "Buka chart besar"}
                            onClick={() => setChartPenuh(!chartPenuh)}>
                      <svg viewBox="0 0 24 24" width="14" height="14" fill="none"
                           stroke="currentColor" strokeWidth="2" strokeLinecap="round">
                        <path d="M15 3h6v6M9 21H3v-6M21 3l-7 7M3 21l7-7" />
                      </svg>
                    </button>
                  </div>
                </div>
                <div style={{ position: "relative", padding: "0 10px 10px" }}>
                  <GrafikMini pair={call.pair} pasar={call.bursa} tinggi={190} />
                  <div
                    role="button" tabIndex={0}
                    title="Buka chart besar di kolom utama"
                    onClick={() => setChartPenuh(true)}
                    onKeyDown={(e) => e.key === "Enter" && setChartPenuh(true)}
                    style={{ position: "absolute", inset: 0, cursor: "pointer" }}
                  />
                </div>
              </section>
            )}

            <section className="kaca">
              <div className="panel-kepala">
                <div>
                  <div className="judul">Aset terbanyak</div>
                  <div className="judul-sub">lima teratas</div>
                </div>
              </div>
              <div className="daftar">
                {perAset.length === 0 && <div className="kosong">Belum ada data.</div>}
                {perAset.map((a) => (
                  <div className="daftar-baris" key={a.aset}>
                    <span className="daftar-nama">{a.aset}</span>
                    <span className="bar-latar"><span className="bar-isi" style={{ width: `${a.persen}%` }} /></span>
                    <span className="daftar-nilai">{a.n}</span>
                  </div>
                ))}
              </div>
            </section>

            <section className="kaca">
              <div className="panel-kepala">
                <div>
                  <div className="judul">Semua analis</div>
                  <div className="judul-sub">{data.jumlahKoreksi} koreksi tersimpan</div>
                </div>
              </div>
              <div className="daftar">
                {data.analis.map((a) => (
                  <button
                    key={a.id}
                    className="daftar-baris"
                    onClick={() => setTerpilih(a.id)}
                    style={{ background: "none", border: 0, padding: 0, cursor: "pointer", textAlign: "left" }}
                  >
                    <span className="daftar-nama" style={{ color: a.id === terpilih ? "var(--ink)" : undefined }}>
                      {a.nama}
                    </span>
                    <span style={{ flex: 1, fontSize: 11, color: "var(--ink-3)" }}>
                      {a.ringkasanSaja ? "ringkasan chat" : a.belumDitarik ? "belum ditarik" : `${a.calls.length} call`}
                    </span>
                    <span className="daftar-nilai">{a.ringkasanSaja || a.belumDitarik ? "—" : pct(a.metrik?.wr, 0)}</span>
                  </button>
                ))}
              </div>
            </section>
          </div>
        </div>
      </div>

    </div>
  );
}
