import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
} from 'react';
import { api } from '../api';
import { useLiveEvents } from '../hooks';

const AppContext = createContext(null);

export function useApp() {
  const context = useContext(AppContext);
  if (!context) throw new Error('useApp must be used inside AppProvider');
  return context;
}

export function AppProvider({ children }) {
  const [refreshKey, setRefreshKey] = useState(0);
  const [connected, setConnected] = useState(false);
  const [notifications, setNotifications] = useState([]);
  const [toasts, setToasts] = useState([]);
  const [modal, setModal] = useState({ open: false, monitor: null });
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [me, setMe] = useState(null);

  useEffect(() => {
    api.me().then(setMe).catch(() => setMe(null));
  }, [refreshKey]);

  const refreshTimer = useRef(null);
  const toastId = useRef(0);
  const toastTimers = useRef(new Map());

  const dismissToast = useCallback((id) => {
    setToasts((current) => current.filter((toast) => toast.id !== id));
    const timer = toastTimers.current.get(id);
    if (timer) {
      window.clearTimeout(timer);
      toastTimers.current.delete(id);
    }
  }, []);

  const notify = useCallback(
    (type, title, message = '') => {
      const id = ++toastId.current;
      setToasts((current) => [...current.slice(-3), { id, type, title, message }]);
      const timer = window.setTimeout(() => dismissToast(id), 6500);
      toastTimers.current.set(id, timer);
    },
    [dismissToast],
  );

  const refreshNow = useCallback(() => {
    if (refreshTimer.current) {
      window.clearTimeout(refreshTimer.current);
      refreshTimer.current = null;
    }
    setRefreshKey((value) => value + 1);
  }, []);

  const refresh = useCallback(() => {
    if (refreshTimer.current) window.clearTimeout(refreshTimer.current);
    refreshTimer.current = window.setTimeout(() => {
      refreshTimer.current = null;
      setRefreshKey((value) => value + 1);
    }, 700);
  }, []);

  const loadNotifications = useCallback(async () => {
    try {
      const data = await api.notifications();
      setNotifications(data);
    } catch {
    }
  }, []);

  useEffect(() => {
    loadNotifications();
  }, [loadNotifications, refreshKey]);

  useEffect(() => {
    const interval = window.setInterval(loadNotifications, 45_000);
    return () => window.clearInterval(interval);
  }, [loadNotifications]);

  useEffect(
    () => () => {
      if (refreshTimer.current) window.clearTimeout(refreshTimer.current);
      for (const timer of toastTimers.current.values()) window.clearTimeout(timer);
      toastTimers.current.clear();
    },
    [],
  );

  const openMonitorModal = useCallback((monitor = null) => {
    setModal({ open: true, monitor });
  }, []);

  const closeMonitorModal = useCallback(() => {
    setModal((current) => ({ ...current, open: false }));
  }, []);

  const handleMonitorSaved = useCallback(
    (saved, isEdit) => {
      setModal({ open: false, monitor: null });
      refreshNow();
      notify(
        'success',
        isEdit ? 'Monitör güncellendi' : 'Monitör eklendi',
        `${saved.name} ${isEdit ? 'güncellendi ve yeniden kontrol edilecek.' : 'izlemeye alındı.'}`,
      );
    },
    [notify, refreshNow],
  );

  const markNotificationRead = useCallback(async (id) => {
    setNotifications((current) =>
      current.map((item) => (item.id === id ? { ...item, read: true } : item)),
    );
    try {
      await api.markNotificationRead(id);
    } catch {
    }
  }, []);

  const markAllNotificationsRead = useCallback(async () => {
    setNotifications((current) => current.map((item) => ({ ...item, read: true })));
    try {
      await api.markAllNotificationsRead();
    } catch {
    }
  }, []);

  const handleLiveEvent = useCallback(
    (event) => {
      if (event.type !== 'check.completed') return;
      refresh();
      if (event.alert?.kind === 'down') {
        notify(
          'error',
          `${event.monitor_name} yanıt vermiyor`,
          event.error || `HTTP ${event.status_code ?? '—'} · ${Math.round(event.response_time_ms)} ms`,
        );
      } else if (event.alert?.kind === 'recovery') {
        notify(
          'success',
          `${event.monitor_name} tekrar çevrimiçi`,
          `HTTP ${event.status_code} · ${Math.round(event.response_time_ms)} ms`,
        );
      }
    },
    [notify, refresh],
  );

  const liveConnected = useLiveEvents(handleLiveEvent);
  useEffect(() => setConnected(liveConnected), [liveConnected]);

  const openNotifications = useCallback(() => {
    setDrawerOpen(true);
    loadNotifications();
  }, [loadNotifications]);

  const closeNotifications = useCallback(() => setDrawerOpen(false), []);

  const unreadCount = notifications.filter((item) => !item.read).length;

  const value = {
    me,
    isAdmin: me?.role === 'admin',
    refreshKey,
    refresh,
    refreshNow,
    connected,
    notifications,
    unreadCount,
    markNotificationRead,
    markAllNotificationsRead,
    loadNotifications,
    notify,
    toasts,
    dismissToast,
    modal,
    openMonitorModal,
    closeMonitorModal,
    handleMonitorSaved,
    drawerOpen,
    openNotifications,
    closeNotifications,
  };

  return <AppContext.Provider value={value}>{children}</AppContext.Provider>;
}
