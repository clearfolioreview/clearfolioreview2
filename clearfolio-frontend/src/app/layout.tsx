import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title:       "Clearfolio Review",
  description: "Privacy-first AI contract auditor. No data leaves your system.",
  icons: {
    icon: "data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'><text y='26' font-size='26'>⚖</text></svg>",
  },
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
        <link
          href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;600;700&family=Inter:wght@300;400;500&family=IBM+Plex+Mono:wght@400;500;600&display=swap"
          rel="stylesheet"
        />
      </head>
      <body style={{ fontFamily: "'Inter', sans-serif" }}>
        {children}
      </body>
    </html>
  );
}
