import "./globals.css";
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "SSGCheck Monitor",
  description: "3-model risk panel with threshold escalation to a human monitor",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="h-full">{children}</body>
    </html>
  );
}
