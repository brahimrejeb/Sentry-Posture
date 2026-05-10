import { useEffect, useState } from 'react';

import type { AutostartInfo, Status } from '../api';
import { api } from '../api';

interface Props {
  status: Status;
  onChange: (patch: Parameters<typeof api.config>[0]) => void;
  debugMode: boolean;
  setDebugMode: (v: boolean) => void;
}

const MODEL_LABEL: Record<string, string> = {
  lite: 'Lite — fastest, less accurate',
  full: 'Full — balanced (default)',
  heavy: 'Heavy — most accurate, more CPU',
};

function formatTime(seconds: number): string {
  if (seconds < 60) return `${seconds}s`;
  const m = Math.floor(seconds / 60);
  const s = Math.round(seconds % 60);
  return s > 0 ? `${m}m ${s}s` : `${m}m`;
}

export function SettingsView({ status, onChange, debugMode, setDebugMode }: Props) {
  const [confirmingClear, setConfirmingClear] = useState(false);
  const [clearedMsg, setClearedMsg] = useState<string | null>(null);
  const [autostart, setAutostart] = useState<AutostartInfo | null>(null);
  const [autostartError, setAutostartError] = useState<string | null>(null);

  const isAdvanced = status.mode === 'advanced';
  const standUpMins = Math.round(status.stand_up_after_seconds / 60);

  useEffect(() => {
    let cancelled = false;
    api
      .autostart()
      .then((data) => !cancelled && setAutostart(data))
      .catch((err) => !cancelled && setAutostartError(String(err)));
    return () => {
      cancelled = true;
    };
  }, []);

  const toggleAutostart = async (enabled: boolean) => {
    setAutostartError(null);
    try {
      const next = await api.setAutostart(enabled);
      setAutostart(next);
    } catch (err) {
      setAutostartError(String(err));
    }
  };

  return (
    <>
      <div className="card section">
        <h2>Detection</h2>
        <div className="field">
          <div className="field-row">
            <label htmlFor="model">Tracking model</label>
            <select
              id="model"
              value={status.current_model}
              onChange={(e) => onChange({ model_level: e.target.value })}
            >
              {(['lite', 'full', 'heavy'] as const).map((level) => (
                <option
                  key={level}
                  value={level}
                  disabled={!status.available_models.includes(level)}
                >
                  {MODEL_LABEL[level]}
                  {!status.available_models.includes(level) ? ' (download required)' : ''}
                </option>
              ))}
            </select>
          </div>
          <div className="helper">
            Heavier models track more reliably under poor lighting. Switching levels triggers a
            download on first use.
          </div>
        </div>
      </div>

      <div className="card section">
        <h2>Alerts</h2>
        <div className="field">
          <div className="field-row">
            <label htmlFor="sens">Sensitivity</label>
            <span>{status.sensitivity_threshold.toFixed(1)}°</span>
          </div>
          <input
            id="sens"
            type="range"
            min={5}
            max={30}
            step={0.5}
            value={status.sensitivity_threshold}
            onChange={(e) => onChange({ sensitivity_threshold: parseFloat(e.target.value) })}
          />
          <div className="helper">
            How far your CVA must drop below your calibrated baseline before it counts as
            slouching. Lower values are stricter.
          </div>
        </div>

        <div className="field">
          <div className="field-row">
            <label htmlFor="time">Time window</label>
            <span>{formatTime(status.slouch_time_threshold)}</span>
          </div>
          <input
            id="time"
            type="range"
            min={5}
            max={600}
            step={5}
            value={status.slouch_time_threshold}
            onChange={(e) => onChange({ slouch_time_threshold: parseFloat(e.target.value) })}
          />
          <div className="helper">
            You'll only be notified if your posture stays bad for this long.
          </div>
        </div>

        <div className="field">
          <div className="field-row">
            <label htmlFor="cooldown">Cooldown after alert</label>
            <span>{formatTime(status.alert_cooldown)}</span>
          </div>
          <input
            id="cooldown"
            type="range"
            min={0}
            max={300}
            step={5}
            value={status.alert_cooldown}
            onChange={(e) => onChange({ alert_cooldown: parseFloat(e.target.value) })}
          />
          <div className="helper">Sentry won't fire another alert during this window.</div>
        </div>
      </div>

      {isAdvanced && (
        <div className="card section">
          <h2>Breaks &amp; goals</h2>
          <div className="field">
            <div className="field-row">
              <label htmlFor="standup">Stand-up reminder after</label>
              <span>{standUpMins} min</span>
            </div>
            <input
              id="standup"
              type="range"
              min={20}
              max={120}
              step={5}
              value={standUpMins}
              onChange={(e) => onChange({ stand_up_after_minutes: parseFloat(e.target.value) })}
            />
            <div className="helper">
              Apple-Watch style. After this long at your desk Sentry nudges you to stand and
              stretch. Resets the moment you take a break.
            </div>
          </div>

          <div className="field">
            <div className="field-row">
              <label htmlFor="slouchgoal">Daily slouch goal</label>
              <span>≤ {(status.daily_slouch_goal_pct * 100).toFixed(0)}%</span>
            </div>
            <input
              id="slouchgoal"
              type="range"
              min={0.05}
              max={0.5}
              step={0.05}
              value={status.daily_slouch_goal_pct}
              onChange={(e) => onChange({ daily_slouch_goal_pct: parseFloat(e.target.value) })}
            />
            <div className="helper">A day counts toward your streak when you stay below this.</div>
          </div>

          <div className="field">
            <div className="field-row">
              <label htmlFor="breakgoal">Daily break goal</label>
              <span>{status.daily_break_goal} breaks</span>
            </div>
            <input
              id="breakgoal"
              type="range"
              min={0}
              max={12}
              step={1}
              value={status.daily_break_goal}
              onChange={(e) => onChange({ daily_break_goal: parseInt(e.target.value, 10) })}
            />
          </div>
        </div>
      )}

      <div className="card section section-platform">
        <h2>Mode</h2>
        <div className="mode-toggle" role="radiogroup" aria-label="App mode">
          <button
            type="button"
            role="radio"
            aria-checked={status.mode === 'simple'}
            className={`mode-option ${status.mode === 'simple' ? 'mode-active' : ''}`}
            onClick={() => onChange({ mode: 'simple' })}
          >
            <strong>Simple</strong>
            <span>Slouch detection &amp; alerts only.</span>
          </button>
          <button
            type="button"
            role="radio"
            aria-checked={status.mode === 'advanced'}
            className={`mode-option ${status.mode === 'advanced' ? 'mode-active' : ''}`}
            onClick={() => onChange({ mode: 'advanced' })}
          >
            <strong>Advanced</strong>
            <span>Adds history, goals, stand-up nudges, diagnostics.</span>
          </button>
        </div>
        <div className="helper" style={{ marginTop: 10 }}>
          Switching to Advanced starts recording history from that moment on. Switching back to
          Simple stops new recording but keeps existing data on disk so you can flip back later.
        </div>
      </div>

      <div className="card section section-platform">
        <h2>Startup</h2>
        {autostart === null && !autostartError && (
          <div className="helper">Loading…</div>
        )}
        {autostartError && <div className="banner warning">{autostartError}</div>}
        {autostart && (
          <>
            <div className="field-row">
              <label htmlFor="autostart">
                Start Sentry automatically when I log in
              </label>
              <input
                id="autostart"
                type="checkbox"
                checked={autostart.enabled}
                disabled={!autostart.supported}
                onChange={(e) => toggleAutostart(e.target.checked)}
              />
            </div>
            {!autostart.supported && (
              <div className="helper">
                Auto-start isn't supported on this platform ({autostart.platform}).
              </div>
            )}
            {autostart.supported && (
              <div className="helper" style={{ marginTop: 8 }}>
                Sentry will boot quietly to your system tray on next login. Click the tray icon
                to open the dashboard. Per-user entry — no admin password needed. If something
                goes wrong, the boot log is written to <code>~/.sentry/sentry.log</code>.
              </div>
            )}
            {autostart.command && (
              <div className="autostart-preview">
                <span className="autostart-label">Command</span>
                <code>{autostart.command}</code>
                <span className="autostart-label">Location</span>
                <code>{autostart.target}</code>
              </div>
            )}
          </>
        )}
      </div>

      {isAdvanced && (
        <div className="card section">
          <h2>Diagnostics</h2>
          <div className="field-row">
            <label htmlFor="debug">Show camera + landmarks</label>
            <input
              id="debug"
              type="checkbox"
              checked={debugMode}
              onChange={(e) => setDebugMode(e.target.checked)}
            />
          </div>
          <div className="helper">
            Visible only on the Live tab. Frames stay on this machine.
          </div>
        </div>
      )}

      {isAdvanced && (
        <div className="card section">
          <h2>Privacy</h2>
          <p className="helper" style={{ marginBottom: 12 }}>
            History is stored on your machine in <code>~/.sentry/history.db</code>. You can wipe
            it any time.
          </p>
          {clearedMsg ? (
            <div className="banner">{clearedMsg}</div>
          ) : confirmingClear ? (
            <div className="controls">
              <button
                className="danger"
                onClick={async () => {
                  await api.clearHistory();
                  setConfirmingClear(false);
                  setClearedMsg('History cleared.');
                  window.setTimeout(() => setClearedMsg(null), 4000);
                }}
              >
                Yes, delete everything
              </button>
              <button className="secondary" onClick={() => setConfirmingClear(false)}>
                Cancel
              </button>
            </div>
          ) : (
            <button className="secondary" onClick={() => setConfirmingClear(true)}>
              Clear history
            </button>
          )}
        </div>
      )}
    </>
  );
}
