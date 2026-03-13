"use client";

import type { RoverTelemetry } from "../lib/types";

function formatCoord(value: number): string {
  const abs = Math.abs(value);
  if (abs >= 10) return value.toFixed(1);
  if (abs >= 1) return value.toFixed(2);
  if (abs >= 0.1) return value.toFixed(3);
  return value.toFixed(4);
}

export default function RoverStatus(props: { telemetry: RoverTelemetry | null; wsConnected: boolean }) {
  const t = props.telemetry;
  const pos = t?.position ?? { x: 0, y: 0, z: 0 };
  const vel = t?.velocity ?? { linear: 0, angular: 0 };
  const x = pos?.x ?? 0, y = pos?.y ?? 0, z = pos?.z ?? 0;
  const linear = vel?.linear ?? 0;
  const yaw = t?.orientation?.yaw ?? 0;
  const headingDeg = ((yaw * 180) / Math.PI).toFixed(1);
  const uptime = t?.uptime_seconds ?? 0;
  const simConnected = t?.sim_connected ?? false;
  const wsConnected = props.wsConnected;

  return (
    <div className="bg-stone-900 border border-stone-800 rounded-lg p-4">
      <h3 className="text-amber-100 font-semibold mb-3">Rover Status</h3>
      <div className="space-y-2 font-mono text-sm">
        <div className="flex justify-between">
          <span className="text-stone-400">Position</span>
          <span>{formatCoord(x)}, {formatCoord(y)}, {formatCoord(z)}</span>
        </div>
        <div className="flex justify-between">
          <span className="text-stone-400">Speed</span>
          <span>{linear.toFixed(3)} m/s</span>
        </div>
        <div className="flex justify-between">
          <span className="text-stone-400">Heading</span>
          <span>{headingDeg} deg</span>
        </div>
        <div className="flex justify-between">
          <span className="text-stone-400">Uptime</span>
          <span>{uptime.toFixed(0)}s</span>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-stone-400">Stream</span>
          <span
            className={
              "w-2 h-2 rounded-full " +
              (wsConnected ? "bg-emerald-500" : "bg-red-500")
            }
          />
          <span className={wsConnected ? "text-emerald-500" : "text-red-500"}>
            {wsConnected ? "Connected" : "Disconnected"}
          </span>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-stone-400">Simulation</span>
          <span
            className={
              "w-2 h-2 rounded-full " +
              (simConnected ? "bg-emerald-500" : "bg-red-500")
            }
          />
          <span className={simConnected ? "text-emerald-500" : "text-red-500"}>
            {simConnected ? "Connected" : "Disconnected"}
          </span>
        </div>
      </div>
    </div>
  );
}
