import { useEffect, useState } from 'react';

import type { Status } from '../api';
import { api } from '../api';

interface Props {
  status: Status;
  onComplete: (ok: boolean, message?: string) => void;
}

export function CalibrationPanel({ status, onComplete }: Props) {
  const [countdown, setCountdown] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (countdown === null) return;
    if (countdown === 0) {
      setBusy(true);
      api
        .calibrate()
        .then((res) => onComplete(res.status === 'success', res.message))
        .catch((err) => onComplete(false, String(err)))
        .finally(() => {
          setBusy(false);
          setCountdown(null);
        });
      return;
    }
    const t = window.setTimeout(() => setCountdown(countdown - 1), 1000);
    return () => window.clearTimeout(t);
  }, [countdown, onComplete]);

  const start = () => setCountdown(3);

  if (!status.person_detected) {
    return (
      <div className="card">
        <div className="banner warning">
          We can't see you yet. Sit in front of the camera to enable calibration.
        </div>
      </div>
    );
  }

  return (
    <div className="card" style={{ textAlign: 'center' }}>
      {countdown === null ? (
        <>
          <p style={{ marginTop: 0 }}>
            Sit comfortably upright with your ears over your shoulders. Sentry will sample
            your craniovertebral angle for a few seconds.
          </p>
          <button onClick={start} disabled={busy}>
            {busy ? 'Calibrating…' : 'Calibrate good posture'}
          </button>
          <p className="helper" style={{ marginTop: 12 }}>
            Aim for a baseline of at least 50°. Anything lower suggests your reference
            posture itself is forward-leaning.
          </p>
        </>
      ) : countdown > 0 ? (
        <>
          <div className="calibration-countdown">{countdown}</div>
          <p className="helper">Hold your best posture…</p>
        </>
      ) : (
        <>
          <div className="calibration-countdown">·</div>
          <p className="helper">Sampling baseline…</p>
        </>
      )}
    </div>
  );
}
