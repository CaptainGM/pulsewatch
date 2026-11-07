import { statusInfo, statusTone } from '../utils';

export function StatusBadge({ status, active = true }) {
  const info = statusInfo(status, active);
  return (
    <span className={`status-pill ${info.tone}`}>
      <i className={`status-dot ${info.tone}`} aria-hidden="true" />
      {info.label}
    </span>
  );
}

export function StatusCode({ code }) {
  const tone = statusTone(code);
  return <span className={`code-chip ${tone}`}>{code ?? 'Hata'}</span>;
}

export function MethodChip({ method = 'GET' }) {
  return <span className={`method-chip method-${method.toLowerCase()}`}>{method}</span>;
}
