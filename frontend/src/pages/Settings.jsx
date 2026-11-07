import { useEffect, useState } from 'react';
import { Copy, ExternalLink, Save } from 'lucide-react';
import { api } from '../api';
import { DashboardSkeleton, ErrorPanel } from '../components/States';
import { useApi, useDocumentTitle } from '../hooks';
import { useApp } from '../context/AppContext';

function toForm(site) {
  return {
    logo_url: site.logo_url || '',
    accent_color: site.accent_color,
    custom_domain: site.custom_domain || '',
    sla_target_percent: site.sla_target_percent,
  };
}

export default function Settings() {
  useDocumentTitle('Ayarlar');
  const { notify } = useApp();
  const site = useApi((signal) => api.site(signal), []);
  const [form, setForm] = useState(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (site.data) setForm(toForm(site.data));
  }, [site.data]);

  if (site.loading && !site.data) return <DashboardSkeleton />;
  if (site.error && !site.data) return <ErrorPanel error={site.error} onRetry={site.reload} />;
  if (!form) return null;

  function update(field, value) {
    setForm((current) => ({ ...current, [field]: value }));
  }

  async function handleSave(event) {
    event.preventDefault();
    setBusy(true);
    try {
      await api.saveSite({
        logo_url: form.logo_url.trim() || null,
        accent_color: form.accent_color,
        custom_domain: form.custom_domain.trim() || null,
        sla_target_percent: Number(form.sla_target_percent),
      });
      notify('success', 'Ayarlar kaydedildi');
      site.reload();
    } catch (err) {
      notify('error', 'Kaydedilemedi', err.message);
    } finally {
      setBusy(false);
    }
  }

  async function copy(text) {
    try {
      await navigator.clipboard.writeText(text);
      notify('success', 'Bağlantı kopyalandı');
    } catch {
      notify('error', 'Kopyalanamadı', text);
    }
  }

  const data = site.data;

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <p className="eyebrow">Yapılandırma</p>
          <h1 className="page-title">Ayarlar</h1>
          <p className="page-sub">Durum sayfasının görünümü, alan adı ve SLA hedefi.</p>
        </div>
      </div>

      <form className="settings-grid" onSubmit={handleSave}>
        <section className="panel">
          <header className="section-head">
            <div>
              <h2>Durum sayfası görünümü</h2>
              <p>Logo adresi ve vurgu rengi herkese açık sayfada kullanılır.</p>
            </div>
          </header>
          <div className="form-grid">
            <div className="field full">
              <label htmlFor="site-logo">Logo adresi</label>
              <input
                id="site-logo"
                type="url"
                placeholder="https://cdn.sirketim.com/logo.png"
                value={form.logo_url}
                onChange={(event) => update('logo_url', event.target.value)}
              />
            </div>
            <div className="field">
              <label htmlFor="site-accent">Vurgu rengi</label>
              <div className="color-field">
                <input
                  id="site-accent"
                  type="color"
                  value={form.accent_color}
                  onChange={(event) => update('accent_color', event.target.value)}
                />
                <input
                  aria-label="Vurgu rengi kodu"
                  value={form.accent_color}
                  maxLength={7}
                  onChange={(event) => update('accent_color', event.target.value)}
                />
              </div>
            </div>
            <div className="field">
              <label htmlFor="site-sla">SLA hedefi (%)</label>
              <input
                id="site-sla"
                type="number"
                min={90}
                max={100}
                step={0.01}
                value={form.sla_target_percent}
                onChange={(event) => update('sla_target_percent', event.target.value)}
              />
            </div>
          </div>
        </section>

        <section className="panel">
          <header className="section-head">
            <div>
              <h2>Alan adı</h2>
              <p>Alan adını yalnızca bu panelde tanımlarsınız; yönlendirmeyi sunucunuzdaki nginx veya Caddy yapar.</p>
            </div>
          </header>
          <div className="form-grid">
            <div className="field full">
              <label htmlFor="site-domain">Durum sayfası alan adı</label>
              <input
                id="site-domain"
                placeholder="durum.sirketim.com"
                value={form.custom_domain}
                onChange={(event) => update('custom_domain', event.target.value)}
              />
            </div>
          </div>
          <ul className="setup-steps">
            <li>Alan adınızın DNS kaydını bu sunucuya yönlendirin (CNAME veya A kaydı).</li>
            <li>Sunucuda HTTPS ile PulseWatch'a proxy kurun (Docker kurulumunda 8080 portu).</li>
            <li>Bağlantı artık <code>https://alan-adiniz/status</code> adresinde açılır.</li>
          </ul>
        </section>

        <section className="panel">
          <header className="section-head">
            <div>
              <h2>Bağlantılar</h2>
              <p>Durum sayfası ve kesinti akışı (RSS). Abone olmak için akışı bir RSS okuyucuya ekleyin.</p>
            </div>
          </header>
          <div className="link-list">
            <div className="link-row">
              <span>Durum sayfası</span>
              <code>{data.status_url}</code>
              <button type="button" className="icon-btn sm" aria-label="Durum sayfası bağlantısını kopyala" onClick={() => copy(data.status_url)}>
                <Copy size={14} />
              </button>
              <a className="icon-btn sm" href={data.status_url} target="_blank" rel="noreferrer" aria-label="Durum sayfasını aç">
                <ExternalLink size={14} />
              </a>
            </div>
            <div className="link-row">
              <span>Kesinti akışı (RSS)</span>
              <code>{data.feed_url}</code>
              <button type="button" className="icon-btn sm" aria-label="Akış bağlantısını kopyala" onClick={() => copy(data.feed_url)}>
                <Copy size={14} />
              </button>
            </div>
          </div>
          <p className="field-hint">E-posta aboneliği için SMTP ayarı gerekir; bu sürümde henüz yok.</p>
        </section>

        <div className="settings-actions">
          <button type="submit" className="btn primary" disabled={busy}>
            <Save size={16} /> {busy ? 'Kaydediliyor…' : 'Kaydet'}
          </button>
        </div>
      </form>
    </div>
  );
}
