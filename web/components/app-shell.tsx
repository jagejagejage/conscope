"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";
import { Icon, type IconName } from "@/components/icons";

const navigation: { label: string; href: string; icon: IconName }[] = [
  { label: "Dashboard", href: "/", icon: "grid" },
  { label: "Discover", href: "/discover", icon: "search" },
  { label: "Watchlist", href: "/watchlist", icon: "ticket" },
  { label: "Settings", href: "/settings", icon: "settings" },
];

function BrandMark() {
  return (
    <div className="flex items-center gap-3">
      <div className="grid h-10 w-10 place-items-center rounded-[13px] bg-[#4168d5] text-white shadow-sm">
        <svg aria-hidden="true" width="24" height="24" viewBox="0 0 24 24" fill="none">
          <path d="M4 7.5a2.5 2.5 0 0 0 0 5v1a2.5 2.5 0 0 0 0 5h16a2.5 2.5 0 0 0 0-5v-1a2.5 2.5 0 0 0 0-5H4Z" stroke="currentColor" strokeWidth="1.6"/>
          <path d="M12.5 8.5v1.2m0 2.2v1.2m0 2.2v1.2" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round"/>
        </svg>
      </div>
      <span className="text-[19px] font-bold tracking-[-.045em]">ConScope</span>
    </div>
  );
}

function activePath(pathname: string, href: string) {
  return href === "/" ? pathname === "/" : pathname === href || pathname.startsWith(`${href}/`);
}

function currentTitle(pathname: string) {
  if (pathname.startsWith("/events/")) return "Event details";
  return navigation.find((item) => activePath(pathname, item.href))?.label ?? "ConScope";
}

export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  return (
    <div className="app-frame min-h-screen lg:flex">
      <a href="#main-content" className="sr-only z-50 rounded bg-white p-3 text-slate-900 focus:not-sr-only focus:fixed focus:left-4 focus:top-4">Skip to content</a>
      <aside className="sidebar hidden min-h-screen w-[244px] shrink-0 flex-col px-5 pb-6 pt-7 lg:flex">
        <Link href="/" className="mb-12 px-2" aria-label="ConScope home"><BrandMark /></Link>
        <p className="mb-3 px-3 text-[11px] font-semibold text-[#94a3b9]">YOUR TICKETS</p>
        <nav aria-label="Main navigation" className="space-y-1">
          {navigation.map((item) => {
            const active = activePath(pathname, item.href);
            return (
              <Link key={item.href} href={item.href} aria-current={active ? "page" : undefined} className={`flex min-h-11 items-center gap-3 rounded-xl px-3 text-sm font-medium transition-colors ${active ? "bg-[#263a5b] text-white" : "text-[#b2bfd1] hover:bg-white/7 hover:text-white"}`}>
                <Icon name={item.icon} size={18} />{item.label}
              </Link>
            );
          })}
        </nav>
        <div className="mt-auto rounded-2xl border border-white/10 bg-white/[.045] p-4">
          <div className="mb-2 flex items-center gap-2 text-sm font-semibold text-white"><span className="h-2 w-2 rounded-full bg-[#94cdb7]" />Demo mode</div>
          <p className="text-xs leading-5 text-[#aab7c9]">Prices and alerts here are fictional. Nothing is monitored or emailed.</p>
          <Link href="/settings" className="mt-3 inline-block text-xs font-semibold text-[#d2ddf0] underline decoration-white/25 underline-offset-4 hover:text-white">About this demo</Link>
        </div>
      </aside>

      <div className="main-area flex min-h-screen flex-1 flex-col">
        <header className="sticky top-0 z-30 border-b border-[#e1e6ed] bg-white/95 backdrop-blur-sm">
          <div className="flex h-[68px] items-center justify-between px-4 sm:px-7 lg:px-10">
            <Link href="/" className="lg:hidden" aria-label="ConScope home"><BrandMark /></Link>
            <h1 className="hidden text-[15px] font-semibold text-[#314258] lg:block">{currentTitle(pathname)}</h1>
            <div className="flex items-center gap-3">
              <span className="hidden rounded-full border border-[#d9e3f5] bg-[#f3f6ff] px-3 py-1.5 text-xs font-semibold text-[#3a569a] sm:inline-flex">Demonstration</span>
              <div aria-label="Demo user profile" className="grid h-9 w-9 place-items-center rounded-full bg-[#e6ecf8] text-xs font-bold text-[#3e5682]">CS</div>
            </div>
          </div>
          <div className="demo-banner px-4 py-2 text-[12px] leading-5 sm:px-7 lg:hidden">
            <span className="font-semibold">Demo only.</span> Fictional events and prices; no live checks or alerts.
          </div>
        </header>
        <main id="main-content" className="mx-auto w-full max-w-[1450px] flex-1 px-4 pb-24 pt-7 sm:px-7 sm:pt-9 lg:px-10 lg:pb-12">
          <div className="demo-banner mb-7 hidden items-center gap-2 rounded-xl border px-4 py-3 text-[13px] lg:flex">
            <span className="grid h-5 w-5 place-items-center rounded-full bg-[#d9e4ff]"><Icon name="info" size={13}/></span>
            <p><strong>Demonstration only.</strong> Every event and price is fictional. No live ticket checks or email alerts are active.</p>
          </div>
          {children}
        </main>
        <footer className="hidden border-t border-[#e1e6ed] px-10 py-4 text-xs text-[#748196] lg:block">ConScope demo · Your changes stay in this browser</footer>
      </div>

      <nav aria-label="Mobile navigation" className="fixed inset-x-0 bottom-0 z-40 grid grid-cols-4 border-t border-[#dfe5ed] bg-white/95 px-2 pb-[max(env(safe-area-inset-bottom),8px)] pt-2 backdrop-blur-md lg:hidden">
        {navigation.map((item) => {
          const active = activePath(pathname, item.href);
          return (
            <Link key={item.href} href={item.href} aria-current={active ? "page" : undefined} className={`flex min-h-14 flex-col items-center justify-center gap-1 rounded-xl text-[10px] font-semibold ${active ? "text-[#3559bd]" : "text-[#758297]"}`}>
              <Icon name={item.icon} size={20}/><span>{item.label}</span>
            </Link>
          );
        })}
      </nav>
    </div>
  );
}
