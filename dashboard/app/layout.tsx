import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "HERMES Mars Rover - Mission Control",
  description: "Live Mars rover simulation dashboard",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="font-mono" suppressHydrationWarning>
      <body className="bg-stone-950 text-amber-100 antialiased" suppressHydrationWarning>
        {children}
      </body>
    </html>
  );
}
