import type {
  ConScopeDataSource,
  DemoSnapshot,
  DiscoveredEvent,
  EventSearchFilters,
  NotificationPreferences,
  TrackEventPreferences,
  TrackedEvent,
  UpdateTrackedEvent,
} from "@/lib/types";

const STORAGE_KEY = "conscope-web-demo-v1";

export const demoEvents: DiscoveredEvent[] = [
  {
    id: "northstar-parade-boston",
    providerId: "demo-event-np-2047",
    source: "demo-catalog",
    name: "Northstar Parade",
    category: "Concert",
    date: "2027-06-12",
    time: "7:30 PM",
    venue: "The Meridian Hall",
    city: "Boston",
    region: "MA",
    currency: "USD",
    imageTone: "blue",
    imageLabel: "NP",
    sourceUrl: null,
  },
  {
    id: "comets-outriders-new-york",
    providerId: "demo-event-co-8821",
    source: "demo-catalog",
    name: "New York Comets vs. Austin Outriders",
    category: "Sports",
    date: "2027-07-03",
    time: "1:05 PM",
    venue: "Harbor Field",
    city: "New York",
    region: "NY",
    currency: "USD",
    imageTone: "teal",
    imageLabel: "NYC",
    sourceUrl: null,
  },
  {
    id: "tessa-vale-chicago",
    providerId: "demo-event-tv-5110",
    source: "demo-catalog",
    name: "Tessa Vale: Paper Moons Tour",
    category: "Concert",
    date: "2027-08-21",
    time: "8:00 PM",
    venue: "The Lantern Room",
    city: "Chicago",
    region: "IL",
    currency: "USD",
    imageTone: "plum",
    imageLabel: "TV",
    sourceUrl: null,
  },
  {
    id: "portland-pines-seattle-sound",
    providerId: "demo-event-pp-3908",
    source: "demo-catalog",
    name: "Portland Pines vs. Seattle Sound",
    category: "Sports",
    date: "2027-09-14",
    time: "6:40 PM",
    venue: "Pine Street Grounds",
    city: "Portland",
    region: "OR",
    currency: "USD",
    imageTone: "copper",
    imageLabel: "PP",
    sourceUrl: null,
  },
  {
    id: "violet-hour-denver",
    providerId: "demo-event-vh-6273",
    source: "demo-catalog",
    name: "Violet Hour",
    category: "Concert",
    date: "2027-10-02",
    time: "7:00 PM",
    venue: "Canyon House",
    city: "Denver",
    region: "CO",
    currency: "USD",
    imageTone: "plum",
    imageLabel: "VH",
    sourceUrl: null,
  },
];

const seededAt = "2026-11-22T16:00:00-05:00";
const history = (values: number[]) =>
  values.map((perTicket, index) => ({
    observedAt: `2026-11-${String(15 + index).padStart(2, "0")}T12:00:00-05:00`,
    perTicket,
    simulationOnly: true as const,
  }));

const defaultPreferences: NotificationPreferences = {
  emailAddress: "",
  priceTargetEmailsEnabled: false,
  weeklySummaryEnabled: false,
};

export function createSeedSnapshot(): DemoSnapshot {
  const events = [demoEvents[0], demoEvents[1]];
  const trackedEvents: TrackedEvent[] = [
    {
      id: "watch-northstar-parade",
      event: events[0],
      requestedQuantity: 2,
      targetPrice: 145,
      currency: "USD",
      paused: false,
      addedAt: seededAt,
      lastCheckedAt: "2026-11-22T15:30:00-05:00",
      simulatedLow: 158,
      history: history([196, 184, 179, 168, 164, 158, 158]),
    },
    {
      id: "watch-comets",
      event: events[1],
      requestedQuantity: 3,
      targetPrice: 92,
      currency: "USD",
      paused: false,
      addedAt: seededAt,
      lastCheckedAt: "2026-11-22T15:30:00-05:00",
      simulatedLow: 86,
      history: history([110, 104, 99, 96, 92, 89, 86]),
    },
  ];

  return {
    trackedEvents,
    alerts: [
      {
        id: "demo-alert-comets",
        trackedEventId: trackedEvents[1].id,
        eventName: trackedEvents[1].event.name,
        message: "A simulated price reached your target for 3 tickets.",
        createdAt: "2026-11-22T15:30:00-05:00",
        simulationOnly: true,
      },
    ],
    notificationPreferences: defaultPreferences,
    mode: "demo",
  };
}

function readStoredSnapshot(): DemoSnapshot {
  if (typeof window === "undefined") return createSeedSnapshot();
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return createSeedSnapshot();
    const stored = JSON.parse(raw) as Partial<DemoSnapshot>;
    if (!Array.isArray(stored.trackedEvents) || !Array.isArray(stored.alerts)) {
      return createSeedSnapshot();
    }
    return {
      trackedEvents: stored.trackedEvents,
      alerts: stored.alerts,
      notificationPreferences: {
        ...defaultPreferences,
        ...(stored.notificationPreferences ?? {}),
      },
      mode: "demo",
    };
  } catch {
    return createSeedSnapshot();
  }
}

function writeSnapshot(snapshot: DemoSnapshot) {
  if (typeof window !== "undefined") {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(snapshot));
  }
}

export class DemoDataSource implements ConScopeDataSource {
  async loadSnapshot(): Promise<DemoSnapshot> {
    return readStoredSnapshot();
  }

  async searchEvents(filters: EventSearchFilters): Promise<DiscoveredEvent[]> {
    const keyword = filters.keyword.trim().toLocaleLowerCase();
    const city = filters.city?.trim().toLocaleLowerCase();
    return demoEvents.filter((event) => {
      const searchable = `${event.name} ${event.venue} ${event.city} ${event.category}`.toLocaleLowerCase();
      return (!keyword || searchable.includes(keyword))
        && (!city || event.city.toLocaleLowerCase().includes(city))
        && (!filters.date || event.date === filters.date);
    });
  }

  async addTrackedEvent(eventId: string, preferences: TrackEventPreferences): Promise<string> {
    const event = demoEvents.find((candidate) => candidate.id === eventId);
    if (!event) throw new Error("That event is not in the demonstration catalog.");
    const snapshot = readStoredSnapshot();
    if (snapshot.trackedEvents.some((tracked) => tracked.event.id === eventId)) {
      throw new Error("This event is already on your watchlist.");
    }
    const id = `watch-${eventId}-${crypto.randomUUID().slice(0, 8)}`;
    snapshot.trackedEvents = [
      {
        id,
        event,
        requestedQuantity: preferences.requestedQuantity,
        targetPrice: preferences.targetPrice,
        currency: preferences.currency,
        paused: false,
        addedAt: new Date().toISOString(),
        lastCheckedAt: null,
        simulatedLow: Math.max(18, Math.round(preferences.targetPrice * 1.12)),
        history: history([preferences.targetPrice * 1.42, preferences.targetPrice * 1.31, preferences.targetPrice * 1.19]),
      },
      ...snapshot.trackedEvents,
    ];
    writeSnapshot(snapshot);
    return id;
  }

  async updateTrackedEvent(id: string, updates: UpdateTrackedEvent): Promise<void> {
    const snapshot = readStoredSnapshot();
    snapshot.trackedEvents = snapshot.trackedEvents.map((tracked) =>
      tracked.id === id ? { ...tracked, ...updates } : tracked,
    );
    writeSnapshot(snapshot);
  }

  async removeTrackedEvent(id: string): Promise<void> {
    const snapshot = readStoredSnapshot();
    snapshot.trackedEvents = snapshot.trackedEvents.filter((tracked) => tracked.id !== id);
    snapshot.alerts = snapshot.alerts.filter((alert) => alert.trackedEventId !== id);
    writeSnapshot(snapshot);
  }

  async saveNotificationPreferences(preferences: NotificationPreferences): Promise<void> {
    const snapshot = readStoredSnapshot();
    snapshot.notificationPreferences = preferences;
    writeSnapshot(snapshot);
  }
}

export const formatCurrency = (value: number, currency: string = "USD") =>
  new Intl.NumberFormat("en-US", {
    style: "currency",
    currency,
    maximumFractionDigits: 0,
  }).format(value);

export const formatEventDate = (value: string) =>
  new Intl.DateTimeFormat("en-US", {
    weekday: "short",
    month: "short",
    day: "numeric",
    year: "numeric",
    timeZone: "UTC",
  }).format(new Date(`${value}T12:00:00Z`));

export const formatCheckedAt = (value: string | null) => {
  if (!value) return "Not checked yet";
  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  }).format(new Date(value));
};
