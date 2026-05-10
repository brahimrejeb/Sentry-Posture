import type { DaySummary } from '../../api';
import { fmtDuration, fmtPct } from '../../format';

interface Props {
  days: DaySummary[];
  goalPct: number;
}

export function DailyBars({ days, goalPct }: Props) {
  const max = Math.max(60, ...days.map((d) => d.locked_seconds));
  return (
    <div className="daily-bars" role="img" aria-label="Locked time per day">
      {days.map((d) => {
        const h = d.locked_seconds / max;
        const slouchPct = d.slouch_seconds / Math.max(d.locked_seconds, 1);
        const slouchH = d.slouch_seconds / max;
        const upright = h - slouchH;
        const meetsGoal = d.locked_seconds > 0 && slouchPct <= goalPct;
        return (
          <div key={d.date} className="daily-bar">
            <div className="daily-bar-stack" title={tooltip(d)}>
              <div
                className="hour-bar-slouch"
                style={{ height: `${slouchH * 100}%` }}
              />
              <div
                className="hour-bar-upright"
                style={{ height: `${upright * 100}%` }}
              />
              {meetsGoal && <div className="daily-bar-goal" aria-hidden />}
            </div>
            <div className="daily-bar-meta">
              <div className="daily-bar-day">{shortDay(d.date)}</div>
              <div className="daily-bar-pct">
                {d.locked_seconds > 0 ? fmtPct(slouchPct) : '—'}
              </div>
              <div className="daily-bar-breaks">
                {d.breaks > 0 ? `${d.breaks} break${d.breaks === 1 ? '' : 's'}` : ''}
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}

function shortDay(iso: string): string {
  const dt = new Date(iso + 'T00:00:00');
  return dt.toLocaleDateString(undefined, { weekday: 'short' });
}

function tooltip(d: DaySummary): string {
  if (d.locked_seconds <= 0) return `${d.date} — no activity`;
  return `${d.date} — ${fmtDuration(d.locked_seconds)} locked, ${fmtPct(
    d.slouch_seconds / d.locked_seconds,
  )} slouch, ${d.breaks} break${d.breaks === 1 ? '' : 's'}`;
}
