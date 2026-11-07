import { useRef, useState } from 'react';
import { Download, Upload } from 'lucide-react';
import { api, downloadFile } from '../api';
import { useApp } from '../context/AppContext';

export default function TransferButtons({ onImported }) {
  const { isAdmin, notify } = useApp();
  const input = useRef(null);
  const [busy, setBusy] = useState(false);

  if (!isAdmin) return null;

  async function exportMonitors() {
    try {
      await downloadFile('/monitors/export', 'pulsewatch-monitors.json');
    } catch (err) {
      notify('error', 'Dışa aktarılamadı', err.message);
    }
  }

  async function importFile(event) {
    const file = event.target.files?.[0];
    event.target.value = '';
    if (!file) return;
    setBusy(true);
    try {
      const parsed = JSON.parse(await file.text());
      const monitors = Array.isArray(parsed) ? parsed : parsed.monitors;
      if (!Array.isArray(monitors)) throw new Error('Dosyada monitör listesi bulunamadı.');
      const result = await api.importMonitors(monitors);
      notify(
        'success',
        'İçe aktarma tamamlandı',
        `${result.created} eklendi, ${result.skipped} atlandı, ${result.errors.length} hatalı.`,
      );
      onImported?.();
    } catch (err) {
      notify('error', 'İçe aktarılamadı', err.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <button type="button" className="btn ghost" onClick={exportMonitors}>
        <Download size={15} /> Dışa aktar
      </button>
      <button type="button" className="btn ghost" disabled={busy} onClick={() => input.current?.click()}>
        <Upload size={15} /> {busy ? 'Aktarılıyor…' : 'İçe aktar'}
      </button>
      <input ref={input} type="file" accept="application/json,.json" hidden onChange={importFile} />
    </>
  );
}
