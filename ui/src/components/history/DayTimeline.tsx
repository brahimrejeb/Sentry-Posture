import type { HourBucket } from '../../api';
import { fmtDuration, fmtPct } from '../../format';

const HOUR_LABELS = [0, 6, 12, 18, 23];

export function DayTimeline({ buckets }: { buckets: HourBucket[] }) {
  return (
    <div className="day-timeline">
      <div className="day-timeline-bar" role="img" aria-label="24-hour posture timeline">
        {buckets.map((b) => {
          const total = b.locked_seconds || 0;
          const slouchPct = total > 0 ? b.slouch_seconds / total : 0;
          const intensity = Math.min(1, total / 3600); // 1 hour = full opacity
          const upright = total - b.slouch_seconds;
          return (
            <div
              key={b.hour}
              className="day-timeline-cell"
              style={{ opacity: 0.15 + 0.85 * intensity }}
              title={
                total > 0
                  ? `${pad(b.hour)}:00 — Locked ${fmtDuration(total)} · Slouch ${fmtPct(
                      slouchPct,
                    )} · ${b.breaks} break${b.breaks === 1 ? '' : 's'}`
                  : `${pad(b.hour)}:00 — no activity`
              }
            >
              {total > 0 && (
                <>
                  <div
                    className="seg seg-upright"
                    style={{ flex: upright }}
                  />
                  <div
                    className="seg seg-slouch"
                    style={{ flex: b.slouch_seconds }}
                  />
                </>
              )}
              {b.breaks > 0 && <span className="seg-break-marker" aria-hidden />}
            </div>
          );
        })}
      </div>
      <div className="day-timeline-axis">
        {HOUR_LABELS.map((h) => (
          <span key={h} style={{ left: `${(h / 23) * 100}%` }}>
            {pad(h)}:00
          </span>
        ))}
      </div>
    </div>
  );
}

function pad(n: number): string {
  return n.toString().padStart(2, '0');
}
