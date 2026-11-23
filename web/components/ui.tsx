import Link from "next/link";
import type { ReactNode } from "react";
import { Icon } from "@/components/icons";
import { formatCurrency, formatEventDate } from "@/lib/demo-client";
import type { DiscoveredEvent, TrackedEvent } from "@/lib/types";

export function EventArtwork({ event, className = "" }: { event: DiscoveredEvent; className?: string }) {
  return (
    <div aria-label={`Fictional demonstration artwork for ${event.name}`} role="img" className={`event-art event-art-${event.imageTone} rounded-[15px] ${className}`}>
      <span className="event-art-label text-[24px] sm:text-[28px]">{event.imageLabel}</span>
    </div>
  );
}

export function CategoryPill({ category }: { category: DiscoveredEvent["category"] }) {
  return <span className="pill pill-blue">{category}</span>;
}

export function EventMeta({ event }: { event: DiscoveredEvent }) {
  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-[13px] text-muted">
      <span className="inline-flex items-center gap-1.5"><Icon name="calendar" size={15}/>{formatEventDate(event.date)}</span>
      <span className="inline-flex items-center gap-1.5"><Icon name="pin" size={15}/>{event.venue}, {event.city}</span>
    </div>
  );
}

export function DemoMark({ children = "Simulated" }: { children?: ReactNode }) {
  return <span className="pill pill-amber">{children}</span>;
}

export function PageHeading({ title, description, action }: { title: string; description?: string; action?: ReactNode }) {
  return (
    <div className="mb-7 flex flex-col justify-between gap-4 sm:mb-9 sm:flex-row sm:items-end">
      <div>
        <h2 className="page-title">{title}</h2>
        {description && <p className="mt-2 max-w-2xl text-[14px] leading-6 text-muted">{description}</p>}
      </div>
      {action}
    </div>
  );
}

export function SectionHeading({ title, action }: { title: string; action?: ReactNode }) {
  return <div className="mb-4 flex items-center justify-between gap-3"><h3 className="section-title">{title}</h3>{action}</div>;
}

export function LoadingState({ label = "Loading your demo" }: { label?: string }) {
  return (
    <div role="status" aria-live="polite" aria-label={label} className="space-y-4">
      <div className="skeleton h-10 w-56 rounded-lg" />
      <div className="skeleton h-5 w-80 max-w-full rounded-md" />
      <div className="grid gap-4 pt-3 md:grid-cols-2"><div className="skeleton h-56 rounded-2xl"/><div className="skeleton h-56 rounded-2xl"/></div>
      <span className="sr-only">{label}</span>
    </div>
  );
}

export function EmptyState({ title, description, action }: { title: string; description: string; action: ReactNode }) {
  return (
    <div className="surface rounded-2xl px-6 py-12 text-center sm:px-10">
      <div className="mx-auto mb-4 grid h-12 w-12 place-items-center rounded-2xl bg-[#eaf0ff] text-[#4168d5]"><Icon name="ticket" size={23}/></div>
      <h3 className="text-lg font-semibold tracking-[-.02em]">{title}</h3>
      <p className="mx-auto mt-2 max-w-md text-sm leading-6 text-muted">{description}</p>
      <div className="mt-5">{action}</div>
    </div>
  );
}

export function TrackedEventRow({ tracked, compact = false }: { tracked: TrackedEvent; compact?: boolean }) {
  return (
    <Link href={`/events/${tracked.id}`} className="group flex min-w-0 items-center gap-3 rounded-xl p-2.5 transition-colors hover:bg-[#f5f7fb] focus-visible:outline-offset-1 sm:gap-4">
      <EventArtwork event={tracked.event} className={`h-[58px] w-[58px] shrink-0 sm:h-[68px] sm:w-[68px] ${compact ? "!rounded-xl" : ""}`}/>
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-2">
          <h4 className="truncate text-[14px] font-semibold text-[#20314a] group-hover:text-[#3458bb]">{tracked.event.name}</h4>
          {tracked.paused && <span className="pill border border-[#dce2ea] bg-white text-[#728096]">Paused</span>}
        </div>
        <p className="mt-1 truncate text-[12px] text-muted">{formatEventDate(tracked.event.date)} · {tracked.event.city}</p>
      </div>
      <div className="hidden shrink-0 text-right sm:block">
        <p className="text-[11px] text-muted">Your target</p>
        <p className="font-semibold tabular-nums">{formatCurrency(tracked.targetPrice, tracked.currency)}</p>
      </div>
      <Icon name="arrow" size={17} className="shrink-0 text-[#9aa6b5] transition-transform group-hover:translate-x-0.5 group-hover:text-[#4366cc]"/>
    </Link>
  );
}

export function PriceChart({ tracked, height = 210 }: { tracked: TrackedEvent; height?: number }) {
  const values = tracked.history.map((point) => point.perTicket);
  const low = Math.min(...values, tracked.targetPrice) * 0.88;
  const high = Math.max(...values, tracked.targetPrice) * 1.08;
  const range = high - low || 1;
  const width = 720;
  const top = 18;
  const bottom = height - 28;
  const xAt = (index: number) => 10 + (index / Math.max(1, values.length - 1)) * (width - 20);
  const yAt = (value: number) => bottom - ((value - low) / range) * (bottom - top);
  const linePath = values.map((value, index) => `${index === 0 ? "M" : "L"}${xAt(index)} ${yAt(value)}`).join(" ");
  const areaPath = `${linePath} L${xAt(values.length - 1)} ${bottom} L${xAt(0)} ${bottom} Z`;
  const targetY = yAt(tracked.targetPrice);
  const lastX = xAt(values.length - 1);
  const lastY = yAt(values[values.length - 1]);

  return (
    <figure aria-labelledby={`chart-title-${tracked.id}`} className="min-w-0">
      <figcaption id={`chart-title-${tracked.id}`} className="sr-only">Simulated price history for {tracked.event.name}. The dashed line marks your target of {formatCurrency(tracked.targetPrice, tracked.currency)} per ticket.</figcaption>
      <div className="relative">
        <div aria-hidden="true" className="pointer-events-none absolute right-0 top-0 flex items-center gap-2 text-[11px] text-muted"><span className="h-px w-5 border-t border-dashed border-[#7588b8]"/>Target {formatCurrency(tracked.targetPrice, tracked.currency)}</div>
        <svg className="mt-5 block w-full overflow-visible" style={{ height }} viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none" role="img">
          <title>Simulated price trend for {tracked.event.name}</title>
          {[0, 1, 2].map((line) => {
            const y = top + (line / 2) * (bottom - top);
            return <line key={line} x1="0" x2={width} y1={y} y2={y} stroke="#e9edf3" strokeWidth="1"/>;
          })}
          <path d={areaPath} fill="url(#chart-fill)" opacity=".75"/>
          <line x1="0" x2={width} y1={targetY} y2={targetY} stroke="#7588b8" strokeDasharray="5 6" strokeWidth="1.5"/>
          <path d={linePath} fill="none" stroke="#4168d5" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" vectorEffect="non-scaling-stroke"/>
          <circle cx={lastX} cy={lastY} r="5" fill="white" stroke="#4168d5" strokeWidth="3" vectorEffect="non-scaling-stroke"/>
          <defs><linearGradient id="chart-fill" x1="0" x2="0" y1="0" y2="1"><stop offset="0" stopColor="#7996e9" stopOpacity=".21"/><stop offset="1" stopColor="#7996e9" stopOpacity=".015"/></linearGradient></defs>
        </svg>
      </div>
      <div className="mt-2 flex justify-between text-[11px] text-muted"><span>Nov 15</span><span>Nov 18</span><span>Nov 21</span></div>
      <p className="mt-3 text-xs leading-5 text-muted">Example trend only. This is not a live listing or verified offer.</p>
    </figure>
  );
}
