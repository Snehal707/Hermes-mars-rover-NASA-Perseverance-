import type { RoverTelemetry, Session, Hazard, Skill, CommandResponse } from "./types";
import { getApiBaseUrl } from "./config";

const API_BASE = getApiBaseUrl();

function headers(): HeadersInit {
  const h: Record<string, string> = { "Content-Type": "application/json" };
  const apiKey = process.env.NEXT_PUBLIC_ROVER_API_KEY;
  if (apiKey) h["X-API-Key"] = apiKey;
  return h;
}

export async function getStatus(): Promise<RoverTelemetry> {
  const res = await fetch(`${API_BASE}/status`, { headers: headers() });
  if (!res.ok) throw new Error("Failed to fetch status");
  return res.json();
}

export async function sendCommand(text: string, user_id?: string): Promise<CommandResponse> {
  const res = await fetch(`${API_BASE}/command`, {
    method: "POST",
    headers: headers(),
    body: JSON.stringify({ text, user_id }),
  });
  if (!res.ok) throw new Error("Failed to send command");
  return res.json();
}

export async function getSessions(): Promise<{ sessions: Session[] }> {
  const res = await fetch(`${API_BASE}/sessions`, { headers: headers() });
  if (!res.ok) throw new Error("Failed to fetch sessions");
  return res.json();
}

export async function getSession(id: string): Promise<Session> {
  const res = await fetch(`${API_BASE}/sessions/${id}`, { headers: headers() });
  if (!res.ok) throw new Error("Failed to fetch session");
  return res.json();
}

export async function getHazards(): Promise<{ hazards: Hazard[] }> {
  const res = await fetch(`${API_BASE}/hazards`, { headers: headers() });
  if (!res.ok) throw new Error("Failed to fetch hazards");
  return res.json();
}

export async function getSkills(): Promise<{ skills: Skill[] }> {
  const res = await fetch(`${API_BASE}/skills`, { headers: headers() });
  if (!res.ok) throw new Error("Failed to fetch skills");
  return res.json();
}
