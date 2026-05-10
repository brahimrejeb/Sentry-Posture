export const API_BASE = (import.meta.env.VITE_API_BASE as string | undefined) ?? '/api';

export type TrackerState = 'idle' | 'searching' | 'locked' | 'paused';
export type Mode = 'simple' | 'advanced';

export interface DeviceInfo {
  id: string;
  name: string;
}

export interface Status {
  monitoring: boolean;
  state: TrackerState;
  calibrated: boolean;
  is_slouching: boolean;
  person_detected: boolean;
  people_in_frame: number;
  settling: boolean;
  welcome_back: boolean;
  current_cva: number | null;
  baseline_cva: number | null;
  deviation: number | null;
  last_alert_at: number | null;
  sensitivity_threshold: number;
  slouch_time_threshold: number;
  alert_cooldown: number;
  current_model: string;
  available_models: string[];
  locked_streak_seconds: number;
  stand_up_after_seconds: number;
  daily_slouch_goal_pct: number;
  daily_break_goal: number;
  mode: Mode;
}

export interface AutostartInfo {
  enabled: boolean;
  supported: boolean;
  command: string | null;
  target: string | null;
  platform: string;
}

export interface HourBucket {
  hour: number;
  locked_seconds: number;
  slouch_seconds: number;
  breaks: number;
}

export interface DayTotals {
  locked_seconds: number;
  slouch_seconds: number;
  breaks: number;
  alerts: number;
  longest_uninterrupted_seconds: number;
  slouch_pct: number;
}

export interface DayHistory {
  date: string;
  buckets: HourBucket[];
  totals: DayTotals;
}

export interface DaySummary {
  date: string;
  locked_seconds: number;
  slouch_seconds: number;
  breaks: number;
  alerts: number;
  slouch_pct: number;
}

export interface RangeHistory {
  days: DaySummary[];
}

export interface Streaks {
  good_posture_days: number;
  break_goal_days: number;
}

async function jsonFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...init,
  });
  if (!res.ok) {
    const text = await res.text().catch(() => '');
    throw new Error(`${res.status} ${res.statusText}: ${text}`);
  }
  return (await res.json()) as T;
}

type ConfigPatch = {
  model_level?: string;
  sensitivity_threshold?: number;
  slouch_time_threshold?: number;
  alert_cooldown?: number;
  stand_up_after_minutes?: number;
  daily_slouch_goal_pct?: number;
  daily_break_goal?: number;
  mode?: Mode;
};

export const api = {
  status: () => jsonFetch<Status>('/status'),
  devices: () => jsonFetch<{ devices: DeviceInfo[] }>('/devices'),
  start: (source: string) =>
    jsonFetch<{ status: string; message?: string }>('/start', {
      method: 'POST',
      body: JSON.stringify({ source }),
    }),
  stop: () => jsonFetch<{ status: string }>('/stop', { method: 'POST' }),
  calibrate: () =>
    jsonFetch<{ status: string; message?: string }>('/calibrate', { method: 'POST' }),
  config: (body: ConfigPatch) =>
    jsonFetch<Status>('/config', { method: 'POST', body: JSON.stringify(body) }),
  feedUrl: (debug: boolean) => `${API_BASE}/feed?debug=${debug ? 'true' : 'false'}`,
  historyToday: () => jsonFetch<DayHistory>('/history/today'),
  historyWeek: () => jsonFetch<RangeHistory>('/history/week'),
  historyMonth: () => jsonFetch<RangeHistory>('/history/month'),
  historyYear: () => jsonFetch<RangeHistory>('/history/year'),
  streaks: () => jsonFetch<Streaks>('/history/streaks'),
  clearHistory: () =>
    jsonFetch<{ status: string }>('/history/clear', { method: 'POST' }),
  autostart: () => jsonFetch<AutostartInfo>('/autostart'),
  setAutostart: (enabled: boolean) =>
    jsonFetch<AutostartInfo>('/autostart', {
      method: 'POST',
      body: JSON.stringify({ enabled }),
    }),
};
