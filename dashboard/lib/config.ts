const trimTrailingSlash = (value: string) => value.replace(/\/+$/, "");

export function getApiBaseUrl(): string {
  const explicit = process.env.NEXT_PUBLIC_API_BASE_URL?.trim();
  if (explicit) return trimTrailingSlash(explicit);

  if (typeof window !== "undefined") {
    // Use the current host so dashboard works from LAN devices too.
    return `http://${window.location.hostname}:8000`;
  }

  return "http://localhost:8000";
}

export function getWsStreamUrl(): string {
  const explicit = process.env.NEXT_PUBLIC_WS_STREAM_URL?.trim();
  if (explicit) return explicit;

  const apiBase = getApiBaseUrl();
  if (apiBase.startsWith("https://")) {
    return `${apiBase.replace("https://", "wss://")}/ws/stream`;
  }
  if (apiBase.startsWith("http://")) {
    return `${apiBase.replace("http://", "ws://")}/ws/stream`;
  }
  return "ws://localhost:8000/ws/stream";
}
