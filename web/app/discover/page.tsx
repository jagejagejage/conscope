"use client";

import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";
import { useDemoData } from "@/components/demo-data-provider";
import { CategoryPill, DemoMark, EmptyState, EventArtwork, LoadingState, PageHeading } from "@/components/ui";
import { Icon } from "@/components/icons";
import { formatEventDate } from "@/lib/demo-client";
import type { DiscoveredEvent } from "@/lib/types";

export default function DiscoverPage() {
  const { client, snapshot, ready, reload } = useDemoData();
  const router = useRouter();
  const [keyword, setKeyword] = useState("");
  const [city, setCity] = useState("");
  const [date, setDate] = useState("");
  const [results, setResults] = useState<DiscoveredEvent[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [selected, setSelected] = useState<DiscoveredEvent | null>(null);
  const [quantity, setQuantity] = useState("2");
  const [target, setTarget] = useState("");
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  if (!ready || !snapshot) return <LoadingState />;

  async function search(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setError(""); setSuccess(""); setLoading(true); setSelected(null);
    try { setResults(await client.searchEvents({ keyword, city: city || undefined, date: date || undefined })); }
    catch { setError("Search is unavailable in this demo. Please try again."); }
    finally { setLoading(false); }
  }
  async function add(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setError("");
    const qty = Number(quantity); const price = Number(target);
    if (!selected) return;
    if (!Number.isInteger(qty) || qty < 1 || qty > 8) { setError("Choose a whole-number quantity from 1 to 8."); return; }
    if (!Number.isFinite(price) || price <= 0 || price > 10000) { setError("Enter a target price between $0.01 and $10,000 per ticket."); return; }
    try { const id = await client.addTrackedEvent(selected.id, { requestedQuantity: qty, targetPrice: price, currency: selected.currency }); await reload(); setSuccess(`${selected.name} was added to your browser-only watchlist.`); setSelected(null); router.push(`/events/${id}`); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "Could not add this event."); }
  }

  return <>
    <PageHeading title="Find an event" description="Search the sample catalog, then set the ticket quantity and per-ticket target you care about." action={<DemoMark>Fictional catalog</DemoMark>} />
    <form onSubmit={search} className="surface grid gap-4 rounded-2xl p-4 sm:grid-cols-2 sm:p-5 lg:grid-cols-[minmax(200px,1.4fr)_minmax(150px,.8fr)_minmax(150px,.8fr)_auto] lg:items-end">
      <label className="block text-sm font-semibold">Event or artist <span className="text-muted">(optional)</span><span className="mt-2 flex min-h-12 items-center gap-2 rounded-[11px] border border-[#cdd6e2] bg-white px-3 focus-within:outline focus-within:outline-2 focus-within:outline-[#7796ed]"><Icon name="search" size={17} className="text-muted"/><input value={keyword} onChange={(e) => setKeyword(e.target.value)} className="w-full border-0 bg-transparent text-sm font-normal outline-none" placeholder="Concert or team"/></span></label>
      <label className="block text-sm font-semibold">City <span className="text-muted">(optional)</span><input value={city} onChange={(e) => setCity(e.target.value)} className="input-field mt-2" placeholder="Boston"/></label>
      <label className="block text-sm font-semibold">Date <span className="text-muted">(optional)</span><input type="date" value={date} onChange={(e) => setDate(e.target.value)} className="input-field mt-2"/></label>
      <button className="button-primary flex items-center justify-center gap-2 px-5" type="submit" disabled={loading}>{loading ? "Searching…" : <><Icon name="search" size={17}/> Search events</>}</button>
    </form>
    <p className="mt-3 text-xs leading-5 text-muted">This search filters a small fictional catalog in your browser. It does not contact Ticketmaster or another provider.</p>
    {error && <p role="alert" className="mt-4 rounded-xl border border-red-200 bg-red-50 p-3 text-sm text-red-800">{error}</p>}
    {success && <p role="status" className="mt-4 rounded-xl border border-green-200 bg-green-50 p-3 text-sm text-green-800">{success}</p>}
    {loading && <div className="mt-8"><LoadingState label="Searching demo events"/></div>}
    {!loading && results && (results.length ? <div className="mt-8 grid gap-4 lg:grid-cols-2">{results.map((event) => {
      const isTracked = snapshot.trackedEvents.some((item) => item.event.id === event.id);
      return <article key={event.id} className="surface grid grid-cols-[84px_minmax(0,1fr)] gap-4 rounded-2xl p-4 sm:grid-cols-[112px_minmax(0,1fr)] sm:p-5">
        <EventArtwork event={event} className="h-[104px] w-[84px] sm:h-[128px] sm:w-[112px]"/>
        <div className="min-w-0"><div className="flex flex-wrap items-center gap-2"><CategoryPill category={event.category}/><DemoMark/></div><h3 className="mt-2 font-semibold leading-5">{event.name}</h3><p className="mt-1 text-xs text-muted">{formatEventDate(event.date)} · {event.time}</p><p className="mt-1 truncate text-xs text-muted">{event.venue}, {event.city}, {event.region}</p><button type="button" onClick={() => { setSelected(event); setTarget("145"); setQuantity("2"); setError(""); }} disabled={isTracked} className="button-secondary mt-3 inline-flex min-h-10 items-center gap-2 px-3 text-sm disabled:cursor-not-allowed disabled:opacity-60">{isTracked ? <><Icon name="check" size={16}/> In watchlist</> : <><Icon name="plus" size={16}/> Track this event</>}</button></div>
      </article>;
    })}</div> : <div className="mt-8"><EmptyState title="No matching demo events" description="Try a different event name or remove one of the optional filters." action={<button type="button" onClick={() => {setKeyword("");setCity("");setDate("");setResults(null);}} className="button-secondary px-4">Clear search</button>}/></div>)}
    {!results && !loading && <div className="mt-8 rounded-2xl border border-dashed border-[#cbd5e2] px-5 py-10 text-center"><span className="mx-auto grid h-11 w-11 place-items-center rounded-xl bg-[#edf2ff] text-[#4168d5]"><Icon name="spark"/></span><p className="mt-3 font-semibold">Search to get started</p><p className="mt-1 text-sm text-muted">Your selection and target are stored only in this browser.</p></div>}

    {selected && <div className="fixed inset-0 z-50 flex items-end justify-center bg-[#101c30]/45 p-0 sm:items-center sm:p-5" role="presentation" onMouseDown={(e) => { if (e.target === e.currentTarget) setSelected(null); }}><section role="dialog" aria-modal="true" aria-labelledby="track-title" className="w-full max-w-lg rounded-t-3xl bg-white p-5 shadow-2xl sm:rounded-3xl sm:p-7"><div className="flex items-start justify-between gap-4"><div><p className="text-xs font-semibold uppercase tracking-wide text-[#536da9]">Add to your watchlist</p><h2 id="track-title" className="mt-1 text-xl font-bold tracking-tight">{selected.name}</h2><p className="mt-1 text-sm text-muted">{selected.venue} · {selected.city}</p></div><button onClick={() => setSelected(null)} type="button" aria-label="Close" className="button-secondary grid h-10 w-10 shrink-0 place-items-center"><Icon name="close" size={18}/></button></div>
        <form onSubmit={add} className="mt-6 space-y-4"><label className="block text-sm font-semibold">Ticket quantity<input className="input-field mt-2" type="number" min="1" max="8" step="1" inputMode="numeric" value={quantity} onChange={(e) => setQuantity(e.target.value)} required/><span className="mt-1 block text-xs font-normal text-muted">How many tickets you hope to find together</span></label><label className="block text-sm font-semibold">Maximum target per ticket <span className="text-muted">(USD)</span><span className="mt-2 flex min-h-12 items-center rounded-[11px] border border-[#cdd6e2] bg-white px-3"><span className="mr-2 text-muted">$</span><input className="w-full bg-transparent outline-none" type="number" min="0.01" max="10000" step="0.01" inputMode="decimal" value={target} onChange={(e) => setTarget(e.target.value)} required aria-label="Maximum target price in US dollars per ticket"/></span><span className="mt-1 block text-xs font-normal text-muted">Per ticket, in US dollars. A demo preference only.</span></label><p className="rounded-xl bg-[#f2f5fa] p-3 text-xs leading-5 text-muted">No real listing is checked. Demo prices do not confirm quantity, fees, or availability.</p>{error && <p role="alert" className="text-sm text-red-700">{error}</p>}<button className="button-primary w-full" type="submit">Save demo watch</button></form>
      </section></div>}
  </>;
}
