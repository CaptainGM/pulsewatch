import { useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  AlertTriangle,
  BellOff,
  CheckCheck,
  CheckCircle2,
  FlaskConical,
  MailCheck,
  X,
} from 'lucide-react';
import { useApp } from '../context/AppContext';
import { timeAgo } from '../utils';

function iconFor(kind) {
  if (kind === 'down') return <AlertTriangle size={18} />;
  if (kind === 'recovery') return <CheckCircle2 size={18} />;
  return <FlaskConical size={18} />;
}

function toneFor(kind) {
  if (kind === 'down') return 'down';
  if (kind === 'recovery') return 'up';
  return 'info';
}

export default function NotificationDrawer() {
  const {
    drawerOpen,
    closeNotifications,
    notifications,
    unreadCount,
    markNotificationRead,
    markAllNotificationsRead,
  } = useApp();
  const navigate = useNavigate();

  useEffect(() => {
    if (!drawerOpen) return undefined;
    document.body.classList.add('modal-open');
    function onKey(event) {
      if (event.key === 'Escape') closeNotifications();
    }
    document.addEventListener('keydown', onKey);
    return () => {
      document.body.classList.remove('modal-open');
      document.removeEventListener('keydown', onKey);
    };
  }, [drawerOpen, closeNotifications]);

  if (!drawerOpen) return null;

  function openNotification(notification) {
    if (!notification.read) markNotificationRead(notification.id);
    if (notification.monitor_id) {
      closeNotifications();
      navigate(`/monitors/${notification.monitor_id}`);
    }
  }

  return (
    <div
      className="drawer-backdrop"
      onMouseDown={(event) => event.target === event.currentTarget && closeNotifications()}
    >
      <aside className="drawer" role="dialog" aria-modal="true" aria-labelledby="notifications-title">
        <header className="drawer-head">
          <div>
            <p className="eyebrow">Bildirim merkezi</p>
            <h2 id="notifications-title">
              Bildirimler {unreadCount > 0 ? <span className="count-badge">{unreadCount}</span> : null}
            </h2>
          </div>
          <button type="button" className="icon-btn" onClick={closeNotifications} aria-label="Kapat">
            <X size={18} />
          </button>
        </header>

        <div className="drawer-toolbar">
          <span>{notifications.length} bildirim</span>
          <button
            type="button"
            className="link-button"
            onClick={markAllNotificationsRead}
            disabled={unreadCount === 0}
          >
            <CheckCheck size={14} /> Tümünü okundu işaretle
          </button>
        </div>

        <div className="drawer-body">
          {notifications.length === 0 ? (
            <div className="drawer-empty">
              <BellOff size={28} />
              <h3>Henüz bildirim yok</h3>
              <p>Bir servis çöktüğünde veya geri geldiğinde burada görünecek.</p>
            </div>
          ) : (
            notifications.map((notification) => (
              <button
                type="button"
                key={notification.id}
                className={`notification-item ${notification.read ? 'read' : 'unread'}`}
                onClick={() => openNotification(notification)}
              >
                <span className={`notification-icon ${toneFor(notification.kind)}`}>
                  {iconFor(notification.kind)}
                </span>
                <span className="notification-copy">
                  <span className="notification-top">
                    <strong>{notification.title}</strong>
                    {!notification.read ? <i className="unread-dot" aria-label="Okunmadı" /> : null}
                  </span>
                  <span className="notification-message">{notification.message}</span>
                  <span className="notification-meta">
                    <span>{timeAgo(notification.created_at)}</span>
                    {notification.webhook_status === 'sent' ? (
                      <span className="webhook-state sent">
                        <MailCheck size={12} /> webhook gönderildi
                      </span>
                    ) : null}
                    {notification.webhook_status === 'failed' ? (
                      <span className="webhook-state failed" title={notification.webhook_error || ''}>
                        webhook başarısız
                      </span>
                    ) : null}
                  </span>
                </span>
              </button>
            ))
          )}
        </div>

        <footer className="drawer-foot">
          Sunucu tarafında oluşturulan olaylar. Webhook tanımlarsanız aynı mesaj Slack/Discord&apos;a da gider.
        </footer>
      </aside>
    </div>
  );
}
