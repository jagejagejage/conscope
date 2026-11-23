"use client";

import Link from "next/link";
import { useDemoData } from "@/components/demo-data-provider";
import { CategoryPill, DemoMark, EmptyState, EventArtwork, EventMeta, LoadingState, PageHeading, PriceChart } from "@/components/ui";
import { formatCurrency } from "@/lib/demo-client";

export default function EventDetail({ trackedEventId }: { trackedEventId: string }) {
  const { snapshot, ready } = useDemoData();
  if (!ready || !snapshot) return <LoadingState />;
  const tracked = snapshot.trackedEvents.find((item) => item.id === trackedEventId);
  if (!tracked) return <EmptyState title="This event is not on your watchlist" description="It may have been removed from this browser or the link may be out of date." action={<Link href="/discover" className="button-primary inline-flex items-center px-4">Find an event</Link>} />;
  const latest = tracked.history.at(-1)?.perTicket ?? tracked.simulatedLow;
  return <>
    <PageHeading title="Event details" description="Your preferences and an illustrative history for this fictional event." action={<Link href="/watchlist" className="button-secondary inline-flex items-center justify-center px-4">Back to watchlist</Link>} />
    <div className="grid gap-6 xl:grid-cols-[minmax(0,1.4fr)_minmax(300px,.75fr)]">
      <section className="surface overflow-hidden rounded-2xl">
        <EventArtwork event={tracked.event} className="h-36 w-full rounded-none sm:h-48"/>
        <div className="p-5 sm:p-7"><div className="flex flex-wrap items-center gap-2"><CategoryPill category={tracked.event.category}/><DemoMark/></div><h2 className="mt-3 text-2xl font-bold tracking-tight sm:text-3xl">{tracked.event.name}</h2><div className="mt-3"><EventMeta event={tracked.event}/></div><p className="mt-3 text-sm text-muted">{tracked.event.time} · {tracked.event.region}</p><div className="mt-6 grid grid-cols-2 gap-3"><div className="rounded-xl bg-[#f5f7fa] p-4"><p className="text-xs text-muted">Your target</p><p className="mt-1 text-xl font-bold">{formatCurrency(tracked.targetPrice, tracked.currency)}<span className="ml-1 text-xs font-medium text-muted">/ ticket</span></p></div><div className="rounded-xl bg-[#f5f7fa] p-4"><p className="text-xs text-muted">Requested quantity</p><p className="mt-1 text-xl font-bold">{tracked.requestedQuantity} tickets</p></div></div>
          <div className="mt-6">{tracked.event.sourceUrl ? <a className="font-semibold text-[#3d5fbd] underline underline-offset-4" href={tracked.event.sourceUrl} target="_blank" rel="noreferrer">Open official event page</a> : <p className="text-sm leading-6 text-muted">No original ticket URL is included in this fictional sample.</p>}</div>
        </div>
      </section>
      <aside className="space-y-4"><div className="surface rounded-2xl p-5 sm:p-6"><div className="flex flex-wrap items-start justify-between gap-3"><div><p className="text-sm text-muted">Latest simulated example</p><p className="mt-1 text-3xl font-bold tracking-tight">{formatCurrency(latest, tracked.currency)}<span className="ml-1 text-sm font-medium text-muted">/ ticket</span></p></div><DemoMark/></div><p className="mt-3 text-xs leading-5 text-muted">This number is fictional. It does not represent a live listing, available quantity, fees, or an all-in price.</p></div><div className="surface rounded-2xl p-5 sm:p-6"><p className="text-sm font-semibold">Monitoring status</p><p className="mt-2 text-sm leading-6 text-muted">No checks are running. ConScope does not currently verify ticket offers or send alerts.</p><p className="mt-4 border-t border-[#edf0f4] pt-4 text-xs text-muted">{tracked.paused ? "This demo watch is paused." : "This demo watch is active as a saved preference only."}</p></div></aside>
    </div>
    <section className="surface mt-6 rounded-2xl p-5 sm:p-7"><div className="mb-3 flex flex-wrap items-end justify-between gap-3"><div><h2 className="section-title">Example price history</h2><p className="mt-1 text-sm text-muted">Illustrative per-ticket values · USD</p></div><DemoMark>Simulated data</DemoMark></div><PriceChart tracked={tracked} height={260}/></section>
  </>;
}
