import { AlertTriangle, Inbox, RefreshCw } from 'lucide-react';

export function EmptyState({ icon, title, message, action }) {
  return (
    <div className="empty-state">
      <span className="empty-icon" aria-hidden="true">
        {icon ?? <Inbox size={26} />}
      </span>
      <h3>{title}</h3>
      {message ? <p>{message}</p> : null}
      {action}
    </div>
  );
}

export function ErrorPanel({ error, onRetry, title = 'Veriler yüklenemedi' }) {
  return (
    <div className="error-panel" role="alert">
      <span className="error-panel-icon" aria-hidden="true">
        <AlertTriangle size={22} />
      </span>
      <div>
        <h3>{title}</h3>
        <p>{error?.message || 'Beklenmeyen bir hata oluştu.'}</p>
      </div>
      {onRetry ? (
        <button type="button" className="btn ghost sm" onClick={onRetry}>
          <RefreshCw size={14} /> Tekrar dene
        </button>
      ) : null}
    </div>
  );
}

export function DashboardSkeleton() {
  return (
    <div className="skeleton-page" aria-label="Yükleniyor">
      <div className="skeleton skeleton-title" />
      <div className="stats-grid">
        {[0, 1, 2, 3].map((item) => (
          <div key={item} className="skeleton skeleton-stat" />
        ))}
      </div>
      <div className="hero-grid">
        {[0, 1, 2].map((item) => (
          <div key={item} className="skeleton skeleton-chart" />
        ))}
      </div>
      <div className="skeleton skeleton-table" />
    </div>
  );
}
