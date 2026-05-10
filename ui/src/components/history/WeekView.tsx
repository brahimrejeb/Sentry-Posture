import { useEffect, useState } from 'react';

import type { RangeHistory } from '../../api';
import { api } from '../../api';
import { fmtDuration, fmtPct } from '../../format';
import { DailyBars } from './DailyBars';
import { KpiCard } from './KpiCard';

export function WeekView({ goalPct, goalBreaks }: { goalPct: number; goalBreaks: number }) {
  const [data, setData] = useState<RangeHistory | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    api
      .historyWeek()
      .then((d) => !cancelled && setData(d))
      .catch((err) => !cancelled && setError(String(err)));
    return () => {
      cancelled = true;
    };
  }, []);

  if (error) return <div className="card banner warning">{error}</div>;
  if (!data) return <div className="card">Loading week…</div>;

  const totals = aggregate(data.days);
  const goalDays = data.days.filter(
    (d) => d.locked_seconds > 0 && d.slouch_pct <= goalPct,
  ).length;

  return (
    <>
      <div className="card section">
        <h2>This week</h2>
        <div className="kpi-grid">
          <KpiCard label="Total time at desk" value={fmtDuration(totals.locked)} />
          <KpiCard
            label="Avg slouching"
            value={totals.locked > 0 ? fmtPct(totals.slouch / totals.locked) : '—'}
            hint={`Goal: ≤ ${fmtPct(goalPct)}`}
          />
          <KpiCard label="Total breaks" value={String(totals.breaks)} hint={`Goal: ${goalBreaks}/day`} />
          <KpiCard
            label="Goal-met days"
            value={`${goalDays}/7`}
            tone={goalDays >= 5 ? 'good' : goalDays >= 3 ? 'warning' : 'default'}
          />
        </div>
      </div>

      <div className="card section">
        <h2>Daily breakdown</h2>
        <DailyBars days={data.days} goalPct={goalPct} />
        <div className="legend">
          <span className="legend-swatch swatch-upright" /> Upright
          <span className="legend-swatch swatch-slouch" /> Slouching
          <span className="legend-swatch swatch-goal" /> Goal met
        </div>
      </div>
    </>
  );
}

function aggregate(days: { locked_seconds: number; slouch_seconds: number; breaks: number }[]) {
  return days.reduce(
    (acc, d) => ({
      locked: acc.locked + d.locked_seconds,
      slouch: acc.slouch + d.slouch_seconds,
      breaks: acc.breaks + d.breaks,
    }),
    { locked: 0, slouch: 0, breaks: 0 },
  );
}
