import "./globals.css";

export const metadata = {
  title: "Analyst — DRC",
  description: "Dashboard khusus analis: ringkasan obrolan, riwayat panggilan, dan koreksi manual.",
};

export default function RootLayout({ children }) {
  return (
    <html lang="id">
      <body>{children}</body>
    </html>
  );
}
