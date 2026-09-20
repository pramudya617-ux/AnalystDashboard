import { alamatBalik } from "@/lib/discord";

/* Layar masuk. Komponen server, tanpa "use client": isinya cuma satu tautan,
   dan tautan tidak butuh JavaScript. */

const BIRU_DISCORD = "#5865F2";

const IkonDiscord = () => (
  <svg viewBox="0 0 24 24" width="18" height="18" fill="currentColor" aria-hidden="true">
    <path d="M20.3 4.9A19.8 19.8 0 0 0 15.4 3.4l-.2.5a18.3 18.3 0 0 1 3.9 1.7 12.9 12.9 0 0 0-11-1.7l-.2-.5A19.8 19.8 0 0 0 3.7 4.9C.9 9.1.2 13.2.5 17.2a19.9 19.9 0 0 0 6 3l.7-1.1a13 13 0 0 1-2-1l.5-.4a14.2 14.2 0 0 0 12.6 0l.5.4a13 13 0 0 1-2 1l.7 1.1a19.9 19.9 0 0 0 6-3c.4-4.7-.6-8.7-3.2-12.3zM8.3 14.8c-1.2 0-2.1-1.1-2.1-2.4s.9-2.4 2.1-2.4 2.2 1.1 2.2 2.4-1 2.4-2.2 2.4zm7.4 0c-1.2 0-2.1-1.1-2.1-2.4s.9-2.4 2.1-2.4 2.2 1.1 2.2 2.4-1 2.4-2.2 2.4z" />
  </svg>
);

export default function MasukDiscord({ sebab, galat }) {
  /* "belum-siap" hanya pernah dilihat oleh yang memasang, bukan oleh member,
     jadi di sanalah alamat balik yang dihitung server ditampilkan - satu
     ketidakcocokan garis miring di situ adalah penyebab paling sering
     "invalid_redirect_uri", dan menebaknya tanpa melihat angkanya itu lambat. */
  const memasang = sebab === "belum-siap";

  return (
    <div style={{ display: "grid", placeItems: "center", minHeight: "100vh", padding: 20 }}>
      <div className="kaca" style={{ width: 360, maxWidth: "100%", padding: 26, borderRadius: 22 }}>
        <div className="merek" style={{ marginBottom: 4 }}>Analyst</div>
        <p style={{ fontSize: 12.5, color: "var(--ink-2)", margin: "0 0 18px", lineHeight: 1.6 }}>
          Dashboard ini khusus member premium DRC. Masuk dengan akun Discord yang
          punya role premium di server.
        </p>

        {galat && (
          <p
            style={{
              fontSize: 12,
              color: sebab === "gangguan" ? "#f5c37b" : "#ff7b7b",
              background: "rgba(255,255,255,.04)",
              border: "1px solid var(--line-2)",
              borderRadius: "var(--r-sm)",
              padding: "10px 12px",
              margin: "0 0 14px",
              lineHeight: 1.6,
            }}
          >
            {galat}
          </p>
        )}

        {!memasang && (
          <a
            href="/api/auth/discord"
            style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              gap: 9,
              width: "100%",
              padding: "12px 16px",
              borderRadius: "var(--r-sm)",
              background: BIRU_DISCORD,
              color: "#fff",
              fontSize: 13.5,
              fontWeight: 600,
            }}
          >
            <IkonDiscord />
            {sebab === "ditolak" ? "Coba akun Discord lain" : "Masuk dengan Discord"}
          </a>
        )}

        {sebab === "ditolak" && (
          <p style={{ fontSize: 11, color: "var(--ink-3)", margin: "12px 0 0", lineHeight: 1.6 }}>
            Masih ditolak padahal role-nya sudah ada? Peramban ini mungkin masuk ke
            akun Discord yang berbeda. Buka discord.com, ganti akunnya, lalu coba lagi.
          </p>
        )}

        {/* Pembuka link dari dalam aplikasi Discord di HP kerap tidak membawa
            sesi discord.com-nya, sehingga member disuruh mengetik sandi padahal
            sudah masuk di aplikasi yang sama. Disebutkan di muka supaya tidak
            terlihat seperti dashboard-nya yang rusak. */}
        {!memasang && (
          <p style={{ fontSize: 11, color: "var(--ink-3)", margin: "12px 0 0", lineHeight: 1.6 }}>
            Membuka dari aplikasi Discord di HP? Pakai menu ⋯ → <b>Open in browser</b>{" "}
            supaya tidak diminta mengetik sandi Discord lagi.
          </p>
        )}

        {memasang && (
          <p style={{ fontSize: 11, color: "var(--ink-3)", margin: 0, lineHeight: 1.7 }}>
            Alamat balik yang dihitung server:
            <br />
            <code style={{ color: "var(--ink-2)", wordBreak: "break-all" }}>{alamatBalik()}</code>
            <br />
            Daftarkan alamat itu PERSIS di Discord Developer Portal → OAuth2 → Redirects.
          </p>
        )}
      </div>
    </div>
  );
}
