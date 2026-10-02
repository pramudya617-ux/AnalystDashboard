# Replikasi: dashboard berbayar di balik login Discord

Panduan membangun ulang sistem ini untuk komunitas lain. Ditulis untuk dibaca
agen atau orang yang belum pernah melihat repo ini.

Yang dijelaskan di sini adalah **keputusan dan jebakannya**, bukan tutorial
Next.js. Kode aslinya ada di repo ini dan bisa disalin apa adanya.

---

## 1. Apa yang dibangun

Dashboard web berisi data berbayar, hanya bisa dibuka anggota Discord yang punya
role tertentu, plus kartu pengumuman bertombol yang diposting bot ke channel.

Tiga bagian, dan hanya bagian pertama yang benar-benar generik:

| Bagian | Generik? | Berkas |
|---|---|---|
| **Gerbang login role Discord** | Ya, salin apa adanya | `lib/discord.js`, `lib/gerbang.js`, `lib/sesi.js`, `app/api/auth/discord/route.js`, `components/MasukDiscord.js`, `components/TombolKeluar.js` |
| **Header keamanan** | Ya | `next.config.mjs` |
| **Pengumuman bot ke Discord** | Ya, ganti konstanta di atas berkas | `umumkan.py` |
| Pipeline data analis (Discord → LLM → harga Binance) | Tidak, khas DRC | `fetch_discord.py`, `tarik_zora.py`, `lib/data.js` |

Stack: Next.js 15 App Router + React 19, **JavaScript tanpa TypeScript**, tanpa
Tailwind, tanpa pustaka auth. Total dependency: `next`, `react`, `react-dom`.
Deploy di Railway.

---

## 2. Alur login

```
Pengunjung  →  /  →  gerbang()  →  tidak ada sesi  →  layar "Masuk dengan Discord"
                                       ↓ klik
                        /api/auth/discord  (tanpa ?code)
                                       ↓ 303
                        discord.com/oauth2/authorize?scope=identify&prompt=none
                                       ↓ balik dengan ?code
                        /api/auth/discord  (dengan ?code)
                          1. cocokkan state dengan cookie
                          2. tukar code → access_token
                          3. GET /users/@me → user ID
                          4. BOT baca GET /guilds/{id}/members/{userId} → roles
                          5. role cocok? → set cookie HMAC 12 jam
                                       ↓
                        /  →  gerbang()  →  periksa role LAGI  →  dashboard
```

### Kenapa scope-nya cuma `identify`

Role **tidak** ditanyakan ke pengguna lewat scope `guilds.members.read`. Role
dibaca oleh bot yang sudah jadi anggota server. Dua untungnya:

- Layar izin yang dilihat member cuma menyebut username dan avatar. Jauh lebih
  tidak menakutkan, dan ini menentukan berapa banyak orang menyelesaikan login.
- Rolenya datang dari sumber yang tidak bisa dipengaruhi penggunanya sendiri.

### Kenapa role diperiksa tiap permintaan, bukan sekali saat login

Cookie hidup 12 jam. Kalau role hanya diperiksa saat login, orang yang berhenti
berlangganan tetap bisa membaca sampai setengah hari berikutnya.

Jadi tiketnya hanya menjawab **"ini siapa"**. Yang menjawab **"boleh masuk?"**
tetap Discord, tiap kali halaman dirender, dengan singgahan lima menit di memori
supaya tidak satu panggilan API per muat halaman.

**Kegagalan jaringan JANGAN disinggahi sebagai "tidak punya role".** Gangguan
sesaat akan mengunci semua member selama lima menit berikutnya. `periksaRole()`
melempar galat untuk kasus itu, dan pemanggilnya membedakan "ditolak" dari
"tidak bisa diperiksa".

---

## 3. Keputusan yang menghemat waktu

### Gerbang di server component, BUKAN middleware

Middleware Next.js berjalan di runtime Edge, yang tidak punya `node:crypto`
bentuk penuh maupun akses berkas. Repo ini sudah dua kali gagal build gara-gara
Edge (`instrumentation.js` dan alias webpack). Halaman `/` sudah
`force-dynamic`, jadi pemeriksaannya cukup di server component — tanpa Edge,
tanpa masalah.

### Satu fungsi gerbang, dipakai halaman DAN rute API

`lib/gerbang.js` adalah satu-satunya tempat keputusan "boleh masuk?" dibuat.
Alasannya terbukti mahal di repo ini: rute `/api/koreksi` pernah terbuka lebar
sementara halamannya meminta sandi, karena penjagaannya ditulis dua kali dan
yang satu ketinggalan.

Kalau menambah rute API baru yang membaca data berbayar, panggil `gerbang()`.
Jangan tulis ulang pemeriksaannya.

### Kunci HMAC terpisah untuk tiap jenis sesi

Sistem ini punya dua sesi: **member** (lewat Discord) dan **admin** (lewat kata
sandi, untuk halaman koreksi). Keduanya ditandatangani dengan kunci **berbeda**.

Kalau kuncinya sama, cookie member tinggal disalin ke nama cookie admin dan
pemegangnya mendapat akses admin. Nama cookie bukan pengaman.

Kunci member diturunkan dari `DISCORD_CLIENT_SECRET` — yang memang sudah wajib
ada untuk OAuth, jadi tidak ada variabel rahasia tambahan yang bisa lupa diisi.
Efek sampingnya benar: memutar client secret mengeluarkan semua orang.

### Gagal ke arah tertutup

Kalau environment belum lengkap, semua orang **ditolak**, bukan diam-diam
diizinkan. Konsekuensinya: variabel harus diisi **sebelum** kode tayang.

Ini juga berarti **menghapus variabel bukan cara mematikan login** — malah
mengunci semua orang termasuk dirimu sendiri. Untuk membuka kembali, revert
commitnya.

### Jalan pintas pengembangan yang tidak bisa menyala di produksi

`TANPA_LOGIN=1` melewati gerbang, tapi dikunci ke `NODE_ENV !== "production"`.
Tanpa itu, pengembangan di laptop mustahil kecuali punya aplikasi OAuth sendiri.
Dengan kunci ganda, variabelnya boleh ikut tersalin ke server tanpa bahaya.

---

## 4. Jebakan yang memakan waktu

Urut dari yang paling sering kena.

### `Invalid OAuth2 redirect_uri`

Discord mencocokkan **karakter per karakter**. Penyebabnya hampir selalu salah
satu dari ini:

- URI-nya tidak benar-benar tersimpan. Setelah menambah redirect, ada bar
  **Save Changes** di bawah halaman yang mudah terlewat. **Refresh halamannya**
  untuk memastikan.
- Tertempel di **OAuth2 URL Generator**, bukan di daftar **Redirects**. Memilih
  URI di dropdown generator tidak mendaftarkan apa pun.
- `http` vs `https`, ada garis miring di ujung, atau path `/api/auth/discord`
  tidak ikut.

**Cara mendiagnosis dalam 5 detik:** saat layar error Discord muncul, alamat di
address bar memuat `&redirect_uri=...`. Itulah yang server kirim. Bandingkan
dengan yang terdaftar.

**Cara menghilangkan tebakan selamanya:** isi `APP_URL` secara eksplisit. Kode
ini bisa menurunkannya dari `RAILWAY_PUBLIC_DOMAIN`, tapi `APP_URL` menang atas
segalanya.

### SERVER MEMBERS INTENT TIDAK diperlukan

`GET /guilds/{id}/members/{userId}` — mengambil **satu** member — jalan tanpa
intent itu. Yang membutuhkannya hanya endpoint **daftar** member
(`GET /guilds/{id}/members`), dan kode ini tidak memakainya.

Sudah diuji terhadap tiga user sungguhan. Jangan buang waktu menyalakannya.

### Satu komunitas bisa punya BEBERAPA role berbayar

DRC punya `Premium` dan `Premium+`, dan keduanya **tidak saling mencakup** —
ada member yang punya `Premium+` tanpa `Premium`. Kalau hanya satu yang
didaftarkan, separuh pelanggan tertolak.

`PREMIUM_ROLE_IDS` menerima daftar dipisah koma. Sebelum tayang, periksa satu
per satu role berbayar yang ada di server.

### Dua sumber data, satu yang ditulis

Pola bug yang sudah muncul **tiga kali** di repo ini, dalam bentuk berbeda:

Data dibaca dari gabungan dua tempat (bawaan repo + volume permanen), tapi
hanya volume yang ditulis. Akibatnya **penghapusan tidak pernah berhasil** —
entri yang asalnya dari repo terbaca lagi dari sana.

Solusinya: tulis **nisan** (`{ dibatalkan: true }`) yang menimpa entri repo,
bukan menghapus kunci. Dan yang menulis **wajib membawa nisan lama serta** —
nisan yang ikut terhapus akan membangkitkan lagi apa yang ditandainya.

**Penting:** bug kelas ini **tidak muncul di laptop** kalau `DATA_DIR` tidak
diset, karena repo dan volume jatuh ke berkas yang sama. Untuk mengujinya,
arahkan `DATA_DIR` ke folder kosong terpisah.

### Railway: push = deploy = langsung kena member

Tidak ada tahap staging. Urutannya wajib:

1. Isi variabel di Railway
2. Daftarkan redirect URI di Discord
3. **Baru** push

Terbalik berarti dashboard menampilkan "belum dikonfigurasi" ke semua member
sampai variabelnya diisi.

Cabang tidak di-deploy Railway, jadi PR aman untuk meninjau tanpa menyentuh
produksi.

### Izin bot di channel bisa dicabut diam-diam

Bot yang kemarin bisa memposting bisa membalas 403 hari ini kalau ada yang
mengubah permission channel. Periksa izin **sebelum** mengirim, jangan biarkan
gagal saat kirim — Discord membalas "Missing Permissions" tanpa menyebut izin
mana yang kurang.

`umumkan.py` melakukan ini di fungsi `izin()`, lengkap dengan urutan resolusi
permission Discord yang benar (base role → overwrite @everyone → overwrite role
→ overwrite anggota).

### Banner: unggah, jangan tautkan

Pesan pengumuman akan dipin permanen. Tautan ke imgur atau CDN pihak ketiga
bisa mati kapan saja, dan yang tersisa kotak kosong selamanya.

Unggah berkasnya sebagai lampiran, lalu embed menunjuk `attachment://banner.png`.

Dan kalau memakai imgur sebagai sumber: `imgur.com/xxx` itu **halaman HTML**.
Yang dibutuhkan `i.imgur.com/xxx.png`.

### CSP akan mematikan chart kalau asalnya terlewat

Kalau dashboard memuat widget pihak ketiga, CSP harus menyebut semua asalnya.
Satu terlewat → halaman blank **tanpa pesan galat**.

Uji di mode produksi, bukan cuma dev. `'unsafe-eval'` hanya dibutuhkan webpack
saat pengembangan — nyalakan dev-only.

`'unsafe-inline'` pada `script-src` tidak bisa dihindari tanpa middleware nonce,
dan itu berarti Edge runtime lagi. Nilai A di securityheaders.com adalah plafon
yang wajar; A+ tidak sepadan dengan risiko build.

### Mesin Windows: bash vs PowerShell

`VAR=nilai perintah`, `printf`, `&&` — semuanya bash, dan gagal di PowerShell.
Padanannya:

```powershell
$env:VAR = "nilai"; python skrip.py
Add-Content .gitignore "`n__pycache__/"
perintahA; if ($?) { perintahB }
```

---

## 5. Yang harus diganti untuk komunitas lain

### Variabel environment

| Variabel | Dari mana | Catatan |
|---|---|---|
| `DISCORD_CLIENT_ID` | Developer Portal → OAuth2 | bukan rahasia |
| `DISCORD_CLIENT_SECRET` | Developer Portal → OAuth2 → **Reset Secret** | tab OAuth2, **bukan** tab Bot |
| `DISCORD_BOT_TOKEN` | Developer Portal → Bot | **jangan reset kalau bot sudah dipakai hal lain** |
| `DISCORD_GUILD_ID` | klik kanan server → Copy ID | |
| `PREMIUM_ROLE_IDS` | klik kanan tiap role → Copy ID | pisah koma, **semua** role berbayar |
| `APP_URL` | domain produksi | tanpa garis miring di ujung |
| `DATA_DIR` | mount path volume | harus di luar folder aplikasi |

Developer Mode harus menyala di Discord (Settings → Advanced) agar Copy ID muncul.

### Nilai di dalam kode

- `umumkan.py`: `CHANNEL`, `GUILD`, `ROLE_PING`, `JUDUL`, `ISI`, `WARNA`, `KAKI`
- `components/MasukDiscord.js`: nama komunitas di teks sambutan
- `next.config.mjs`: daftar asal di CSP, kalau widget pihak ketiganya berbeda

### Yang TIDAK perlu ditiru

Seluruh pipeline data (`fetch_discord.py`, `tarik_zora.py`, `lib/data.js`,
`components/Dashboard.js`) khas kasus DRC: menarik panggilan trading dari
Discord, menilai hasilnya dengan harga Binance, dan menampilkan win rate.
Komunitas lain hampir pasti menampilkan data yang sama sekali berbeda.

Yang dipakai ulang hanya **gerbangnya**.

---

## 6. Urutan pemasangan

1. Buat aplikasi Discord, undang botnya ke server (scope `bot`, permission
   `View Channels` + `Read Message History`)
2. Developer Portal → OAuth2 → Redirects → tambah
   `https://<domain>/api/auth/discord` → **Save Changes** → refresh untuk
   memastikan tersimpan
3. Isi semua variabel di host
4. Salin berkas gerbang dari repo ini
5. Panggil `gerbang()` di halaman dan tiap rute API yang menyajikan data berbayar
6. Deploy
7. **Uji dengan akun yang TIDAK punya role premium** — ini yang paling sering
   dilewati, dan satu-satunya cara membuktikan gerbangnya benar-benar menutup

### Cara menguji tanpa akun kedua

Buat tiket member bertanda tangan untuk user ID sembarang, lalu pasang sebagai
cookie:

```python
import hmac, hashlib, time
exp = int(time.time()) + 3600
uid = "<user id yang akan diuji>"
isi = f"{exp}.{uid}"
print(isi + "." + hmac.new(b"<DISCORD_CLIENT_SECRET>", isi.encode(), hashlib.sha256).hexdigest())
```

Yang harus terjadi:

- tanda tangan salah → layar masuk, **nol baris data terkirim**
- tanda tangan sah tapi user bukan anggota server → ditolak
- tanda tangan sah dan rolenya cocok → dashboard terbuka

---

## 7. Kalau membangun dari nol, lakukan ini sejak awal

- **Tombol keluar dibuat bersamaan dengan login.** Di sini rutenya ada sejak
  awal tapi tombolnya baru menyusul, dan selama itu member tidak punya cara
  keluar sama sekali — termasuk yang masuk ke akun Discord yang salah dan
  terjebak di layar penolakan.
- **Header keamanan sejak commit pertama.** Satu berkas konfigurasi, F → A.
- **Satu fungsi gerbang sebelum rute API kedua ditulis.**
- **Uji dengan `DATA_DIR` terpisah sejak awal** kalau memakai volume permanen.

---

## 8. Komentar di repo ini layak dibaca

Kode di sini menjelaskan **kenapa**, bukan apa. Beberapa yang paling berharga:

- `lib/discord.js` — kenapa scope `identify` dan kenapa role dicek tiap request
- `lib/gerbang.js` — kenapa satu pintu
- `lib/sesi.js` — kenapa kunci HMAC dipisah
- `lib/data.js` (`tulisKoreksi`) — pola bug dua sumber data
- `next.config.mjs` — kenapa CSP dipasang belakangan dan tanpa `preload`
- `umumkan.py` — kenapa link button tidak butuh gateway
- `lib/penjadwal.js` — kenapa `eval("require")` dipakai untuk menghindari webpack

Kalau menyalin berkasnya, **bawa komentarnya**. Hampir semuanya ditulis setelah
sesuatu rusak di produksi.
