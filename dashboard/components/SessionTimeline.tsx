"use client";

import { useEffect, useState } from "react";
import { getSessions, getSession } from "../lib/api";
import type { Session } from "../lib/types";

export default function SessionTimeline() {
  const [sessions, setSessions] = useState<Session[]>([]);
  const [expanded, setExpanded] = useState<string | null>(null);
  const [detail, setDetail] = useState<Session | null>(null);

  useEffect(() => {
    let cancelled = false;

    const refreshSessions = async () => {
      try {
        const r = await getSessions();
        if (!cancelled) setSessions(r.sessions);
      } catch {
        // Keep previous UI state on transient API errors.
      }
    };

    refreshSessions();
    const timer = window.setInterval(refreshSessions, 4000);

    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, []);

  useEffect(() => {
    if (!expanded) return;

    let cancelled = false;

    const refreshDetail = async () => {
      try {
        const s = await getSession(expanded);
        if (!cancelled) setDetail(s);
      } catch {
        if (!cancelled) setDetail(null);
      }
    };

    refreshDetail();
    const timer = window.setInterval(refreshDetail, 4000);

    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [expanded]);

  async function toggle(id: string) {
    if (expanded === id) {
      setExpanded(null);
      setDetail(null);
      return;
    }
    try {
      const s = await getSession(id);
      setDetail(s);
      setExpanded(id);
    } catch {
      setExpanded(null);
      setDetail(null);
    }
  }

  const renderedSessions: Session[] = [];
  const seenSessionIds = new Set<string>();
  for (const session of sessions) {
    const sid = String(session.session_id || "").trim();
    if (sid) {
      if (seenSessionIds.has(sid)) continue;
      seenSessionIds.add(sid);
    }
    renderedSessions.push(session);
  }

  return (
    <div className="bg-stone-900 border border-stone-800 rounded-lg p-4">
      <h3 className="text-amber-100 font-semibold mb-3">Session Timeline</h3>
      <div className="space-y-2 font-mono text-sm max-h-64 overflow-y-auto">
        {renderedSessions.length === 0 && <div className="text-stone-400">No sessions yet</div>}
        {renderedSessions.map((s, i) => (
          <div
            key={`${s.session_id ?? "session"}-${s.start_time ?? "unknown"}-${i}`}
            className="border border-stone-800 rounded p-2 cursor-pointer hover:bg-stone-800/50"
            onClick={() => s.session_id && toggle(s.session_id)}
          >
            <div className="flex justify-between text-amber-100">
              <span className="truncate">{(s.session_id ?? "unknown").slice(0, 8)}...</span>
              <span className="text-stone-400 text-xs">{s.start_time?.slice(0, 19)}</span>
            </div>
            <div className="text-stone-400 text-xs mt-1">
              dist: {(s.distance_traveled ?? 0).toFixed(1)}m, hazards: {s.hazards_encountered ?? 0}
            </div>
            {s.session_id && expanded === s.session_id && detail && (
              <div className="mt-2 pt-2 border-t border-stone-700 text-stone-400 text-xs">
                <div>End: {detail.end_time ?? "—"}</div>
                <div>Skills: {detail.skills_used || "—"}</div>
                <div>Summary: {detail.summary || "—"}</div>
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
