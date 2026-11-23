export type CurrencyCode = "USD";

export interface DiscoveredEvent {
  id: string;
  providerId: string;
  source: "demo-catalog";
  name: string;
  category: "Concert" | "Sports";
  date: string;
  time: string;
  venue: string;
  city: string;
  region: string;
  currency: CurrencyCode;
  imageTone: "blue" | "plum" | "copper" | "teal";
  imageLabel: string;
  sourceUrl: string | null;
}

export interface PricePoint {
  observedAt: string;
  perTicket: number;
  /** Demo history is always simulated and must not be treated as a listing. */
  simulationOnly: true;
}

export interface TrackedEvent {
  id: string;
  event: DiscoveredEvent;
  requestedQuantity: number;
  targetPrice: number;
  currency: CurrencyCode;
  paused: boolean;
  addedAt: string;
  lastCheckedAt: string | null;
  simulatedLow: number;
  history: PricePoint[];
}

export interface DemoAlert {
  id: string;
  trackedEventId: string;
  eventName: string;
  message: string;
  createdAt: string;
  simulationOnly: true;
}

export interface NotificationPreferences {
  emailAddress: string;
  priceTargetEmailsEnabled: boolean;
  weeklySummaryEnabled: boolean;
}

export interface DemoSnapshot {
  trackedEvents: TrackedEvent[];
  alerts: DemoAlert[];
  notificationPreferences: NotificationPreferences;
  mode: "demo";
}

export interface EventSearchFilters {
  keyword: string;
  city?: string;
  date?: string;
}

export interface TrackEventPreferences {
  requestedQuantity: number;
  targetPrice: number;
  currency: CurrencyCode;
}

export interface UpdateTrackedEvent {
  requestedQuantity?: number;
  targetPrice?: number;
  paused?: boolean;
}

/**
 * UI-facing data boundary. A future authenticated backend can implement this
 * contract without coupling pages to localStorage or a persistence engine.
 */
export interface ConScopeDataSource {
  loadSnapshot(): Promise<DemoSnapshot>;
  searchEvents(filters: EventSearchFilters): Promise<DiscoveredEvent[]>;
  addTrackedEvent(eventId: string, preferences: TrackEventPreferences): Promise<string>;
  updateTrackedEvent(id: string, updates: UpdateTrackedEvent): Promise<void>;
  removeTrackedEvent(id: string): Promise<void>;
  saveNotificationPreferences(preferences: NotificationPreferences): Promise<void>;
}
