export function fmtDuration(seconds: number): string {
  if (!seconds || seconds < 1) return '0s';
  if (seconds < 60) return `${Math.round(seconds)}s`;
  const m = Math.floor(seconds / 60);
  const s = Math.round(seconds % 60);
  if (m < 60) return s > 0 ? `${m}m ${s}s` : `${m}m`;
  const h = Math.floor(m / 60);
  const mm = m % 60;
  return mm > 0 ? `${h}h ${mm}m` : `${h}h`;
}

export function fmtPct(value: number): string {
  return `${(value * 100).toFixed(1)}%`;
}

export function fmtRelative(seconds: number | null): string {
  if (seconds == null) return '—';
  const delta = Math.max(0, Math.floor(Date.now() / 1000 - seconds));
  if (delta < 60) return `${delta}s ago`;
  if (delta < 3600) return `${Math.floor(delta / 60)}m ago`;
  return `${Math.floor(delta / 3600)}h ago`;
}

export function postureColor(slouchPct: number): string {
  if (slouchPct < 0.1) return 'var(--posture-great)';
  if (slouchPct < 0.2) return 'var(--posture-good)';
  if (slouchPct < 0.35) return 'var(--posture-okay)';
  if (slouchPct < 0.5) return 'var(--posture-bad)';
  return 'var(--posture-poor)';
}
