import { Globe2 } from 'lucide-react';
import { api } from '../api';
import { useApi } from '../hooks';
import { fmtMs, timeAgo } from '../utils';

export default function RegionsCard({ monitorId }) {
  const regions = useApi((signal) => api.monitorRegions(monitorId, signal), [monitorId], {
    pollMs: 60000,
  });
  const rows = regions.data || [];

  return (
    <section className="panel regions-panel">
      <header className="section-head">
        <div>
          <h2>Bölgeler</h2>
          <p>Uzak ajanların son kontrolleri. Bildirimler yalnızca merkez kontrolünden gönderilir.</p>
        </div>
      </header>
      {rows.length === 0 ? (
        <div className="mini-empty">
          <Globe2 size={20} />
          <span>Henüz bölge verisi yok. scripts/agent.py ile bir bölge ekleyin.</span>
        </div>
      ) : (
        <ul className="region-list">
          {rows.map((row) => (
            <li key={row.region}>
              <span className={`status-pill ${row.success ? 'up' : 'down'}`}>
                {row.success ? 'Çalışıyor' : 'Hata'}
              </span>
              <strong>{row.region}</strong>
              <span className="mono-cell">{fmtMs(row.response_time_ms)}</span>
              <span className="muted-cell">{timeAgo(row.checked_at)}</span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
