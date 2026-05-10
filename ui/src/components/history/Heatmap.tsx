import type { DaySummary } from '../../api';
import { fmtDuration, fmtPct, postureColor } from '../../format';

interface Props {
  days: DaySummary[];
  cellSize?: number;
  /** Show weekday labels on the y-axis (year heatmap only). */
  showWeekdayAxis?: boolean;
}

/**
 * GitHub-style calendar heatmap. Days flow column-by-column (top → bottom)
 * starting on the first Sunday at or before the earliest day. The cell
 * colour reflects posture quality, the cell opacity reflects how much
 * locked time we have for that day.
 */
export function Heatmap({ days, cellSize = 14, showWeekdayAxis = false }: Props) {
  if (days.length === 0) return null;

  const first = new Date(days[0].date + 'T00:00:00');
  const offset = first.getDay(); // 0 = Sunday
  const cells: (DaySummary | null)[] = Array(offset).fill(null).concat(days);
  const rows = 7;
  const cols = Math.ceil(cells.length / rows);
  const padded = cells.concat(Array(cols * rows - cells.length).fill(null));

  const width = cols * (cellSize + 3) + (showWeekdayAxis ? 30 : 0);
  const height = rows * (cellSize + 3) + 28; // room for month labels

  const monthLabels = computeMonthLabels(padded, cellSize, showWeekdayAxis ? 30 : 0);

  return (
    <svg className="heatmap" viewBox={`0 0 ${width} ${height}`} width="100%">
      {monthLabels.map((m, i) => (
        <text
          key={i}
          x={m.x}
          y={12}
          fontSize={11}
          fill="var(--text-muted)"
        >
          {m.label}
        </text>
      ))}
      {showWeekdayAxis &&
        ['', 'Mon', '', 'Wed', '', 'Fri', ''].map((label, r) =>
          label ? (
            <text
              key={r}
              x={4}
              y={r * (cellSize + 3) + cellSize + 16}
              fontSize={10}
              fill="var(--text-muted)"
            >
              {label}
            </text>
          ) : null,
        )}
      {padded.map((d, i) => {
        const col = Math.floor(i / rows);
        const row = i % rows;
        const x = col * (cellSize + 3) + (showWeekdayAxis ? 30 : 0);
        const y = row * (cellSize + 3) + 18;
        if (d === null) return null;
        const has = d.locked_seconds > 0;
        const fill = has ? postureColor(d.slouch_pct) : 'var(--surface-muted)';
        const opacity = has ? 0.35 + 0.65 * Math.min(1, d.locked_seconds / 7200) : 1;
        return (
          <rect
            key={d.date}
            x={x}
            y={y}
            width={cellSize}
            height={cellSize}
            rx={2}
            fill={fill}
            opacity={opacity}
          >
            <title>
              {has
                ? `${d.date} — ${fmtDuration(d.locked_seconds)} (${fmtPct(d.slouch_pct)} slouch, ${d.breaks} breaks)`
                : `${d.date} — no activity`}
            </title>
          </rect>
        );
      })}
    </svg>
  );
}

function computeMonthLabels(
  cells: (DaySummary | null)[],
  cellSize: number,
  xOffset: number,
): { x: number; label: string }[] {
  const out: { x: number; label: string }[] = [];
  let lastMonth = -1;
  for (let i = 0; i < cells.length; i += 7) {
    const cell = cells[i];
    if (!cell) continue;
    const month = new Date(cell.date + 'T00:00:00').getMonth();
    if (month !== lastMonth) {
      const col = i / 7;
      out.push({
        x: xOffset + col * (cellSize + 3),
        label: new Date(cell.date + 'T00:00:00').toLocaleDateString(undefined, {
          month: 'short',
        }),
      });
      lastMonth = month;
    }
  }
  return out;
}
