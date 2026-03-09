"use client";

export default function HazardAlert({ onDismiss }: { onDismiss: () => void }) {
  return (
    <div className="fixed top-0 left-0 right-0 z-50 bg-red-500/90 text-white px-4 py-3 flex items-center justify-between">
      <div>
        <span className="font-semibold">Hazard detected</span>
        <span className="ml-2 text-sm opacity-90">
          Stop immediately. Check tilt and terrain. Follow safety protocol.
        </span>
      </div>
      <button onClick={onDismiss} className="px-3 py-1 bg-white/20 rounded hover:bg-white/30 text-sm">
        Dismiss
      </button>
    </div>
  );
}
