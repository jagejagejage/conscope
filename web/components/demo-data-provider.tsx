"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { DemoDataSource } from "@/lib/demo-client";
import type { ConScopeDataSource, DemoSnapshot } from "@/lib/types";

interface DemoDataContextValue {
  client: ConScopeDataSource;
  snapshot: DemoSnapshot | null;
  ready: boolean;
  reload: () => Promise<void>;
}

const DemoDataContext = createContext<DemoDataContextValue | null>(null);
const demoClient = new DemoDataSource();

export function DemoDataProvider({ children }: { children: ReactNode }) {
  const [snapshot, setSnapshot] = useState<DemoSnapshot | null>(null);
  const [ready, setReady] = useState(false);

  const reload = useCallback(async () => {
    const next = await demoClient.loadSnapshot();
    setSnapshot(next);
    setReady(true);
  }, []);

  useEffect(() => {
    let active = true;
    demoClient.loadSnapshot().then((next) => {
      if (active) {
        setSnapshot(next);
        setReady(true);
      }
    });
    return () => { active = false; };
  }, []);

  const value = useMemo(() => ({ client: demoClient, snapshot, ready, reload }), [snapshot, ready, reload]);

  return <DemoDataContext.Provider value={value}>{children}</DemoDataContext.Provider>;
}

export function useDemoData() {
  const context = useContext(DemoDataContext);
  if (!context) throw new Error("useDemoData must be used within DemoDataProvider");
  return context;
}
