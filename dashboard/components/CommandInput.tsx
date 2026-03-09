"use client";

import { useState } from "react";
import { sendCommand } from "../lib/api";
import type { CommandResponse } from "../lib/types";

type Entry = { text: string; response: CommandResponse };

export default function CommandInput() {
  const [text, setText] = useState("");
  const [history, setHistory] = useState<Entry[]>([]);
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!text.trim() || loading) return;
    setLoading(true);
    try {
      const res = await sendCommand(text.trim());
      setHistory((prev) => [...prev, { text: text.trim(), response: res }].slice(-5));
      setText("");
    } catch (err) {
      setHistory((prev) => [...prev, { text: text.trim(), response: { response: String(err), status: "error" } }].slice(-5));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="bg-stone-900 border border-stone-800 rounded-lg p-4">
      <h3 className="text-amber-100 font-semibold mb-3">Command</h3>
      <form onSubmit={handleSubmit} className="flex gap-2">
        <input
          type="text"
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder="Enter command..."
          className="flex-1 bg-stone-800 border border-stone-700 rounded px-3 py-2 text-amber-100 placeholder-stone-500 text-sm"
          disabled={loading}
          suppressHydrationWarning
        />
        <button
          type="submit"
          className="px-4 py-2 bg-red-500/20 text-red-400 rounded hover:bg-red-500/30 text-sm font-medium"
          disabled={loading}
          suppressHydrationWarning
        >
          Send
        </button>
      </form>
      {history.length > 0 && (
        <div className="mt-3 space-y-2 font-mono text-sm">
          {history.slice().reverse().map((h, i) => (
            <div key={i} className="border-l-2 border-stone-700 pl-2">
              <div className="text-amber-100">{h.text}</div>
              <div className="text-stone-400 text-xs">{h.response.response}</div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
