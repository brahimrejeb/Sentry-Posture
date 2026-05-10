import { useCallback, useEffect, useRef, useState } from 'react';

import type { DeviceInfo, Status } from './api';
import { api } from './api';
import { CalibrationPanel } from './components/CalibrationPanel';
import { SettingsView } from './components/SettingsView';
import { StandUpRing } from './components/StandUpRing';
import { StatusCard } from './components/StatusCard';
import { Tabs } from './components/Tabs';
import { RangeView } from './components/history/RangeView';
import { TodayView } from './components/history/TodayView';
import { WeekView } from './components/history/WeekView';
import { useView } from './hooks/useView';

const DEFAULT_STATUS: Status = {
  monitoring: false,
  state: 'idle',
  calibrated: false,
  is_slouching: false,
  person_detected: false,
  people_in_frame: 0,
  settling: false,
  welcome_back: false,
  current_cva: null,
  baseline_cva: null,
  deviation: null,
  last_alert_at: null,
  sensitivity_threshold: 12,
  slouch_time_threshold: 10,
  alert_cooldown: 30,
  current_model: 'full',
  available_models: [],
  locked_streak_seconds: 0,
  stand_up_after_seconds: 3000,
  daily_slouch_goal_pct: 0.2,
  daily_break_goal: 5,
  mode: 'simple',
};

export default function App() {
  const [status, setStatus] = useState<Status>(DEFAULT_STATUS);
  const [devices, setDevices] = useState<DeviceInfo[]>([]);
  const [selectedDevice, setSelectedDevice] = useState('0');
  const [ipAddress, setIpAddress] = useState('');
  const [debugMode, setDebugMode] = useState(false);
  const [busy, setBusy] = useState(false);
  const [banner, setBanner] = useState<{ kind: 'info' | 'warning'; text: string } | null>(null);
  const [view, setView] = useView();
  const lastWelcomeBack = useRef(false);

  // Redirect advanced-only views to Live when in simple mode.
  useEffect(() => {
    const advancedViews: typeof view[] = ['today', 'week', 'month', 'year'];
    if (status.mode === 'simple' && advancedViews.includes(view)) {
      setView('live');
    }
  }, [status.mode, view, setView]);

  useEffect(() => {
    let cancelled = false;
    api
      .devices()
      .then((data) => {
        if (cancelled) return;
        setDevices(data.devices);
        if (data.devices.length > 0) setSelectedDevice(data.devices[0].id);
      })
      .catch(() => {
        /* offline; user will see it via /status polling */
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    const tick = async () => {
      try {
        const next = await api.status();
        if (cancelled) return;
        setStatus(next);
        if (next.welcome_back && !lastWelcomeBack.current) {
          setBanner({
            kind: 'info',
            text:
              "You've been away for a while. If your seat moved, a quick re-calibration will keep alerts accurate.",
          });
        }
        lastWelcomeBack.current = next.welcome_back;
      } catch {
        /* polling errors silenced */
      }
    };
    tick();
    const id = window.setInterval(tick, 1000);
    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, []);

  const startMonitoring = async () => {
    const src = selectedDevice === 'ip' ? ipAddress : selectedDevice;
    if (!src) return;
    setBusy(true);
    try {
      const res = await api.start(src);
      if (res.status !== 'started') {
        setBanner({ kind: 'warning', text: res.message ?? 'Could not start the camera.' });
      }
    } finally {
      setBusy(false);
    }
  };

  const stopMonitoring = async () => {
    setBusy(true);
    try {
      await api.stop();
    } finally {
      setBusy(false);
    }
  };

  const onCalibrationComplete = useCallback((ok: boolean, message?: string) => {
    setBanner(
      ok
        ? { kind: 'info', text: message ?? 'Calibration successful.' }
        : { kind: 'warning', text: message ?? 'Calibration failed.' },
    );
  }, []);

  const updateConfig = async (patch: Parameters<typeof api.config>[0]) => {
    try {
      const next = await api.config(patch);
      setStatus(next);
    } catch (err) {
      setBanner({ kind: 'warning', text: String(err) });
    }
  };

  return (
    <div className="app">
      <header className="card">
        <div className="brand">
          <img src="/sentry_logo.png" alt="Sentry" />
          <div>
            <h1>Sentry</h1>
            <p>Local, privacy-first posture monitor.</p>
          </div>
        </div>
      </header>

      <Tabs view={view} onChange={setView} mode={status.mode} />

      {banner && (
        <div className={`banner ${banner.kind === 'warning' ? 'warning' : ''}`}>
          <span>{banner.text}</span>
          <button
            className="secondary"
            style={{ padding: '4px 10px', marginLeft: 'auto' }}
            onClick={() => setBanner(null)}
          >
            Dismiss
          </button>
        </div>
      )}

      {view === 'live' && (
        <LiveView
          status={status}
          devices={devices}
          selectedDevice={selectedDevice}
          setSelectedDevice={setSelectedDevice}
          ipAddress={ipAddress}
          setIpAddress={setIpAddress}
          busy={busy}
          startMonitoring={startMonitoring}
          stopMonitoring={stopMonitoring}
          debugMode={debugMode}
          onCalibrationComplete={onCalibrationComplete}
        />
      )}
      {view === 'today' && (
        <TodayView goalPct={status.daily_slouch_goal_pct} goalBreaks={status.daily_break_goal} />
      )}
      {view === 'week' && (
        <WeekView goalPct={status.daily_slouch_goal_pct} goalBreaks={status.daily_break_goal} />
      )}
      {view === 'month' && <RangeView scope="month" goalPct={status.daily_slouch_goal_pct} />}
      {view === 'year' && <RangeView scope="year" goalPct={status.daily_slouch_goal_pct} />}
      {view === 'settings' && (
        <SettingsView
          status={status}
          onChange={updateConfig}
          debugMode={debugMode}
          setDebugMode={setDebugMode}
        />
      )}

      <footer className="helper" style={{ textAlign: 'center', marginTop: 16 }}>
        Sentry runs entirely on your computer. No data leaves this device.
      </footer>
    </div>
  );
}

interface LiveProps {
  status: Status;
  devices: DeviceInfo[];
  selectedDevice: string;
  setSelectedDevice: (s: string) => void;
  ipAddress: string;
  setIpAddress: (s: string) => void;
  busy: boolean;
  startMonitoring: () => void;
  stopMonitoring: () => void;
  debugMode: boolean;
  onCalibrationComplete: (ok: boolean, message?: string) => void;
}

function LiveView(props: LiveProps) {
  const { status, devices, selectedDevice, setSelectedDevice, ipAddress, setIpAddress } = props;
  const isAdvanced = status.mode === 'advanced';
  const showStandUpRing =
    isAdvanced && status.monitoring && status.calibrated && status.state === 'locked';

  return (
    <>
      <div className="live-row">
        <div style={{ flex: 1 }}>
          <StatusCard status={status} />
        </div>
        {showStandUpRing && (
          <div className="card stand-up-card">
            <div className="kpi-label">Next break</div>
            <StandUpRing
              lockedStreakSeconds={status.locked_streak_seconds}
              standUpAfterSeconds={status.stand_up_after_seconds}
            />
          </div>
        )}
      </div>

      {!status.monitoring ? (
        <div className="card section">
          <h2>Camera</h2>
          <div className="field">
            <select
              value={selectedDevice}
              onChange={(e) => setSelectedDevice(e.target.value)}
            >
              {devices.map((d) => (
                <option key={d.id} value={d.id}>
                  {d.name}
                </option>
              ))}
            </select>
            {selectedDevice === 'ip' && (
              <input
                type="text"
                placeholder="http://phone-ip:8080/video"
                value={ipAddress}
                onChange={(e) => setIpAddress(e.target.value)}
              />
            )}
            <button
              onClick={props.startMonitoring}
              disabled={props.busy || (selectedDevice === 'ip' && !ipAddress)}
            >
              {props.busy ? 'Starting…' : 'Start monitoring'}
            </button>
          </div>
          <div className="helper">Sentry analyses frames locally. Nothing is uploaded.</div>
        </div>
      ) : (
        <>
          {!status.calibrated ? (
            <CalibrationPanel status={status} onComplete={props.onCalibrationComplete} />
          ) : (
            <div className="card">
              <div className="controls">
                <button
                  className="secondary"
                  onClick={() =>
                    api
                      .calibrate()
                      .then((r) => props.onCalibrationComplete(r.status === 'success', r.message))
                      .catch((err) => props.onCalibrationComplete(false, String(err)))
                  }
                >
                  Re-calibrate
                </button>
                <button className="danger" onClick={props.stopMonitoring} disabled={props.busy}>
                  Stop monitoring
                </button>
              </div>
            </div>
          )}

          {props.debugMode && isAdvanced && (
            <div className="card">
              <div className="video">
                <img src={api.feedUrl(true)} alt="Camera feed" />
              </div>
              <p className="helper" style={{ marginTop: 8 }}>
                Frames stay on this machine — nothing is uploaded.
              </p>
            </div>
          )}
        </>
      )}
    </>
  );
}
