import { useState } from 'react';
import { Check, Copy, KeyRound, Plus, Trash2 } from 'lucide-react';
import { api } from '../api';
import { useApi, useDocumentTitle } from '../hooks';
import { useApp } from '../context/AppContext';
import ConfirmDialog from '../components/ConfirmDialog';
import { DashboardSkeleton, EmptyState, ErrorPanel } from '../components/States';
import { fmtDateTime, timeAgo } from '../utils';

const ENDPOINTS = [
  { path: '/api/v1/status', note: 'Genel durum özeti. Anahtar gerektirmez.' },
  { path: '/api/v1/monitors', note: 'Tüm monitörler ve son 24 saatlik özet.' },
  { path: '/api/v1/monitors/{id}/stats?hours=24', note: 'Yanıt süresi, uptime ve HTTP kodları.' },
  { path: '/api/v1/incidents', note: 'Kesinti kayıtları.' },
];

export default function ApiKeys() {
  useDocumentTitle('API Anahtarları');
  const { notify } = useApp();
  const { data, loading, error, reload } = useApi((signal) => api.apiKeys(signal), []);
  const [name, setName] = useState('');
  const [busy, setBusy] = useState(false);
  const [created, setCreated] = useState(null);
  const [copied, setCopied] = useState(false);
  const [pendingDelete, setPendingDelete] = useState(null);

  const origin = window.location.origin;
  const exampleKey = created?.key || 'ANAHTARINIZ';
  const curlExample = `curl -H "X-API-Key: ${exampleKey}" \\\n  ${origin}/api/v1/monitors`;
  const pythonExample = `import httpx

response = httpx.get(
    "${origin}/api/v1/monitors",
    headers={"X-API-Key": "${exampleKey}"},
)
for monitor in response.json():
    print(monitor["name"], monitor["status"], monitor["uptime_percent"])`;

  async function handleCreate(event) {
    event.preventDefault();
    setBusy(true);
    try {
      const result = await api.createApiKey(name.trim());
      setCreated(result);
      setCopied(false);
      setName('');
      reload();
    } catch (err) {
      notify('error', 'Anahtar oluşturulamadı', err.message);
    } finally {
      setBusy(false);
    }
  }

  async function copyKey() {
    try {
      await navigator.clipboard.writeText(created.key);
      setCopied(true);
    } catch {
      notify('error', 'Kopyalanamadı', 'Anahtarı seçip elle kopyalayın.');
    }
  }

  async function confirmDelete() {
    const key = pendingDelete;
    setBusy(true);
    try {
      await api.deleteApiKey(key.id);
      notify('success', 'Anahtar iptal edildi', key.name);
      setPendingDelete(null);
      reload();
    } catch (err) {
      notify('error', 'Anahtar iptal edilemedi', err.message);
    } finally {
      setBusy(false);
    }
  }

  if (loading && !data) return <DashboardSkeleton />;
  if (error && !data) return <ErrorPanel error={error} onRetry={reload} />;

  const keys = data || [];

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <p className="eyebrow">Entegrasyon</p>
          <h1 className="page-title">API Anahtarları</h1>
          <p className="page-sub">
            Kendi sisteminizden PulseWatch verilerini okumak için anahtar oluşturun. Anahtar
            <code className="inline-code"> X-API-Key </code>
            başlığında gönderilir.
          </p>
        </div>
      </div>

      <div className="keys-layout">
        <div className="keys-main">
          <section className="panel">
            <form className="key-create" onSubmit={handleCreate}>
              <div className="field">
                <label htmlFor="key-name">Yeni anahtar adı</label>
                <input
                  id="key-name"
                  required
                  maxLength={120}
                  value={name}
                  onChange={(event) => setName(event.target.value)}
                  placeholder="Ör. Müşteri paneli"
                />
              </div>
              <button type="submit" className="btn primary" disabled={busy || !name.trim()}>
                <Plus size={16} /> Anahtar oluştur
              </button>
            </form>

            {created ? (
              <div className="key-reveal" role="status">
                <div>
                  <strong>{created.name} anahtarı oluşturuldu</strong>
                  <span>Bu anahtar yalnızca şimdi gösterilir. Güvenli bir yere kaydedin.</span>
                </div>
                <div className="key-value">
                  <code>{created.key}</code>
                  <button type="button" className="btn ghost sm" onClick={copyKey}>
                    {copied ? <Check size={14} /> : <Copy size={14} />}
                    {copied ? 'Kopyalandı' : 'Kopyala'}
                  </button>
                </div>
              </div>
            ) : null}
          </section>

          <section className="panel">
            <header className="section-head">
              <div>
                <h2>Mevcut anahtarlar</h2>
                <p>{keys.length} anahtar kayıtlı</p>
              </div>
            </header>

            {keys.length === 0 ? (
              <EmptyState
                icon={<KeyRound size={26} />}
                title="Henüz anahtar yok"
                message="Sistemlerinizden erişim için yukarıdan bir anahtar oluşturun."
              />
            ) : (
              <div className="table-wrap">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>Ad</th>
                      <th>Önek</th>
                      <th>Oluşturuldu</th>
                      <th>Son kullanım</th>
                      <th aria-label="İşlemler" />
                    </tr>
                  </thead>
                  <tbody>
                    {keys.map((key) => (
                      <tr key={key.id}>
                        <td>
                          <strong>{key.name}</strong>
                        </td>
                        <td className="mono-cell">{key.prefix}…</td>
                        <td className="muted-cell" title={fmtDateTime(key.created_at)}>
                          {timeAgo(key.created_at)}
                        </td>
                        <td className="muted-cell">
                          {key.last_used_at ? timeAgo(key.last_used_at) : 'Hiç kullanılmadı'}
                        </td>
                        <td>
                          <button
                            type="button"
                            className="icon-btn sm danger"
                            aria-label={`${key.name} anahtarını iptal et`}
                            onClick={() => setPendingDelete(key)}
                          >
                            <Trash2 size={14} />
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>
        </div>

        <aside className="keys-side">
          <section className="panel usage-panel">
            <header className="section-head">
              <div>
                <h2>Nasıl kullanılır</h2>
                <p>Sisteminizden tek bir istekle veriyi çekebilirsiniz.</p>
              </div>
            </header>
            <pre className="code-block">
              <code>{curlExample}</code>
            </pre>
            <pre className="code-block">
              <code>{pythonExample}</code>
            </pre>
          </section>

          <section className="panel usage-panel">
            <header className="section-head">
              <div>
                <h2>Uç noktalar</h2>
                <p>Salt okunur entegrasyon API&apos;si</p>
              </div>
            </header>
            <ul className="endpoint-list">
              {ENDPOINTS.map((endpoint) => (
                <li key={endpoint.path}>
                  <code>GET {endpoint.path}</code>
                  <span>{endpoint.note}</span>
                </li>
              ))}
            </ul>
          </section>
        </aside>
      </div>

      <ConfirmDialog
        open={Boolean(pendingDelete)}
        title="Anahtarı iptal et"
        message={`"${pendingDelete?.name || ''}" anahtarı iptal edilecek. Bu anahtarı kullanan sistemler erişimini kaybeder.`}
        confirmLabel="İptal et"
        busy={busy}
        onConfirm={confirmDelete}
        onCancel={() => setPendingDelete(null)}
      />
    </div>
  );
}
