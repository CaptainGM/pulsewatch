from html import escape

STATUS_META = {
    "operational": ("#3ce7b0", "operational"),
    "up": ("#3ce7b0", "operational"),
    "degraded": ("#f5c451", "degraded"),
    "outage": ("#ff5d6c", "outage"),
    "down": ("#ff5d6c", "outage"),
    "maintenance": ("#a78bfa", "maintenance"),
    "paused": ("#94a3b8", "paused"),
    "unknown": ("#94a3b8", "unknown"),
    "empty": ("#94a3b8", "no monitors"),
}


def status_meta(status: str) -> tuple[str, str]:
    return STATUS_META.get(status, STATUS_META["unknown"])


def badge_svg(status: str, *, label: str = "PulseWatch", theme: str = "dark") -> str:
    color, text = status_meta(status)
    label = escape(label[:26])
    text = escape(text)
    if theme == "light":
        background = "#ffffff"
        border = "#d7e1ee"
        label_color = "#0f1b2d"
        muted = "#64748b"
    else:
        background = "#0b1524"
        border = "#223149"
        label_color = "#eaf1fb"
        muted = "#93a4bd"
    width = 208
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="36" viewBox="0 0 {width} 36" role="img" aria-label="{label}: {text}">
  <title>{label}: {text}</title>
  <rect x="0.5" y="0.5" width="{width - 1}" height="35" rx="8" fill="{background}" stroke="{border}"/>
  <circle cx="17" cy="18" r="4.5" fill="{color}">
    <animate attributeName="opacity" values="1;.55;1" dur="2.4s" repeatCount="indefinite"/>
  </circle>
  <text x="29" y="22.5" font-family="Inter, Segoe UI, sans-serif" font-size="11" font-weight="700" fill="{label_color}">{label}</text>
  <text x="{width - 14}" y="22.5" text-anchor="end" font-family="Inter, Segoe UI, sans-serif" font-size="10.5" font-weight="600" fill="{muted}">{text}</text>
</svg>"""
