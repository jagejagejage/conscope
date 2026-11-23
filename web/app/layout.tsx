import type { Metadata } from "next";
import type { ReactNode } from "react";
import { AppShell } from "@/components/app-shell";
import { DemoDataProvider } from "@/components/demo-data-provider";
import "./globals.css";

export const metadata: Metadata = {
  title: "ConScope — Ticket watch demo",
  description: "A local-only demonstration of ticket price watchlists.",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body>
        <DemoDataProvider>
          <AppShell>{children}</AppShell>
        </DemoDataProvider>
      </body>
    </html>
  );
}
