"use client";

import { useEffect, useRef, useState } from "react";
import { WebSocketManager } from "../lib/websocket";
import { getHazards } from "../lib/api";
import { getWsStreamUrl } from "../lib/config";
import type { RoverTelemetry, Hazard } from "../lib/types";
import MapView from "../components/MapView";
import RoverStatus from "../components/RoverStatus";
import SensorPanel from "../components/SensorPanel";
import CommandInput from "../components/CommandInput";
import SessionTimeline from "../components/SessionTimeline";
import HazardAlert from "../components/HazardAlert";

export default function Dashboard() {
  const [telemetry, setTelemetry] = useState<RoverTelemetry | null>(null);
  const [wsConnected, setWsConnected] = useState(false);
  const [hazards, setHazards] = useState<Hazard[]>([]);
  const [positionHistory, setPositionHistory] = useState<{ x: number; y: number }[]>([]);
  const [hazardDismissed, setHazardDismissed] = useState(false);
  const wsRef = useRef<WebSocketManager | null>(null);

  useEffect(() => {
    const ws = new WebSocketManager();
    wsRef.current = ws;
    ws.onState((connected) => setWsConnected(connected));
    ws.onMessage((data) => {
      setTelemetry(data);
      if (data.position) {
        const px = data.position?.x ?? 0;
        const py = data.position?.y ?? 0;
        setPositionHistory((prev) => {
          const last = prev[prev.length - 1];
          const same =
            last !== undefined &&
            Math.abs(last.x - px) < 1e-4 &&
            Math.abs(last.y - py) < 1e-4;
          if (same) return prev;
          const next = [...prev, { x: px, y: py }];
          return next.slice(-500);
        });
      }
    });
    ws.connect(getWsStreamUrl());

    getHazards()
      .then((r) => setHazards(r.hazards))
      .catch(() => {});

    return () => {
      ws.disconnect();
      wsRef.current = null;
    };
  }, []);

  const showHazardAlert = !!telemetry?.hazard_detected && !hazardDismissed;

  return (
    <div className="min-h-screen bg-stone-950 text-amber-100 p-4">
      <header className="text-center mb-6">
        <h1 className="text-3xl font-bold tracking-wider text-red-400">
          HERMES MARS ROVER — MISSION CONTROL
        </h1>
        <p className="text-sm text-stone-400 mt-1">Live Simulation Dashboard</p>
        <p className="text-xs text-stone-500 mt-0.5">
          Map is fixed at mission origin (0,0); rover marker moves as telemetry updates. Run Gazebo + bridge for live movement.
        </p>
      </header>

      {showHazardAlert && (
        <HazardAlert onDismiss={() => setHazardDismissed(true)} />
      )}

      <div className="grid grid-cols-12 gap-4">
        <div className="col-span-8 space-y-4">
          <MapView
            telemetry={telemetry}
            hazards={hazards}
            positionHistory={positionHistory}
          />
          <SessionTimeline />
        </div>
        <div className="col-span-4 space-y-4">
          <RoverStatus telemetry={telemetry} wsConnected={wsConnected} />
          <SensorPanel telemetry={telemetry} />
          <CommandInput />
        </div>
      </div>
    </div>
  );
}
