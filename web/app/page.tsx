"use client";

import Link from "next/link";
import { useDemoData } from "@/components/demo-data-provider";
import { DemoMark, EmptyState, LoadingState, PageHeading, SectionHeading, TrackedEventRow } from "@/components/ui";
import { formatCheckedAt } from "@/lib/demo-client";
import { Icon } from "@/components/icons";

export default function DashboardPage() {
  const { snapshot, ready } = useDemoData();
  if (!ready || !snapshot) return <LoadingState />;
  const tracked = snapshot.trackedEvents;
  const nextCheck = "No scheduled checks in demo mode";
  return (
    <>
      <PageHeading title="Your ticket watch" description="A calm place to keep an eye on the events you care about." action={<Link href="/discover" className="button-primary inline-flex items-center justify-center gap-2 px-4"><Icon name="plus" size={17}/> Find an event</Link>} />
      <div className="grid gap-4 sm:grid-cols-3">
        <div className="surface rounded-2xl p-5"><p className="text-[13px] text-muted">Events you’re watching</p><p className="mt-2 text-3xl font-bold tracking-tight">{tracked.length}</p><p className="mt-1 text-xs text-muted">Saved in this browser</p></div>
        <div className="surface rounded-2xl p-5"><p className="text-[13px] text-muted">Monitoring status</p><div className="mt-2 flex items-center gap-2 text-lg font-semibold"><span className="h-2.5 w-2.5 rounded-full bg-[#d69a39]"/>Demo only</div><p className="mt-1 text-xs text-muted">No live price checks run</p></div>
        <div className="surface rounded-2xl p-5"><p className="text-[13px] text-muted">Most recent demo check</p><p className="mt-2 text-lg font-semibold">{tracked.length ? formatCheckedAt(tracked[0].lastCheckedAt) : "Not available"}</p><p className="mt-1 text-xs text-muted">{nextCheck}</p></div>
      </div>

      <div className="mt-9 grid gap-8 xl:grid-cols-[minmax(0,1.45fr)_minmax(310px,.8fr)]">
        <section>
          <SectionHeading title="Your watchlist" action={<Link href="/watchlist" className="text-sm font-semibold text-[#3d5fbd]">Manage</Link>} />
          <div className="surface divide-y divide-[#edf0f4] rounded-2xl p-2 sm:p-3">
            {tracked.length ? tracked.slice(0, 4).map((item) => <TrackedEventRow key={item.id} tracked={item} />) : <div className="p-3"><EmptyState title="Start with an event" description="Search the fictional demo catalog and set a quantity and target for your watchlist." action={<Link href="/discover" className="button-primary inline-flex items-center px-4">Discover events</Link>} /></div>}
          </div>
        </section>
        <section>
          <SectionHeading title="Recent demo alerts" action={<DemoMark>Simulated</DemoMark>} />
          <div className="surface rounded-2xl p-5">
            {snapshot.alerts.length ? <div className="space-y-4">{snapshot.alerts.slice(0, 3).map((alert) => <div key={alert.id} className="flex gap-3"><span className="grid h-9 w-9 shrink-0 place-items-center rounded-xl bg-[#eef3ff] text-[#4566c1]"><Icon name="bell" size={17}/></span><div className="min-w-0"><p className="text-sm font-semibold">{alert.eventName}</p><p className="mt-1 text-xs leading-5 text-muted">{alert.message}</p><p className="mt-2 text-[11px] text-muted">{formatCheckedAt(alert.createdAt)} · Fictional result</p></div></div>)}</div> : <p className="text-sm leading-6 text-muted">No demo alerts yet. These examples are simulated and never sent by email.</p>}
            <p className="mt-5 border-t border-[#edf0f4] pt-4 text-xs leading-5 text-muted">Targets are preferences only. Displayed demo lows are not purchasable listings or verified all-in prices.</p>
          </div>
        </section>
      </div>
      <section className="mt-8 rounded-2xl bg-[#eaf0ff] p-5 sm:flex sm:items-center sm:justify-between sm:gap-5 sm:p-6">
        <div><p className="text-sm font-bold text-[#294785]">What this preview can do</p><p className="mt-1 max-w-2xl text-sm leading-6 text-[#49608e]">Explore the planned workflow using made-up events and prices. Changes stay on this device in browser storage.</p></div>
        <Link href="/settings" className="mt-4 inline-flex items-center gap-2 text-sm font-semibold text-[#294785] sm:mt-0">Demo settings <Icon name="arrow" size={16}/></Link>
      </section>
    </>
  );
}
