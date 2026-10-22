import type { Metadata } from "next";
import type { ReactNode } from "react";

import Nav from "../components/Nav";
import "./globals.css";

export const metadata: Metadata = {
  title: "trace — AI authorship",
  description: "Know who — and what — wrote every line.",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body>
        <div className="flex min-h-screen">
          <Nav />
          <main className="flex-1 px-8 py-8">
            <div className="max-w-[1080px] mx-auto">{children}</div>
          </main>
        </div>
      </body>
    </html>
  );
}
