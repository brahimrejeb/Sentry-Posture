interface Props {
  label: string;
  value: string;
  hint?: string;
  tone?: 'default' | 'good' | 'warning' | 'bad';
}

export function KpiCard({ label, value, hint, tone = 'default' }: Props) {
  return (
    <div className={`kpi kpi-${tone}`}>
      <div className="kpi-label">{label}</div>
      <div className="kpi-value">{value}</div>
      {hint && <div className="kpi-hint">{hint}</div>}
    </div>
  );
}
