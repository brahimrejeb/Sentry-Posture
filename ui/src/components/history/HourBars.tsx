import type { HourBucket } from '../../api';
import { fmtDuration, fmtPct } from '../../format';

export function HourBars({ buckets }: { buckets: HourBucket[] }) {
  const max = Math.max(60, ...buckets.map((b) => b.locked_seconds));
  return (
    <div className="hour-bars" role="img" aria-label="Locked time per hour">
      {buckets.map((b) => {
        const h = b.locked_seconds / max;
        const slouchH = b.slouch_seconds / max;
        const upright = h - slouchH;
        return (
          <div
            key={b.hour}
            className="hour-bar"
            title={
              b.locked_seconds > 0
                ? `${b.hour}:00 — ${fmtDuration(b.locked_seconds)} (${fmtPct(
                    b.slouch_seconds / Math.max(b.locked_seconds, 1),
                  )} slouch)`
                : `${b.hour}:00 — no activity`
            }
          >
            <div className="hour-bar-stack">
              <div
                className="hour-bar-slouch"
                style={{ height: `${slouchH * 100}%` }}
              />
              <div
                className="hour-bar-upright"
                style={{ height: `${upright * 100}%` }}
              />
            </div>
            {b.hour % 6 === 0 && <div className="hour-bar-label">{b.hour}</div>}
          </div>
        );
      })}
    </div>
  );
}
