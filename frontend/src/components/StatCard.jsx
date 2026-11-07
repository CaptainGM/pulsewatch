export default function StatCard({ label, value, hint, icon, tone = 'mint' }) {
  return (
    <article className={`stat-card tone-${tone}`}>
      <span className="stat-icon" aria-hidden="true">
        {icon}
      </span>
      <div className="stat-copy">
        <span className="stat-label">{label}</span>
        <strong className="stat-value">{value}</strong>
        {hint ? <span className="stat-hint">{hint}</span> : null}
      </div>
    </article>
  );
}
