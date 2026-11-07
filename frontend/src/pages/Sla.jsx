import { useState } from 'react';
import { Download, ShieldCheck } from 'lucide-react';
import { api, downloadFile } from '../api';
import { DashboardSkeleton, EmptyState, ErrorPanel } from '../components/States';
import { useApi, useDocumentTitle } from '../hooks';
import { useApp } from '../context/AppContext';
import { fmtDateTime, fmtNumber, fmtPercent } from '../utils';

const PERIODS = [
  { days: 7, label: 'Son 7 gün' },
  { days: 30, label: 'Son 30 gün' },
  { days: 90, label: 'Son 90 gün' },
];

export default function Sla() {
  useDocumentTitle('SLA');
  const { notify } = useApp();
  const [days, setDays] = useState(30);
  const report = useApi((signal) => api.sla(days, signal), [days]);

  if (report.loading && !report.data) return <DashboardSkeleton />;
  if (report.error && !report.data) return <ErrorPanel error={report.error} onRetry={report.reload} />;

  const data = report.data;
  const rows = data.monitors;

  async function exportCsv() {
    try {
      await downloadFile(`/sla/export.csv?days=${days}`, `sla-${days}-gun.csv`);
    } catch (err) {
      notify('error', 'Dışa aktarılamadı', err.message);
    }
  }

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <p className="eyebrow">Hizmet seviyesi</p>
          <h1 className="page-title">SLA raporu</h1>
          <p className="page-sub">
            Hedef {fmtPercent(data.target_percent, 2)}. Bakım pencereleri kesinti sayılmaz.
          </p>
        </div>
        <div className="page-head-actions">
          <select
            aria-label="Rapor dönemi"
            value={days}
            onChange={(event) => setDays(Number(event.target.value))}
          >
            {PERIODS.map((period) => (
              <option key={period.days} value={period.days}>
                {period.label}
              </option>
            ))}
          </select>
          <button type="button" className="btn ghost" onClick={exportCsv}>
            <Download size={15} /> CSV indir
          </button>
        </div>
      </div>

      <div className="stats-grid">
        <div className="panel sla-summary">
          <span>Genel erişilebilirlik</span>
          <strong>{fmtPercent(data.overall_percent, 3)}</strong>
          <small>
            {fmtDateTime(data.period_start)} – {fmtDateTime(data.period_end)}
          </small>
        </div>
        <div className="panel sla-summary">
          <span>Hedefi tutturan API</span>
          <strong>
            {rows.filter((row) => row.meets_target).length} / {rows.length}
          </strong>
          <small>Hedef: {fmtPercent(data.target_percent, 2)}</small>
        </div>
        <div className="panel sla-summary">
          <span>Toplam kesinti</span>
          <strong>{fmtNumber(Math.round(rows.reduce((sum, row) => sum + row.downtime_minutes, 0)))} dk</strong>
          <small>{rows.reduce((sum, row) => sum + row.incidents, 0)} olay</small>
        </div>
      </div>

      {rows.length === 0 ? (
        <section className="panel">
          <EmptyState
            icon={<ShieldCheck size={28} />}
            title="Rapor için API yok"
            message="API ekledikçe erişilebilirlik ve hata bütçesi burada hesaplanır."
          />
        </section>
      ) : (
        <section className="panel">
          <div className="table-wrap">
            <table className="data-table">
              <thead>
                <tr>
                  <th>API</th>
                  <th>Erişilebilirlik</th>
                  <th>Kesinti</th>
                  <th>Olay</th>
                  <th>Hata bütçesi</th>
                  <th>Hedef</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => (
                  <tr key={row.monitor_id}>
                    <td>
                      <strong>{row.name}</strong>
                    </td>
                    <td>
                      <div className="sla-bar" aria-label={fmtPercent(row.availability_percent, 3)}>
                        <i
                          className={row.meets_target ? 'ok' : 'bad'}
                          style={{ width: `${Math.max(0, Math.min(100, row.availability_percent))}%` }}
                        />
                      </div>
                      <span className="mono-cell">{fmtPercent(row.availability_percent, 3)}</span>
                    </td>
                    <td className="mono-cell">{fmtNumber(row.downtime_minutes)} dk</td>
                    <td className="mono-cell">{row.incidents}</td>
                    <td className={`mono-cell ${row.error_budget_minutes < 0 ? 'text-danger' : ''}`}>
                      {fmtNumber(row.error_budget_minutes)} dk
                    </td>
                    <td>
                      <span className={`status-pill ${row.meets_target ? 'up' : 'down'}`}>
                        {row.meets_target ? 'Tutturuldu' : 'Aşıldı'}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}
    </div>
  );
}
