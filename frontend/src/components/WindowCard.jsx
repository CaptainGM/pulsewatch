export default function WindowCard({ title, badge, children, right, className = '' }) {
  return (
    <section className={`window-card ${className}`.trim()}>
      <header className="window-head">
        <span className="traffic-lights" aria-hidden="true">
          <i className="red" />
          <i className="amber" />
          <i className="green" />
        </span>
        <h2 className="window-title">{title}</h2>
        <div className="window-head-right">
          {right ?? (
            <span className="window-signal" aria-hidden="true">
              <i />
              <i />
              <i />
            </span>
          )}
        </div>
        {badge ? <span className="window-badge">{badge}</span> : null}
      </header>
      <div className="window-body">{children}</div>
    </section>
  );
}
