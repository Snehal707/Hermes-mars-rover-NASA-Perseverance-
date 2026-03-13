import type { RoverTelemetry } from "./types";

export class WebSocketManager {
  private ws: WebSocket | null = null;
  private url = "";
  private onMessageCallback: ((data: RoverTelemetry) => void) | null = null;
  private onStateCallback: ((connected: boolean) => void) | null = null;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private shouldReconnect = false;

  connect(url: string) {
    this.shouldReconnect = true;
    this.url = url;
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    if (this.ws) {
      this.ws.close();
    }
    this.ws = new WebSocket(url);
    this.ws.onopen = () => {
      this.onStateCallback?.(true);
    };
    this.ws.onmessage = (e) => {
      try {
        const data = JSON.parse(e.data) as RoverTelemetry;
        this.onMessageCallback?.(data);
      } catch {
        // ignore parse errors
      }
    };
    this.ws.onclose = () => {
      this.ws = null;
      this.onStateCallback?.(false);
      if (this.shouldReconnect) {
        this.reconnectTimer = setTimeout(() => this.connect(this.url), 2000);
      }
    };
    this.ws.onerror = () => {
      this.onStateCallback?.(false);
      // onclose will handle reconnect
    };
  }

  onMessage(callback: (data: RoverTelemetry) => void) {
    this.onMessageCallback = callback;
  }

  onState(callback: (connected: boolean) => void) {
    this.onStateCallback = callback;
  }

  disconnect() {
    this.shouldReconnect = false;
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    if (this.ws) {
      this.ws.close();
      this.ws = null;
    }
  }
}
