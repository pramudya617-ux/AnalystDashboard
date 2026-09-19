/* DNS-over-HTTPS untuk sisi Node.
 *
 * Binance diblokir di lapis DNS di Indonesia: resolver jaringan memulangkan IP
 * internetpositif yang membalas 403. Proyek Python lama memecahkannya dengan
 * dns_doh.py; berkas ini melakukan hal yang sama untuk server Next.js.
 *
 * Yang ditambal HANYA resolusi namanya. Nama host aslinya tetap dipakai sebagai
 * SNI dan header Host, jadi sambungannya tetap sah - yang berubah cuma alamat
 * mana yang dihubungi.
 */
import https from "node:https";

const DOH = "https://cloudflare-dns.com/dns-query";
const UMUR_CACHE = 5 * 60 * 1000;
const cache = new Map();

async function alamat(host) {
  const c = cache.get(host);
  if (c && c.kedaluwarsa > Date.now()) return c.ip;

  const r = await fetch(`${DOH}?name=${encodeURIComponent(host)}&type=A`, {
    headers: { accept: "application/dns-json" },
    cache: "no-store",
  });
  if (!r.ok) throw new Error(`DoH HTTP ${r.status}`);
  const j = await r.json();
  const a = (j.Answer || []).filter((x) => x.type === 1); // type 1 = A record
  if (!a.length) throw new Error(`DoH tidak memulangkan alamat untuk ${host}`);

  const ip = a[0].data;
  cache.set(host, { ip, kedaluwarsa: Date.now() + UMUR_CACHE });
  return ip;
}

/* Host yang perlu ditembus. Domain lain dibiarkan memakai resolver biasa. */
const PERLU_DOH = /(^|\.)binance\.com$/;

export async function ambilJson(url, timeout = 15000) {
  const u = new URL(url);
  let lookup;

  if (PERLU_DOH.test(u.hostname)) {
    const ip = await alamat(u.hostname);
    /* Dua bentuk balasan. Node 20+ menyalakan autoSelectFamily, yang memanggil
       lookup dengan { all: true } dan menunggu ARRAY; bentuk lama menunggu
       sepasang argumen. Menjawab bentuk yang salah menghasilkan galat
       "Invalid IP address: undefined" yang sama sekali tidak menyebut DNS. */
    lookup = (_host, opsi, cb) =>
      opsi && opsi.all
        ? cb(null, [{ address: ip, family: 4 }])
        : cb(null, ip, 4);
  }

  return new Promise((selesai, gagal) => {
    const req = https.request(
      {
        hostname: u.hostname,          // tetap nama asli: SNI dan Host benar
        path: u.pathname + u.search,
        method: "GET",
        headers: { "User-Agent": "Mozilla/5.0", accept: "application/json" },
        lookup,
        timeout,
      },
      (res) => {
        let buf = "";
        res.setEncoding("utf8");
        res.on("data", (d) => (buf += d));
        res.on("end", () => {
          if (res.statusCode >= 400) {
            const e = new Error(`HTTP ${res.statusCode}`);
            e.status = res.statusCode;
            return gagal(e);
          }
          try {
            selesai(JSON.parse(buf));
          } catch (e) {
            gagal(new Error("balasan bukan JSON"));
          }
        });
      }
    );
    req.on("error", gagal);
    req.on("timeout", () => req.destroy(new Error("timeout")));
    req.end();
  });
}
