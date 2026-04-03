export interface HRPoint {
  timestamp: string;
  bpm: number;
}

export interface SleepStage {
  stage: 'deep' | 'light' | 'rem' | 'awake';
  start: string;
  end: string;
  minutes: number;
}

export interface SleepEntry {
  date: string;
  total_minutes: number;
  deep_minutes: number;
  light_minutes: number;
  rem_minutes: number;
  awake_minutes: number;
  stages: SleepStage[];
}

export interface SpO2Point {
  timestamp: string;
  value: number;
}

export interface StressPoint {
  timestamp: string;
  level: number;
}

export interface HRVPoint {
  timestamp: string;
  rmssd: number;
  sdnn: number;
}

export interface ActivityEntry {
  date: string;
  steps: number;
  calories: number;
  distance: number;
}

export interface DeviceStatus {
  state: string;
  battery_level: number | null;
  firmware_version: string | null;
  last_sync: string | null;
  has_auth: boolean;
  device_id: string | null;
  error_message: string | null;
}
