/** Dashboard analis: hanya baca berkas lokal, tanpa layanan luar saat build. */
const nextConfig = { experimental: { serverActions: { bodySizeLimit: '4mb' } } };
export default nextConfig;
