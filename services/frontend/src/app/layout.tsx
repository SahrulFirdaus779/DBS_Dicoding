import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "ZakatSight Enterprise Dashboard",
  description: "Platform analitik zakat berbasis AI untuk transparansi publik dan manajemen amil.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="id">
      <body className="antialiased min-h-screen p-4 md:p-8 flex justify-center bg-gray-200">
        {children}
      </body>
    </html>
  );
}
