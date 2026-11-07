import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { fmtDateTime, fmtMs, fmtPercent, fmtTime } from '../utils';

const COLORS = {
  green: '#3ce7b0',
  amber: '#f5c451',
  red: '#ff5d6c',
  net: '#c084fc',
  grid: 'rgba(148, 163, 184, 0.12)',
  tick: '#7f8ea8',
};

function normalize(series = []) {
  return series.map((point) => ({
    ...point,
    label: fmtTime(point.start),
    fullLabel: fmtDateTime(point.start),
    '2xx': point.classes?.['2xx'] ?? 0,
    '3xx': point.classes?.['3xx'] ?? 0,
    '4xx': point.classes?.['4xx'] ?? 0,
    '5xx': point.classes?.['5xx'] ?? 0,
    net: point.classes?.net ?? 0,
  }));
}

function tickInterval(length) {
  if (length <= 8) return 0;
  return Math.max(1, Math.ceil(length / 7) - 1);
}

function AreaTooltip({ active, payload }) {
  if (!active || !payload?.length) return null;
  const point = payload[0].payload;
  return (
    <div className="chart-tooltip">
      <span className="tooltip-title">{point.fullLabel}</span>
      <div className="tooltip-row">
        <span>Ortalama</span>
        <strong>{fmtMs(point.avg_ms)}</strong>
      </div>
      <div className="tooltip-row">
        <span>Uptime</span>
        <strong>{fmtPercent(point.uptime_percent)}</strong>
      </div>
      <div className="tooltip-row">
        <span>Kontrol</span>
        <strong>{point.checks ?? 0}</strong>
      </div>
      {(point.errors ?? 0) > 0 ? (
        <div className="tooltip-row danger">
          <span>Hata</span>
          <strong>{point.errors}</strong>
        </div>
      ) : null}
    </div>
  );
}

function ErrorTooltip({ active, payload }) {
  if (!active || !payload?.length) return null;
  const point = payload[0].payload;
  return (
    <div className="chart-tooltip">
      <span className="tooltip-title">{point.fullLabel}</span>
      <div className="tooltip-row">
        <span>4xx</span>
        <strong>{point['4xx']}</strong>
      </div>
      <div className="tooltip-row">
        <span>5xx</span>
        <strong>{point['5xx']}</strong>
      </div>
      <div className="tooltip-row">
        <span>Ağ hatası</span>
        <strong>{point.net}</strong>
      </div>
      <div className="tooltip-row total">
        <span>Toplam hata</span>
        <strong>{point.errors ?? 0}</strong>
      </div>
    </div>
  );
}

export function ResponseAreaChart({ series, height = 210 }) {
  const data = normalize(series);
  return (
    <div className="chart-box" style={{ height }}>
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={data} margin={{ top: 10, right: 6, left: 0, bottom: 0 }}>
          <defs>
            <linearGradient id="response-gradient" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={COLORS.green} stopOpacity={0.32} />
              <stop offset="100%" stopColor={COLORS.green} stopOpacity={0.01} />
            </linearGradient>
          </defs>
          <CartesianGrid stroke={COLORS.grid} strokeDasharray="3 7" vertical={false} />
          <XAxis
            dataKey="label"
            tickLine={false}
            axisLine={false}
            tick={{ fill: COLORS.tick, fontSize: 11 }}
            interval={tickInterval(data.length)}
            minTickGap={18}
          />
          <YAxis
            tickLine={false}
            axisLine={false}
            tick={{ fill: COLORS.tick, fontSize: 11 }}
            width={54}
            tickFormatter={(value) => `${Math.round(value)}ms`}
          />
          <Tooltip content={<AreaTooltip />} cursor={{ stroke: 'rgba(255,255,255,0.18)' }} />
          <Area
            type="monotone"
            dataKey="avg_ms"
            stroke={COLORS.green}
            strokeWidth={2.4}
            fill="url(#response-gradient)"
            connectNulls
            dot={false}
            activeDot={{ r: 4, fill: COLORS.green, stroke: '#0b1524', strokeWidth: 2 }}
          />
        </AreaChart>
      </ResponsiveContainer>
      {!data.some((point) => point.avg_ms !== null) ? (
        <span className="chart-empty-note">Bu aralıkta yanıt süresi verisi yok.</span>
      ) : null}
    </div>
  );
}

export function ErrorBarsChart({ series, height = 210 }) {
  const data = normalize(series);
  const hasErrors = data.some(
    (point) => point['4xx'] + point['5xx'] + point.net > 0,
  );
  return (
    <div className="chart-box" style={{ height }}>
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} margin={{ top: 10, right: 6, left: 0, bottom: 0 }}>
          <CartesianGrid stroke={COLORS.grid} strokeDasharray="3 7" vertical={false} />
          <XAxis
            dataKey="label"
            tickLine={false}
            axisLine={false}
            tick={{ fill: COLORS.tick, fontSize: 11 }}
            interval={tickInterval(data.length)}
            minTickGap={18}
          />
          <YAxis
            tickLine={false}
            axisLine={false}
            tick={{ fill: COLORS.tick, fontSize: 11 }}
            width={40}
            allowDecimals={false}
          />
          <Tooltip content={<ErrorTooltip />} cursor={{ fill: 'rgba(255,255,255,0.035)' }} />
          <Bar dataKey="4xx" stackId="errors" fill={COLORS.amber} maxBarSize={18} />
          <Bar dataKey="5xx" stackId="errors" fill={COLORS.red} maxBarSize={18} />
          <Bar
            dataKey="net"
            stackId="errors"
            fill={COLORS.net}
            maxBarSize={18}
            radius={[3, 3, 0, 0]}
          />
        </BarChart>
      </ResponsiveContainer>
      {!hasErrors ? (
        <span className="chart-empty-note">Bu aralıkta HTTP hatası yok</span>
      ) : null}
    </div>
  );
}
