"use client";

import type { RoverTelemetry } from "../lib/types";

function tiltColor(rad: number): string {
  const abs = Math.abs(rad);
  if (abs >= 0.52) return "text-red-500";
  if (abs >= 0.35) return "text-amber-500";
  return "text-emerald-500";
}

export default function SensorPanel({ telemetry }: { telemetry: RoverTelemetry | null }) {
  const orient = telemetry?.orientation ?? { roll: 0, pitch: 0, yaw: 0 };
  const roll = orient?.roll ?? 0, pitch = orient?.pitch ?? 0, yaw = orient?.yaw ?? 0;
  const hazard = telemetry?.hazard_detected ?? false;

  return (
    <div className="bg-stone-900 border border-stone-800 rounded-lg p-4">
      <h3 className="text-amber-100 font-semibold mb-3">Sensors</h3>
      <div className="space-y-2 font-mono text-sm">
        <div className="flex justify-between">
          <span className="text-stone-400">Roll</span>
          <span className={tiltColor(roll)}>{(roll * (180 / Math.PI)).toFixed(2)} deg</span>
        </div>
        <div className="flex justify-between">
          <span className="text-stone-400">Pitch</span>
          <span className={tiltColor(pitch)}>{(pitch * (180 / Math.PI)).toFixed(2)} deg</span>
        </div>
        <div className="flex justify-between">
          <span className="text-stone-400">Yaw</span>
          <span>{(yaw * (180 / Math.PI)).toFixed(2)} deg</span>
        </div>
        <div className="flex justify-between">
          <span className="text-stone-400">Nearest obstacle</span>
          <span className="text-stone-400">—</span>
        </div>
        <div className="flex items-center gap-2 mt-2">
          <span className={`px-2 py-0.5 rounded text-xs ${hazard ? "bg-red-500/20 text-red-500" : "bg-emerald-500/20 text-emerald-500"}`}>
            {hazard ? "Hazard" : "Safe"}
          </span>
        </div>
      </div>
    </div>
  );
}
