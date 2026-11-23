"use client";

import Link from "next/link";
import { useState } from "react";
import { useDemoData } from "@/components/demo-data-provider";
import { DemoMark, EmptyState, EventArtwork, LoadingState, PageHeading } from "@/components/ui";
import { Icon } from "@/components/icons";
import { formatCurrency, formatEventDate } from "@/lib/demo-client";
import type { TrackedEvent } from "@/lib/types";

export default function WatchlistPage() {
  const { client, snapshot, ready, reload } = useDemoData();
  const [editing, setEditing] = useState<string | null>(null);
  const [quantity, setQuantity] = useState("");
  const [target, setTarget] = useState("");
  const [error, setError] = useState("");
  if (!ready || !snapshot) return <LoadingState />;

  async function save(item: TrackedEvent) {
    const qty = Number(quantity); const price = Number(target);
    if (!Number.isInteger(qty) || qty < 1 || qty > 8 || !Number.isFinite(price) || price <= 0 || price > 10000) { setError("Use a quantity from 1 to 8 and a target between $0.01 and $10,000."); return; }
    await client.updateTrackedEvent(item.id, { requestedQuantity: qty, targetPrice: price });
    setEditing(null); setError(""); await reload();
  }

  return <>
    <PageHeading title="Watchlist" description="Adjust your demo targets or pause items. This list is saved in this browser only." action={<Link href="/discover" className="button-primary inline-flex items-center justify-center gap-2 px-4"><Icon name="plus" size={17}/> Add an event</Link>} />
    {snapshot.trackedEvents.length === 0 ? <EmptyState title="Your watchlist is empty" description="Search the demo catalog and choose how many tickets and what per-ticket target to watch." action={<Link href="/discover" className="button-primary inline-flex items-center px-4">Find an event</Link>}/> : <div className="space-y-4">{snapshot.trackedEvents.map((item) => <article className="surface rounded-2xl p-4 sm:p-5" key={item.id}><div className="flex flex-col gap-4 sm:flex-row sm:items-center"><EventArtwork event={item.event} className="h-[78px] w-[78px] shrink-0 sm:h-[90px] sm:w-[110px]"/><div className="min-w-0 flex-1"><div className="flex flex-wrap items-center gap-2"><h2 className="font-semibold">{item.event.name}</h2><DemoMark/>{item.paused && <span className="pill border border-[#dce2ea] bg-white text-[#728096]">Paused</span>}</div><p className="mt-1 text-sm text-muted">{formatEventDate(item.event.date)} · {item.event.venue}, {item.event.city}</p><div className="mt-3 flex flex-wrap gap-x-5 gap-y-1 text-xs text-muted"><span>Quantity <strong className="text-[#25354c]">{item.requestedQuantity}</strong></span><span>Target <strong className="text-[#25354c]">{formatCurrency(item.targetPrice, item.currency)} / ticket</strong></span><span>Demo low <strong className="text-[#25354c]">{formatCurrency(item.simulatedLow, item.currency)}</strong></span></div></div><div className="flex flex-wrap gap-2 sm:justify-end"><Link href={`/events/${item.id}`} className="button-secondary inline-flex min-h-10 items-center gap-2 px-3 text-sm">Details <Icon name="arrow" size={15}/></Link><button onClick={() => void client.updateTrackedEvent(item.id, { paused: !item.paused }).then(reload)} className="button-secondary inline-flex min-h-10 items-center gap-2 px-3 text-sm" type="button"><Icon name={item.paused ? "play" : "pause"} size={15}/>{item.paused ? "Resume" : "Pause"}</button><button onClick={() => {setEditing(editing === item.id ? null : item.id);setQuantity(String(item.requestedQuantity));setTarget(String(item.targetPrice));setError("");}} className="button-secondary grid min-h-10 w-10 place-items-center" type="button" aria-label={`Edit ${item.event.name}`}><Icon name="edit" size={16}/></button><button onClick={() => {if (window.confirm(`Remove ${item.event.name} from this demo watchlist?`)) void client.removeTrackedEvent(item.id).then(reload);}} className="button-secondary button-danger grid min-h-10 w-10 place-items-center" type="button" aria-label={`Remove ${item.event.name}`}><Icon name="trash" size={16}/></button></div></div>
        {editing === item.id && <div className="mt-5 border-t border-[#edf0f4] pt-4"><div className="grid gap-3 sm:grid-cols-[1fr_1fr_auto] sm:items-end"><label className="text-sm font-semibold">Quantity<input className="input-field mt-2" type="number" min="1" max="8" step="1" value={quantity} onChange={(e) => setQuantity(e.target.value)}/></label><label className="text-sm font-semibold">Target per ticket (USD)<span className="mt-2 flex min-h-12 items-center rounded-[11px] border border-[#cdd6e2] bg-white px-3"><span className="mr-2 text-muted">$</span><input className="w-full bg-transparent outline-none" type="number" min="0.01" max="10000" step="0.01" value={target} onChange={(e) => setTarget(e.target.value)}/></span></label><button type="button" onClick={() => void save(item)} className="button-primary px-5">Save changes</button></div>{error && <p role="alert" className="mt-2 text-sm text-red-700">{error}</p>}</div>}
      </article>)}</div>}
    <p className="mt-5 text-xs leading-5 text-muted">Displayed lows and trends are simulated. They are not offers or available ticket listings. Pausing and resuming change only this local demo state.</p>
  </>;
}
