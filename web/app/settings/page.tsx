"use client";

import { useState, type FormEvent } from "react";
import { useDemoData } from "@/components/demo-data-provider";
import { DemoMark, LoadingState, PageHeading } from "@/components/ui";
import { Icon } from "@/components/icons";
import type { NotificationPreferences } from "@/lib/types";

export default function SettingsPage() {
  const { client, snapshot, ready, reload } = useDemoData();
  if (!ready || !snapshot) return <LoadingState />;

  return <SettingsForm preferences={snapshot.notificationPreferences} savePreferences={async (preferences) => { await client.saveNotificationPreferences(preferences); await reload(); }} />;
}

function SettingsForm({ preferences, savePreferences }: { preferences: NotificationPreferences; savePreferences: (preferences: NotificationPreferences) => Promise<void> }) {
  const [email, setEmail] = useState(preferences.emailAddress);
  const [priceEmails, setPriceEmails] = useState(preferences.priceTargetEmailsEnabled);
  const [weekly, setWeekly] = useState(preferences.weeklySummaryEnabled);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState("");

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setSaved(false); setError("");
    if ((priceEmails || weekly) && email && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) { setError("Enter a valid email address or leave it blank."); return; }
    await savePreferences({ emailAddress: email, priceTargetEmailsEnabled: priceEmails, weeklySummaryEnabled: weekly }); setSaved(true);
  }

  return <>
    <PageHeading title="Settings" description="Explore how preferences could work. Every setting below stays in local browser storage." action={<DemoMark>Demo settings</DemoMark>} />
    <div className="grid gap-6 xl:grid-cols-[minmax(0,1.2fr)_minmax(300px,.8fr)]">
      <form onSubmit={save} className="surface rounded-2xl p-5 sm:p-7">
        <div className="flex items-start gap-3"><span className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-[#eef3ff] text-[#4566c1]"><Icon name="mail" size={19}/></span><div><h2 className="section-title">Email preferences</h2><p className="mt-1 text-sm leading-5 text-muted">These controls demonstrate the planned settings only.</p></div></div>
        <label className="mt-6 block text-sm font-semibold">Email address <span className="font-normal text-muted">(optional)</span><input type="email" autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} className="input-field mt-2" placeholder="you@example.com"/></label>
        <div className="mt-5 space-y-3">
          <label className="flex min-h-[60px] cursor-pointer items-center justify-between gap-4 rounded-xl border border-[#e5eaf0] p-4"><span><span className="block text-sm font-semibold">Price target emails</span><span className="mt-1 block text-xs text-muted">Example preference for a future alert</span></span><input className="h-5 w-5 accent-[#4168d5]" type="checkbox" checked={priceEmails} onChange={(e) => setPriceEmails(e.target.checked)} aria-label="Enable price target emails in demo settings"/></label>
          <label className="flex min-h-[60px] cursor-pointer items-center justify-between gap-4 rounded-xl border border-[#e5eaf0] p-4"><span><span className="block text-sm font-semibold">Weekly summary</span><span className="mt-1 block text-xs text-muted">Example preference for a future digest</span></span><input className="h-5 w-5 accent-[#4168d5]" type="checkbox" checked={weekly} onChange={(e) => setWeekly(e.target.checked)} aria-label="Enable weekly summary in demo settings"/></label>
        </div>
        {error && <p role="alert" className="mt-4 text-sm text-red-700">{error}</p>}{saved && <p role="status" className="mt-4 text-sm text-[#246b58]">Saved in this browser. No email was sent.</p>}
        <button className="button-primary mt-5 inline-flex items-center gap-2 px-5" type="submit"><Icon name="check" size={17}/> Save demo preferences</button>
      </form>
      <aside className="space-y-4"><div className="rounded-2xl border border-[#e9d8ae] bg-[#fff9ed] p-5 sm:p-6"><div className="flex items-center gap-2 font-semibold text-[#72551e]"><Icon name="info" size={18}/> Email is not connected</div><p className="mt-2 text-sm leading-6 text-[#755f36]">Saving these checkboxes cannot send mail. No notification service or customer delivery is active in this frontend.</p></div><div className="surface rounded-2xl p-5 sm:p-6"><h2 className="font-semibold">Monitoring information</h2><dl className="mt-4 space-y-4 text-sm"><div><dt className="text-muted">Data mode</dt><dd className="mt-1 font-semibold">Fictional demonstration</dd></div><div><dt className="text-muted">Price checks</dt><dd className="mt-1 font-semibold">Not active</dd></div><div><dt className="text-muted">Storage</dt><dd className="mt-1 font-semibold">This browser only</dd></div><div><dt className="text-muted">Shared across devices</dt><dd className="mt-1 font-semibold">No</dd></div></dl><p className="mt-5 border-t border-[#edf0f4] pt-4 text-xs leading-5 text-muted">Clearing this browser’s site data removes demo changes. No account or backend sync is configured.</p></div></aside>
    </div>
  </>;
}
