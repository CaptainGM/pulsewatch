import { Link, NavLink, Outlet } from 'react-router-dom';
import {
  Activity,
  AlertTriangle,
  Bell,
  BellRing,
  CheckCircle2,
  Info,
  KeyRound,
  LayoutDashboard,
  LogOut,
  Plus,
  Settings,
  ShieldCheck,
  Users,
  Wrench,
  Send,
  Server,
  X,
} from 'lucide-react';
import Logo from './Logo';
import { clearToken, getToken } from '../api';
import { useApp } from '../context/AppContext';
import MonitorModal from './MonitorModal';
import NotificationDrawer from './NotificationDrawer';

function navClass({ isActive }) {
  return `nav-link${isActive ? ' active' : ''}`;
}

function ToastIcon({ type }) {
  if (type === 'error') return <AlertTriangle size={17} />;
  if (type === 'success') return <CheckCircle2 size={17} />;
  return <Info size={17} />;
}

function signOut() {
  clearToken();
  window.location.reload();
}

export default function Layout() {
  const {
    connected,
    unreadCount,
    openNotifications,
    openMonitorModal,
    modal,
    closeMonitorModal,
    handleMonitorSaved,
    toasts,
    dismissToast,
    isAdmin,
  } = useApp();

  return (
    <div className="app-shell">
      <div className="ambient" aria-hidden="true">
        <span className="glow glow-one" />
        <span className="glow glow-two" />
        <span className="dot-field" />
      </div>

      <a className="skip-link" href="#main-content">
        İçeriğe geç
      </a>

      <header className="topbar">
        <Link to="/" className="brand" aria-label="PulseWatch ana sayfa">
          <Logo />
          <span className="brand-copy">
            <strong>PulseWatch</strong>
            <small>API İzleme</small>
          </span>
        </Link>

        <nav className="main-nav" aria-label="Ana menü">
          <NavLink to="/" end className={navClass}>
            <LayoutDashboard size={16} /> Genel Bakış
          </NavLink>
          <NavLink to="/monitors" className={navClass}>
            <Server size={16} /> API&apos;ler
          </NavLink>
          <NavLink to="/incidents" className={navClass}>
            <AlertTriangle size={16} /> Olaylar
          </NavLink>
          <NavLink to="/sla" className={navClass}>
            <ShieldCheck size={16} /> SLA
          </NavLink>
          <NavLink to="/maintenance" className={navClass}>
            <Wrench size={16} /> Bakım
          </NavLink>
          {isAdmin ? (
            <>
              <NavLink to="/channels" className={navClass}>
                <Send size={16} /> Kanallar
              </NavLink>
              <NavLink to="/api-keys" className={navClass}>
                <KeyRound size={16} /> Anahtarlar
              </NavLink>
              <NavLink to="/users" className={navClass}>
                <Users size={16} /> Kullanıcılar
              </NavLink>
              <NavLink to="/settings" className={navClass}>
                <Settings size={16} /> Ayarlar
              </NavLink>
            </>
          ) : null}
        </nav>

        <div className="topbar-actions">
          <span className={`live-pill ${connected ? 'on' : 'off'}`} title={connected ? 'Canlı veri akışı bağlı' : 'Canlı akışa yeniden bağlanılıyor'}>
            <i className="live-dot" aria-hidden="true" />
            {connected ? 'Canlı' : 'Bağlanıyor'}
          </span>
          <button
            type="button"
            className="icon-btn bell-button"
            onClick={openNotifications}
            aria-label={`Bildirimler${unreadCount ? `, ${unreadCount} okunmamış` : ''}`}
          >
            {unreadCount > 0 ? <BellRing size={18} /> : <Bell size={18} />}
            {unreadCount > 0 ? (
              <span className="notification-badge">{unreadCount > 9 ? '9+' : unreadCount}</span>
            ) : null}
          </button>
          {getToken() ? (
            <button type="button" className="icon-btn" onClick={signOut} aria-label="Çıkış yap" title="Çıkış yap">
              <LogOut size={17} />
            </button>
          ) : null}
          <button type="button" className="btn primary" hidden={!isAdmin} onClick={() => openMonitorModal()}>
            <Plus size={16} /> API Ekle
          </button>
        </div>
      </header>

      <main id="main-content" className="page-shell">
        <Outlet />
      </main>

      <footer className="footer">
        <span className="footer-brand">
          <Activity size={14} /> PulseWatch <em>v2.0.0</em>
        </span>
        <span>FastAPI · PostgreSQL · Redis · React</span>
        <span className="footer-right">
          <a href="/status" target="_blank" rel="noreferrer">
            Herkese açık durum sayfası
          </a>
        </span>
      </footer>

      {modal.open ? (
        <MonitorModal
          monitor={modal.monitor}
          onClose={closeMonitorModal}
          onSaved={handleMonitorSaved}
        />
      ) : null}

      <NotificationDrawer />

      <div className="toast-stack" aria-live="polite" aria-atomic="false">
        {toasts.map((toast) => (
          <div key={toast.id} className={`toast ${toast.type}`} role="status">
            <span className={`toast-icon ${toast.type}`}>
              <ToastIcon type={toast.type} />
            </span>
            <span className="toast-copy">
              <strong>{toast.title}</strong>
              {toast.message ? <span>{toast.message}</span> : null}
            </span>
            <button
              type="button"
              className="toast-close"
              onClick={() => dismissToast(toast.id)}
              aria-label="Bildirimi kapat"
            >
              <X size={14} />
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}
