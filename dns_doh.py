"""Menembus blokir DNS Binance, dipakai bersama serve.py dan fetch_discord.py.

TEMUAN TERUKUR: blokir Binance di Indonesia dijalankan di lapis DNS SAJA.

  - Resolver jaringan memulangkan 36.86.63.185 (internetpositif.id /
    aduankonten.id) untuk api.binance.com, dan alamat itu membalas
    {"error":403}.
  - Kueri ke 8.8.8.8 pun dicegat transparan, jadi mengganti DNS tidak menolong.
  - DNS-over-HTTPS lolos: port 443, terenkripsi, tidak bisa dicegat.
  - Menyambung LANGSUNG ke IP asli berhasil — HTTP 200 dalam 0,17 detik dengan
    data ticker sungguhan. Jadi IP-nya tidak diblokir dan SNI tidak disaring.
  - Terjadi di dua operator berbeda dengan IP blokir yang sama, jadi ini
    kebijakan nasional, bukan kebijakan satu operator.

Maka cukup resolusinya yang diperbaiki. Tidak perlu VPN, dan tidak perlu
mengubah berkas hosts — yang butuh hak admin dan basi begitu IP CloudFront
berputar.

Caranya: socket.getaddrinfo ditambal HANYA untuk host binance.com. Nama host
aslinya tetap dipakai http.client, sehingga SNI dan header Host tetap benar;
yang berubah hanya alamat yang disambungi.

Pakai: `import dns_doh` sekali di awal program. Menambalnya idempoten.
"""
import json
import socket
import time
import urllib.request

DOH = "https://cloudflare-dns.com/dns-query"
HOST_DITAMBAL = ("binance.com",)
_singgah = {}                      # host -> (waktu, ip)
_asli = socket.getaddrinfo


def resolusi(host, ttl=1800):
    """IP asli lewat DNS-over-HTTPS; None kalau tidak terjawab."""
    punya = _singgah.get(host)
    if punya and time.time() - punya[0] < ttl:
        return punya[1]
    try:
        r = urllib.request.Request(
            f"{DOH}?name={host}&type=A",
            headers={"accept": "application/dns-json",
                     "User-Agent": "Mozilla/5.0 (compatible; LQDashboard/1.0)"})
        with urllib.request.urlopen(r, timeout=10) as f:
            d = json.loads(f.read().decode("utf-8"))
        ip = next((a["data"] for a in d.get("Answer", []) if a.get("type") == 1), None)
        if ip:
            _singgah[host] = (time.time(), ip)
            return ip
    except Exception:                                        # noqa: BLE001
        pass
    return punya[1] if punya else None


def _tambal(host, port, *a, **kw):
    if isinstance(host, str) and host.endswith(HOST_DITAMBAL):
        ip = resolusi(host)
        if ip:
            host = ip
    return _asli(host, port, *a, **kw)


def pasang():
    if socket.getaddrinfo is not _tambal:
        socket.getaddrinfo = _tambal


def dns_bersih():
    """Apakah resolver bawaan sudah sampai ke Binance yang asli?

    Ditanyakan karena tambalan ini BERBAHAYA di tempat yang DNS-nya sehat. Dia
    memaku SATU alamat IP - yang pertama dari sudut pandang Cloudflare - untuk
    seluruh host binance.com selama setengah jam. Di laptop rumahan itu
    penyelamat. Di Railway itu justru membuang alamat tetangga yang dipilihkan
    jaringannya sendiri dan menggantinya dengan alamat pilihan resolver asing,
    yang bisa jauh atau menolak IP pusat data - dan gagalnya berpindah-pindah:
    daftar simbol futures gagal jam 13:45, lilinnya yang gagal jam 14:10.

    Satu permintaan ping sudah cukup menjawab, dan jawabannya pasti: kalau
    resolver bawaan sampai ke Binance asli, tambalan ini tidak punya urusan."""
    try:
        with urllib.request.urlopen(
                urllib.request.Request("https://api.binance.com/api/v3/ping",
                                       headers={"User-Agent": "Mozilla/5.0"}),
                timeout=8) as f:
            return f.status == 200
    except Exception:                                        # noqa: BLE001
        return False


if dns_bersih():
    print("[dns] resolver bawaan sampai ke Binance; tambalan DoH tidak dipasang")
else:
    pasang()
    print("[dns] resolusi Binance dialihkan lewat DNS-over-HTTPS")
