export interface RoverTelemetry {
  position: { x: number; y: number; z: number };
  orientation: { roll: number; pitch: number; yaw: number };
  velocity: { linear: number; angular: number };
  hazard_detected: boolean;
  uptime_seconds: number;
  sim_connected: boolean;
}

export interface Session {
  id?: number;
  session_id: string;
  start_time: string;
  end_time?: string;
  distance_traveled?: number;
  photos_taken?: number;
  hazards_encountered?: number;
  skills_used?: string;
  summary?: string;
}

export interface Hazard {
  id?: number;
  x: number;
  y: number;
  hazard_type: string;
  severity: string;
  description?: string;
  discovered_at?: string;
  session_id?: string;
}

export interface Skill {
  name: string;
  description: string;
  path: string;
}

export interface CommandResponse {
  response: string;
  status: string;
}
