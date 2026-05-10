import type { Status } from '../api';

const PILL_BY_STATE: Record<string, { label: string; cls: string }> = {
  idle: { label: 'Idle', cls: 'pill-idle' },
  searching: { label: 'Searching', cls: 'pill-searching' },
  locked: { label: 'Locked', cls: 'pill-locked' },
  paused: { label: 'Paused', cls: 'pill-paused' },
};

function fmtAngle(value: number | null): string {
  return value == null ? '—' : `${value.toFixed(1)}°`;
}

function fmtSeconds(t: number | null): string {
  if (t == null) return '—';
  const delta = Math.max(0, Math.floor(Date.now() / 1000 - t));
  if (delta < 60) return `${delta}s ago`;
  if (delta < 3600) return `${Math.floor(delta / 60)}m ago`;
  return `${Math.floor(delta / 3600)}h ago`;
}

export function StatusCard({ status }: { status: Status }) {
  const showSlouching = status.is_slouching && status.state === 'locked';
  const pill = showSlouching
    ? { label: 'Slouching', cls: 'pill-slouching' }
    : PILL_BY_STATE[status.state] ?? PILL_BY_STATE.idle;

  return (
    <div className="card">
      <div className="status-row">
        <span className={`status-pill ${pill.cls}`}>
          <span className="dot" />
          {pill.label}
        </span>
        <div>
          <div style={{ fontSize: '0.95rem', fontWeight: 500 }}>
            {describe(status)}
          </div>
          {status.people_in_frame > 1 && (
            <div className="helper">
              {status.people_in_frame} people in frame — tracking the closest one.
            </div>
          )}
        </div>
        <div className="helper">{status.settling ? 'Settling…' : ''}</div>
      </div>

      <div className="metric-grid">
        <Metric label="Live CVA" value={fmtAngle(status.current_cva)} />
        <Metric label="Baseline" value={fmtAngle(status.baseline_cva)} />
        <Metric
          label="Deviation"
          value={status.deviation == null ? '—' : `${status.deviation.toFixed(1)}°`}
        />
        <Metric label="Last alert" value={fmtSeconds(status.last_alert_at)} />
      </div>
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="metric">
      <div className="label">{label}</div>
      <div className="value">{value}</div>
    </div>
  );
}

function describe(status: Status): string {
  if (!status.monitoring) return 'Monitoring is stopped.';
  if (!status.calibrated) return 'Sit upright and press Calibrate to start.';
  switch (status.state) {
    case 'searching':
      return 'Looking for you in front of the camera.';
    case 'paused':
      return 'You stepped away. Sentry will pick up where it left off when you return.';
    case 'locked':
      if (status.is_slouching) {
        return 'Your craniovertebral angle has dropped — sit up to reset it.';
      }
      return 'Tracking your posture.';
    default:
      return '';
  }
}
