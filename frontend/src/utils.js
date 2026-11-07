const rtf = new Intl.RelativeTimeFormat('tr', { numeric: 'auto' });
const timeFormatter = new Intl.DateTimeFormat('tr-TR', {
  hour: '2-digit',
  minute: '2-digit',
});
const dateTimeFormatter = new Intl.DateTimeFormat('tr-TR', {
  day: '2-digit',
  month: 'short',
  hour: '2-digit',
  minute: '2-digit',
});
const dateFormatter = new Intl.DateTimeFormat('tr-TR', {
  day: '2-digit',
  month: 'short',
  year: 'numeric',
});

export function fmtMs(value) {
  if (value === null || value === undefined) return '—';
  return `${Math.round(value).toLocaleString('tr-TR')} ms`;
}

export function fmtPercent(value, digits = 2) {
  if (value === null || value === undefined) return '—';
  return `%${Number(value).toLocaleString('tr-TR', {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  })}`;
}

export function fmtNumber(value) {
  if (value === null || value === undefined) return '—';
  return Number(value).toLocaleString('tr-TR');
}

export function fmtTime(value) {
  if (!value) return '—';
  return timeFormatter.format(new Date(value));
}

export function fmtDateTime(value) {
  if (!value) return '—';
  return dateTimeFormatter.format(new Date(value));
}

export function fmtDate(value) {
  if (!value) return '—';
  return dateFormatter.format(new Date(value));
}

export function timeAgo(value) {
  if (!value) return '—';
  const diff = (new Date(value).getTime() - Date.now()) / 1000;
  const absolute = Math.abs(diff);
  if (absolute < 45) return 'az önce';
  const units = [
    ['year', 31_536_000],
    ['month', 2_592_000],
    ['day', 86_400],
    ['hour', 3_600],
    ['minute', 60],
  ];
  for (const [unit, seconds] of units) {
    if (absolute >= seconds) {
      return rtf.format(Math.round(diff / seconds), unit);
    }
  }
  return rtf.format(Math.round(diff), 'second');
}

export function fmtDuration(seconds) {
  if (seconds === null || seconds === undefined) return '—';
  const value = Math.max(0, Math.round(seconds));
  if (value < 60) return `${value} sn`;
  const minutes = Math.floor(value / 60);
  if (minutes < 60) return `${minutes} dk`;
  const hours = Math.floor(minutes / 60);
  const remainingMinutes = minutes % 60;
  if (hours < 24) {
    return remainingMinutes ? `${hours} sa ${remainingMinutes} dk` : `${hours} sa`;
  }
  const days = Math.floor(hours / 24);
  const remainingHours = hours % 24;
  return remainingHours ? `${days} gün ${remainingHours} sa` : `${days} gün`;
}

export function statusInfo(status, active = true) {
  if (!active) return { label: 'Duraklatıldı', tone: 'paused' };
  switch (status) {
    case 'up':
      return { label: 'Çalışıyor', tone: 'up' };
    case 'down':
      return { label: 'Çevrimdışı', tone: 'down' };
    case 'paused':
      return { label: 'Duraklatıldı', tone: 'paused' };
    default:
      return { label: 'Bekliyor', tone: 'unknown' };
  }
}

export function statusTone(code) {
  if (code === null || code === undefined) return 'net';
  if (code < 300) return 'ok';
  if (code < 400) return 'redirect';
  if (code < 500) return 'warn';
  return 'error';
}

export function uptimeTone(percent) {
  if (percent === null || percent === undefined) return 'empty';
  if (percent >= 99.9) return 'up';
  if (percent >= 95) return 'warn';
  return 'down';
}

export function intervalLabel(seconds) {
  if (!seconds) return '—';
  if (seconds < 60) return `${seconds} sn`;
  if (seconds % 3600 === 0) return `${seconds / 3600} sa`;
  return `${Math.round(seconds / 60)} dk`;
}

