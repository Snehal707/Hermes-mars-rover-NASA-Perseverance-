"use client";

import { useEffect, useRef } from "react";
import type { RoverTelemetry, Hazard } from "../lib/types";

const W = 600;
const H = 400;
const MIN_PIXELS_PER_METER = 6;
const MAX_PIXELS_PER_METER = 500;
const MIN_WORLD_EXTENT_METERS = 0.02;

function formatMeters(value: number): string {
  const abs = Math.abs(value);
  if (abs >= 10) return value.toFixed(1);
  if (abs >= 1) return value.toFixed(2);
  if (abs >= 0.1) return value.toFixed(3);
  return value.toFixed(4);
}

export default function MapView({
  telemetry,
  hazards,
  positionHistory,
}: {
  telemetry: RoverTelemetry | null;
  hazards: Hazard[];
  positionHistory: { x: number; y: number }[];
}) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const roverX = telemetry?.position?.x ?? 0;
  const roverY = telemetry?.position?.y ?? 0;

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    // Mars brown background
    ctx.fillStyle = "#5c4033";
    ctx.fillRect(0, 0, W, H);

    const cx = W / 2;
    const cy = H / 2;

    // Auto-scale so both small and large moves are visible.
    // Keep origin fixed at center, adjust zoom by max seen extent.
    const maxExtentFromOrigin = Math.max(
      0,
      Math.abs(roverX),
      Math.abs(roverY),
      ...positionHistory.map((p) => Math.max(Math.abs(p.x), Math.abs(p.y))),
      ...hazards.map((h) => Math.max(Math.abs(h?.x ?? 0), Math.abs(h?.y ?? 0))),
    );
    const extentForScale = Math.max(MIN_WORLD_EXTENT_METERS, maxExtentFromOrigin);
    const paddingMeters = Math.max(0.02, extentForScale * 0.15);
    const targetPixels = Math.min(W, H) * 0.42; // leave margin from edges
    const pixelsPerMeter = Math.max(
      MIN_PIXELS_PER_METER,
      Math.min(MAX_PIXELS_PER_METER, targetPixels / (extentForScale + paddingMeters)),
    );

    const worldToCanvas = (x: number, y: number) => ({
      px: cx + x * pixelsPerMeter,
      py: cy - y * pixelsPerMeter,
    });

    // Origin marker (0,0)
    ctx.strokeStyle = "rgba(255, 255, 255, 0.2)";
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(cx - 10, cy);
    ctx.lineTo(cx + 10, cy);
    ctx.moveTo(cx, cy - 10);
    ctx.lineTo(cx, cy + 10);
    ctx.stroke();

    // Draw path (last 500 positions)
    if (positionHistory.length >= 2) {
      ctx.strokeStyle = "rgba(251, 191, 36, 0.5)";
      ctx.lineWidth = 1;
      ctx.beginPath();
      const first = positionHistory[0];
      const p0 = worldToCanvas(first.x, first.y);
      ctx.moveTo(p0.px, p0.py);
      for (let i = 1; i < positionHistory.length; i++) {
        const p = positionHistory[i];
        const pt = worldToCanvas(p.x, p.y);
        ctx.lineTo(pt.px, pt.py);
      }
      ctx.stroke();
    }

    // Draw hazard markers (red X)
    ctx.strokeStyle = "#ef4444";
    ctx.lineWidth = 2;
    for (const h of hazards) {
      const hx = h?.x ?? 0, hy = h?.y ?? 0;
      const { px, py } = worldToCanvas(hx, hy);
      const s = 6;
      ctx.beginPath();
      ctx.moveTo(px - s, py - s);
      ctx.lineTo(px + s, py + s);
      ctx.moveTo(px + s, py - s);
      ctx.lineTo(px - s, py + s);
      ctx.stroke();
    }

    // Rover (bright dot at current world position)
    const roverPt = worldToCanvas(roverX, roverY);
    ctx.fillStyle = "#fbbf24";
    ctx.beginPath();
    ctx.arc(roverPt.px, roverPt.py, 6, 0, Math.PI * 2);
    ctx.fill();
    ctx.strokeStyle = "#fff";
    ctx.lineWidth = 1;
    ctx.stroke();
  }, [telemetry, hazards, positionHistory, roverX, roverY]);

  return (
    <div className="bg-stone-900 border border-stone-800 rounded-lg p-4">
      <h3 className="text-amber-100 font-semibold mb-1">Map</h3>
      <div className="text-[11px] text-stone-400 mb-2 font-mono">
        Pos: {formatMeters(roverX)}, {formatMeters(roverY)} m
      </div>
      <canvas
        ref={canvasRef}
        width={W}
        height={H}
        className="w-full max-w-[600px] h-auto rounded border border-stone-700"
      />
    </div>
  );
}
