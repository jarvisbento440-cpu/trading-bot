/* Krypto-Signale – Oberfläche */
(() => {
  const LC = window.LightweightCharts;
  const TZ = -new Date().getTimezoneOffset() * 60; // Charts zeigen Ortszeit
  const COLORS = {
    up: "#26a69a", down: "#ef5350", ema20: "#f2b84b", ema50: "#4f9cf9", ema200: "#c678dd",
    bb: "rgba(139,148,158,0.6)", entry: "#4f9cf9", stop: "#ef5350", target: "#26a69a",
    fib: { 0: "#8b949e", 0.236: "#e06c75", 0.382: "#f2b84b", 0.5: "#56b6c2", 0.618: "#98c379", 0.786: "#61afef", 1: "#8b949e" },
    res: "rgba(239,83,80,0.7)", sup: "rgba(38,166,154,0.7)",
  };

  const store = {
    get(k, d) { try { const v = localStorage.getItem(k); return v === null ? d : JSON.parse(v); } catch { return d; } },
    set(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch { /* egal */ } },
  };

  const state = {
    tf: store.get("tf", "4h"),
    layers: Object.assign({ sessions: true, light: true, signals: true, ema: true, fib: false, zones: true, bb: false, st: false }, store.get("layers", {})),
    strategies: [],
    stratOn: store.get("stratOn", null), // null = alle an
    sound: store.get("sound", true),
    lastSeenId: store.get("lastSeenId", null),
    alerts: new Set(store.get("alerts", [])),
    tiles: new Map(),
    data: new Map(),
    focus: null,
    timeframes: ["1h", "4h", "1d"],
    newIds: new Set(),
    regimeSeen: store.get("regimeSeen", {}),
    heatmap: store.get("heatmap", "off"),
    trendLight: null,
  };

  const $ = (s, el = document) => el.querySelector(s);
  const fmt = (p) => p == null ? "–" : p.toLocaleString("de-DE", {
    minimumFractionDigits: p >= 100 ? 2 : p >= 1 ? 4 : 5, maximumFractionDigits: p >= 100 ? 2 : p >= 1 ? 4 : 5 });
  const pct = (v) => v == null ? "" : (v >= 0 ? "+" : "") + v.toFixed(2).replace(".", ",") + " %";
  const names = {};
  const coinName = (s) => names[s] || s.split("/")[0];
  const sideDe = (s) => s === "long" ? "LONG" : "SHORT";

  async function getJSON(url) {
    const r = await fetch(url, { cache: "no-store" });
    if (!r.ok) throw new Error(r.status + " " + url);
    return r.json();
  }

  // ---------- Liquiditätszonen als Flächen ----------
  class ZonesPrimitive {
    constructor() {
      this.zones = []; this.big = false; this.chart = null; this.series = null; this.req = null;
      const self = this;
      this.view = { zOrder: () => "bottom", renderer: () => ({ draw: (t) => self.draw(t) }) };
    }
    attached(p) { this.chart = p.chart; this.series = p.series; this.req = p.requestUpdate; }
    detached() { this.chart = null; this.series = null; }
    paneViews() { return [this.view]; }
    updateAllViews() {}
    set(zones, big) { this.zones = zones || []; this.big = big; if (this.req) this.req(); }
    draw(target) {
      if (!this.chart || !this.series || !this.zones.length) return;
      const ts = this.chart.timeScale();
      target.useBitmapCoordinateSpace(({ context: ctx, bitmapSize, horizontalPixelRatio: hr, verticalPixelRatio: vr }) => {
        const W = bitmapSize.width;
        for (const z of this.zones) {
          const yTop = this.series.priceToCoordinate(z.top), yBot = this.series.priceToCoordinate(z.bottom);
          if (yTop == null || yBot == null) continue;
          const xs = ts.timeToCoordinate(z.start + TZ);
          const xe = z.end != null ? ts.timeToCoordinate(z.end + TZ) : null;
          const x1 = xs == null ? 0 : Math.max(0, xs * hr);
          const x2 = z.end != null && xe != null ? xe * hr : W;
          let y1 = Math.round(yTop * vr), y2 = Math.round(yBot * vr);
          if (y2 - y1 < 3 * vr) { const m = (y1 + y2) / 2; y1 = m - 1.5 * vr; y2 = m + 1.5 * vr; }
          const rgb = z.kind === "buy" ? "239,83,80" : "38,166,154";
          const strength = Math.min(1, 0.35 + 0.22 * (z.touches - 1));
          ctx.fillStyle = `rgba(${rgb},${z.swept ? 0.05 : 0.10 + 0.14 * strength})`;
          ctx.fillRect(x1, y1, x2 - x1, y2 - y1);
          ctx.strokeStyle = `rgba(${rgb},${z.swept ? 0.35 : 0.55 + 0.35 * strength})`;
          ctx.lineWidth = Math.max(1, hr);
          ctx.setLineDash(z.swept ? [4 * hr, 4 * hr] : []);
          ctx.beginPath();
          ctx.moveTo(x1, z.kind === "buy" ? y1 : y2); ctx.lineTo(x2, z.kind === "buy" ? y1 : y2);
          ctx.stroke();
          ctx.setLineDash([]);
          // Beschriftung
          const name = this.big
            ? (z.kind === "buy" ? "Buy-Side-Liquidität" : "Sell-Side-Liquidität") + (z.touches > 1 ? ` · ${z.touches}× (Equal ${z.kind === "buy" ? "Highs" : "Lows"})` : "") + (z.swept ? " · abgeholt" : "")
            : (z.kind === "buy" ? "BSL" : "SSL") + (z.touches > 1 ? ` ${z.touches}×` : "");
          ctx.font = `${(this.big ? 11 : 10) * vr}px "Segoe UI", system-ui, sans-serif`;
          ctx.fillStyle = `rgba(${rgb},${z.swept ? 0.5 : 0.95})`;
          ctx.textBaseline = z.kind === "buy" ? "bottom" : "top";
          const tw = ctx.measureText(name).width;
          const tx = Math.max(x1 + 4 * hr, Math.min(W - tw - 6 * hr, x2 - tw - 6 * hr));
          ctx.fillText(name, tx, z.kind === "buy" ? y1 - 2 * vr : y2 + 2 * vr);
        }
      });
    }
  }


  // ---------- Handelssitzungen (Börsenzeiten, Sommer-/Winterzeit automatisch) ----------
  const SESSIONS = [
    { key: "asia", name: "Asien", where: "Tokio / Hongkong", color: "199,120,221",
      open: ["Asia/Tokyo", 9, 0], close: ["Asia/Hong_Kong", 16, 0] },
    { key: "europe", name: "Europa", where: "London / Frankfurt", color: "79,156,249",
      open: ["Europe/London", 8, 0], close: ["Europe/Berlin", 17, 30] },
    { key: "usa", name: "USA", where: "New York (NYSE/Nasdaq)", color: "242,184,75",
      open: ["America/New_York", 9, 30], close: ["America/New_York", 16, 0] },
  ];
  const tzFmt = {};
  function tzParts(ms, tz) {
    tzFmt[tz] = tzFmt[tz] || new Intl.DateTimeFormat("en-US", { timeZone: tz, hourCycle: "h23",
      year: "numeric", month: "numeric", day: "numeric", hour: "numeric", minute: "numeric", weekday: "short" });
    const p = {};
    tzFmt[tz].formatToParts(new Date(ms)).forEach((x) => { p[x.type] = x.value; });
    return p;
  }
  // Ortszeit (Datum y-m-d, h:mi) in Zeitzone tz -> UTC-Millisekunden
  function zoned(y, m, d, h, mi, tz) {
    const guess = Date.UTC(y, m - 1, d, h, mi);
    let t = guess;
    for (let k = 0; k < 2; k++) {
      const p = tzParts(t, tz);
      const shown = Date.UTC(+p.year, +p.month - 1, +p.day, +p.hour, +p.minute);
      t += guess - shown;
    }
    return t;
  }
  // Alle Sitzungen (Mo–Fr in der Börsen-Zeitzone) zwischen fromMs und toMs
  function sessionsBetween(fromMs, toMs) {
    const out = [];
    for (let day = Math.floor(fromMs / 864e5) - 1; day <= Math.floor(toMs / 864e5) + 1; day++) {
      const dt = new Date(day * 864e5);
      const y = dt.getUTCFullYear(), m = dt.getUTCMonth() + 1, d = dt.getUTCDate();
      const wd = dt.getUTCDay();
      if (wd === 0 || wd === 6) continue; // Kalendertag der Börse: Sa/So zu (Feiertage nicht berücksichtigt)
      for (const s of SESSIONS) {
        const start = zoned(y, m, d, s.open[1], s.open[2], s.open[0]);
        const end = zoned(y, m, d, s.close[1], s.close[2], s.close[0]);
        if (end > fromMs && start < toMs) out.push({ ...s, start, end });
      }
    }
    return out;
  }
  const timeDe = (ms) => new Date(ms).toLocaleTimeString("de-DE", { hour: "2-digit", minute: "2-digit" });
  const dayDe = (ms) => {
    const a = new Date(ms), b = new Date();
    const diff = Math.round((new Date(a.getFullYear(), a.getMonth(), a.getDate()) - new Date(b.getFullYear(), b.getMonth(), b.getDate())) / 864e5);
    return diff === 0 ? "" : diff === 1 ? "morgen " : a.toLocaleDateString("de-DE", { weekday: "short" }) + " ";
  };
  const durDe = (ms) => { const m = Math.round(ms / 6e4); return m >= 60 ? `${Math.floor(m / 60)} h ${String(m % 60).padStart(2, "0")} min` : `${m} min`; };
  function sessionStatus(now = Date.now()) {
    const list = sessionsBetween(now - 864e5, now + 5 * 864e5);
    return SESSIONS.map((s) => {
      const mine = list.filter((x) => x.key === s.key);
      const cur = mine.find((x) => x.start <= now && now < x.end);
      const next = mine.filter((x) => x.start > now).sort((a, b) => a.start - b.start)[0];
      return { ...s, open: !!cur, cur, next };
    });
  }

  class SessionsPrimitive {
    constructor() {
      this.on = false; this.big = false; this.times = []; this.chart = null; this.series = null; this.req = null;
      const self = this;
      this.view = { zOrder: () => "bottom", renderer: () => ({ draw: (t) => self.draw(t) }) };
    }
    attached(p) { this.chart = p.chart; this.series = p.series; this.req = p.requestUpdate; }
    detached() { this.chart = null; }
    paneViews() { return [this.view]; }
    updateAllViews() {}
    set(times, on, big) {
      // times: echte UTC-Sekunden der Kerzen (ohne Ortszeit-Verschiebung)
      this.times = times; this.on = on; this.big = big;
      this.list = on && times.length > 1 ? sessionsBetween(times[0] * 1000, (times[times.length - 1] + (times[1] - times[0])) * 1000) : [];
      if (this.req) this.req();
    }
    // Uhrzeit -> logische Position (Kerze i liegt bei i, ihr Beginn bei i - 0,5)
    logical(t) {
      const T = this.times, n = T.length, dur = T[n - 1] - T[n - 2];
      if (t <= T[0]) return -0.5 - (T[0] - t) / dur;
      if (t >= T[n - 1]) return n - 1.5 + (t - T[n - 1]) / dur;
      let lo = 0, hi = n - 1;
      while (hi - lo > 1) { const mid = (lo + hi) >> 1; if (T[mid] <= t) lo = mid; else hi = mid; }
      const span = Math.min(T[hi] - T[lo], dur);
      return lo - 0.5 + Math.min(1, (t - T[lo]) / span);
    }
    draw(target) {
      if (!this.chart || !this.on || !this.list || !this.list.length) return;
      const ts = this.chart.timeScale();
      target.useBitmapCoordinateSpace(({ context: ctx, bitmapSize, horizontalPixelRatio: hr, verticalPixelRatio: vr }) => {
        const H = bitmapSize.height, row = (this.big ? 5 : 3) * vr;
        // logicalToCoordinate kann nur ganze Kerzen: dazwischen linear interpolieren
        const coord = (l) => {
          const i = Math.floor(l), c0 = ts.logicalToCoordinate(i), c1 = ts.logicalToCoordinate(i + 1);
          return c0 == null || c1 == null ? null : c0 + (l - i) * (c1 - c0);
        };
        this.list.forEach((s) => {
          const a = coord(this.logical(s.start / 1000));
          const b = coord(this.logical(s.end / 1000));
          if (a == null || b == null || b < 0) return;
          const x1 = Math.max(0, a * hr), x2 = Math.min(bitmapSize.width, b * hr);
          if (x2 <= x1) return;
          const r = SESSIONS.findIndex((x) => x.key === s.key);
          ctx.fillStyle = `rgba(${s.color},0.045)`;
          ctx.fillRect(x1, 0, x2 - x1, H);
          ctx.fillStyle = `rgba(${s.color},0.75)`;
          ctx.fillRect(x1, r * (row + vr), x2 - x1, row);
          if (this.big && x2 - x1 > 60 * hr) {
            ctx.font = `${10 * vr}px "Segoe UI", system-ui, sans-serif`;
            ctx.textBaseline = "top";
            ctx.fillStyle = `rgba(${s.color},0.9)`;
            ctx.fillText(`${s.name} ${timeDe(s.start)}`, x1 + 3 * hr, 3 * (row + vr) + 2 * vr + r * 12 * vr);
          }
        });
      });
    }
  }

  function renderSessionClock() {
    const box = $("#sessions");
    if (!box) return;
    box.innerHTML = sessionStatus().map((s) => {
      const txt = s.open ? `offen bis ${timeDe(s.cur.end)} (noch ${durDe(s.cur.end - Date.now())})`
        : s.next ? `öffnet ${dayDe(s.next.start)}${timeDe(s.next.start)}` : "zu";
      return `<span class="sess ${s.open ? "open" : ""}" style="--c:${s.color}" title="${s.where}: ${timeDe(s.next ? s.next.start : 0)}–${timeDe(s.next ? s.next.end : 0)} Uhr deine Zeit">
        <i></i><b>${s.name}</b> ${txt}</span>`;
    }).join("");
  }


  // ---------- Liquidations-Heatmap ----------
  const HM_STOPS = [[40, 20, 80], [59, 82, 139], [33, 145, 140], [94, 201, 98], [253, 231, 37]];
  function hmColor(v) {
    const t = v / 255 * (HM_STOPS.length - 1), i = Math.min(HM_STOPS.length - 2, Math.floor(t)), f = t - i;
    const a = HM_STOPS[i], b = HM_STOPS[i + 1];
    return [0, 1, 2].map((k) => Math.round(a[k] + (b[k] - a[k]) * f));
  }
  // Uhrzeit (UTC-Sekunden) -> x-Pixel, über die Kerzenzeiten des Charts
  function timeMapper(chart, T) {
    const ts = chart.timeScale(), n = T.length;
    if (n < 2) return () => null;
    const dur = T[n - 1] - T[n - 2];
    const logical = (t) => {
      if (t <= T[0]) return -0.5 - (T[0] - t) / dur;
      if (t >= T[n - 1]) return n - 1.5 + (t - T[n - 1]) / dur;
      let lo = 0, hi = n - 1;
      while (hi - lo > 1) { const mid = (lo + hi) >> 1; if (T[mid] <= t) lo = mid; else hi = mid; }
      return lo - 0.5 + Math.min(1, (t - T[lo]) / Math.min(T[hi] - T[lo], dur));
    };
    return (t) => {
      const l = logical(t), i = Math.floor(l), c0 = ts.logicalToCoordinate(i), c1 = ts.logicalToCoordinate(i + 1);
      return c0 == null || c1 == null ? null : c0 + (l - i) * (c1 - c0);
    };
  }

  class HeatmapPrimitive {
    constructor() {
      this.hm = null; this.img = null; this.times = []; this.chart = null; this.series = null; this.req = null;
      const self = this;
      this.view = { zOrder: () => "bottom", renderer: () => ({ draw: (t) => self.draw(t) }) };
    }
    attached(p) { this.chart = p.chart; this.series = p.series; this.req = p.requestUpdate; }
    detached() { this.chart = null; }
    paneViews() { return [this.view]; }
    updateAllViews() {}
    set(times, hm) {
      this.times = times;
      if (hm !== this.hm) {
        this.hm = hm; this.img = null;
        if (hm) {
          const raw = atob(hm.data), cols = hm.times.length, bins = hm.bins;
          const c = document.createElement("canvas"); c.width = cols; c.height = bins;
          const ctx = c.getContext("2d"), id = ctx.createImageData(cols, bins);
          for (let j = 0; j < cols; j++) {
            for (let b = 0; b < bins; b++) {
              const v = raw.charCodeAt(j * bins + b), o = ((bins - 1 - b) * cols + j) * 4;
              if (v < 20) continue;
              const [r, g, bl] = hmColor(v);
              id.data[o] = r; id.data[o + 1] = g; id.data[o + 2] = bl; id.data[o + 3] = Math.round(255 * (0.08 + 0.8 * v / 255));
            }
          }
          ctx.putImageData(id, 0, 0);
          this.img = c;
        }
      }
      if (this.req) this.req();
    }
    draw(target) {
      if (!this.chart || !this.series || !this.img || this.times.length < 2) return;
      const hm = this.hm, x = timeMapper(this.chart, this.times);
      const xa = x(hm.times[0]), xb = x(hm.times[hm.times.length - 1] + hm.step);
      const ya = this.series.priceToCoordinate(hm.pmax), yb = this.series.priceToCoordinate(hm.pmin);
      if (xa == null || xb == null || ya == null || yb == null) return;
      target.useBitmapCoordinateSpace(({ context: ctx, horizontalPixelRatio: hr, verticalPixelRatio: vr }) => {
        ctx.save();
        ctx.imageSmoothingEnabled = true;
        ctx.drawImage(this.img, xa * hr, ya * vr, (xb - xa) * hr, (yb - ya) * vr);
        ctx.restore();
      });
    }
  }


  // ---------- Eigene Zeichnungen: Long/Short-Position und Linien (wie TradingView) ----------
  const drawings = {}; // symbol -> [ {id, type: long|short|hline, t0, t1, entry, stop, target, price} ]
  const draw = { tool: null, sel: null, drag: null };
  const uid = () => Math.random().toString(36).slice(2, 10);
  async function loadDrawings() {
    try { Object.assign(drawings, await getJSON("/api/drawings")); } catch (e) { /* egal */ }
  }
  function saveDrawings(symbol) {
    fetch(`/api/drawings?symbol=${encodeURIComponent(symbol)}`, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(drawings[symbol] || []),
    }).catch(() => {});
  }
  // Ergebnis einer Position: erste Kerze ab Einstieg, die Stop oder Ziel berührt (Stop zuerst geprüft)
  function positionStatus(p, candles) {
    const long = p.type === "long";
    let reached = false;
    for (const k of candles) {
      if (k.time < p.t0) continue;
      if (!reached) { // Einstieg muss erst erreicht werden
        if (k.low <= p.entry && k.high >= p.entry) reached = true; else continue;
      }
      if (long ? k.low <= p.stop : k.high >= p.stop) return { state: "stop", time: k.time };
      if (long ? k.high >= p.target : k.low <= p.target) return { state: "target", time: k.time };
    }
    return { state: reached ? "open" : "waiting" };
  }
  const pctOf = (a, b) => ((a / b - 1) * 100);
  function positionText(p) {
    const risk = Math.abs(p.entry - p.stop), reward = Math.abs(p.target - p.entry);
    return { rr: risk ? reward / risk : 0, tp: pctOf(p.target, p.entry), sl: pctOf(p.stop, p.entry) };
  }
  function positionSize(p) {
    const risk = Math.abs(p.entry - p.stop);
    const money = paperOpt.capital * paperOpt.risk / 100;
    if (!risk || !money) return null;
    const qty = money / risk;
    return { qty, value: qty * p.entry, money };
  }

  class DrawPrimitive {
    constructor() {
      this.items = []; this.times = []; this.candles = []; this.big = false; this.chart = null; this.series = null; this.req = null;
      const self = this;
      this.view = { zOrder: () => "top", renderer: () => ({ draw: (t) => self.draw(t) }) };
    }
    attached(p) { this.chart = p.chart; this.series = p.series; this.req = p.requestUpdate; }
    detached() { this.chart = null; }
    paneViews() { return [this.view]; }
    updateAllViews() {}
    set(candles, items, big) {
      this.candles = candles; this.times = candles.map((k) => k.time); this.items = items || []; this.big = big;
      if (this.req) this.req();
    }
    geom(it) {
      const x = timeMapper(this.chart, this.times), y = (p) => this.series.priceToCoordinate(p);
      if (it.type === "hline") return { y: y(it.price) };
      return { x0: x(it.t0), x1: x(it.t1), yE: y(it.entry), yS: y(it.stop), yT: y(it.target) };
    }
    // Welcher Griff liegt unter der Maus? (Koordinaten relativ zum Chart)
    hit(mx, my) {
      if (!this.chart || this.times.length < 2) return null;
      for (let i = this.items.length - 1; i >= 0; i--) {
        const it = this.items[i], g = this.geom(it);
        if (it.type === "hline") { if (g.y != null && Math.abs(my - g.y) <= 6) return { it, part: "price" }; continue; }
        if (g.x0 == null || g.x1 == null) continue;
        if (mx < g.x0 - 6 || mx > g.x1 + 6) continue;
        if (Math.abs(my - g.yT) <= 6) return { it, part: "target" };
        if (Math.abs(my - g.yS) <= 6) return { it, part: "stop" };
        if (Math.abs(mx - g.x1) <= 6 && my >= Math.min(g.yT, g.yS) && my <= Math.max(g.yT, g.yS)) return { it, part: "end" };
        if (my >= Math.min(g.yT, g.yS) && my <= Math.max(g.yT, g.yS)) return { it, part: "move" };
      }
      return null;
    }
    draw(target) {
      if (!this.chart || !this.series || this.times.length < 2 || !this.items.length) return;
      target.useBitmapCoordinateSpace(({ context: ctx, bitmapSize, horizontalPixelRatio: hr, verticalPixelRatio: vr }) => {
        const W = bitmapSize.width;
        const label = (txt, x, y, color, bg, align = "left") => {
          ctx.font = `${(this.big ? 11 : 9) * vr}px "Segoe UI", system-ui, sans-serif`;
          const w = ctx.measureText(txt).width + 8 * hr, h = (this.big ? 16 : 13) * vr;
          const lx = align === "right" ? x - w : x;
          ctx.fillStyle = bg; ctx.fillRect(lx, y - h / 2, w, h);
          ctx.fillStyle = color; ctx.textBaseline = "middle"; ctx.fillText(txt, lx + 4 * hr, y);
        };
        for (const it of this.items) {
          const g = this.geom(it), selected = draw.sel === it.id;
          if (it.type === "hline") {
            if (g.y == null) continue;
            const y = g.y * vr;
            ctx.strokeStyle = it.color || "#f2b84b"; ctx.lineWidth = (selected ? 2 : 1.5) * hr;
            ctx.setLineDash([6 * hr, 4 * hr]); ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(W, y); ctx.stroke(); ctx.setLineDash([]);
            if (this.big) label(fmt(it.price), W - 4 * hr, y, "#0e1117", it.color || "#f2b84b", "right");
            continue;
          }
          if (g.x0 == null || g.x1 == null || g.yE == null) continue;
          const x0 = g.x0 * hr, x1 = g.x1 * hr, yE = g.yE * vr, yS = g.yS * vr, yT = g.yT * vr;
          const st = positionStatus(it, this.candles);
          const dim = st.state === "stop" || st.state === "target" ? 0.6 : 1;
          ctx.fillStyle = `rgba(38,166,154,${0.22 * dim})`; ctx.fillRect(x0, Math.min(yE, yT), x1 - x0, Math.abs(yT - yE));
          ctx.fillStyle = `rgba(239,83,80,${0.22 * dim})`; ctx.fillRect(x0, Math.min(yE, yS), x1 - x0, Math.abs(yS - yE));
          ctx.lineWidth = (selected ? 2 : 1) * hr;
          [[yT, "#26a69a"], [yS, "#ef5350"], [yE, "#e6edf3"]].forEach(([y, c]) => {
            ctx.strokeStyle = c; ctx.beginPath(); ctx.moveTo(x0, y); ctx.lineTo(x1, y); ctx.stroke();
          });
          if (selected) { // Griffe
            ctx.fillStyle = "#4f9cf9";
            [[x0, yT], [x0, yS], [x1, yE]].forEach(([x, y]) => { ctx.beginPath(); ctx.arc(x, y, 4 * hr, 0, 7); ctx.fill(); });
          }
          if (!this.big && !selected) continue;
          const t = positionText(it);
          const sgn = (v) => (v >= 0 ? "+" : "") + v.toFixed(2).replace(".", ",") + " %";
          label(`Ziel ${fmt(it.target)} (${sgn(t.tp)})`, x0 + 2 * hr, yT + (yT < yE ? -9 : 9) * vr, "#fff", "rgba(38,166,154,.9)");
          label(`Stop ${fmt(it.stop)} (${sgn(t.sl)})`, x0 + 2 * hr, yS + (yS > yE ? 9 : -9) * vr, "#fff", "rgba(239,83,80,.9)");
          const status = { stop: " · Stop getroffen", target: " · Ziel erreicht", open: " · läuft", waiting: " · wartet auf Einstieg" }[st.state];
          label(`${it.type === "long" ? "Long" : "Short"} ${fmt(it.entry)} · CRV 1:${t.rr.toFixed(1).replace(".", ",")}${status}`,
            x0 + 2 * hr, yE + (it.type === "long" ? 9 : -9) * vr, "#0e1117", "rgba(230,237,243,.92)");
        }
      });
    }
  }

  function setTool(t) {
    draw.tool = draw.tool === t ? null : t;
    document.querySelectorAll("#draw-tools [data-tool]").forEach((b) => b.classList.toggle("active", b.dataset.tool === draw.tool));
    $("#focus-chart").style.cursor = draw.tool ? "crosshair" : "";
  }
  function focusItems() { return state.focus ? (drawings[state.focus.symbol] = drawings[state.focus.symbol] || []) : []; }
  function redrawDrawings() {
    if (state.focus) { const d = state.data.get(state.focus.symbol + "|" + state.tf); if (d) renderFocus(d); }
    state.tiles.forEach((t, sym) => { const d = state.data.get(sym + "|" + state.tf); if (d) t.chart.draws.set(d.candles, drawings[sym], false); });
  }
  function deleteSelected() {
    if (!state.focus || !draw.sel) return;
    drawings[state.focus.symbol] = focusItems().filter((x) => x.id !== draw.sel);
    draw.sel = null; saveDrawings(state.focus.symbol); redrawDrawings();
  }

  function setupDrawing(c, el) {
    // Klick mit gewähltem Werkzeug: neue Zeichnung; ohne Werkzeug: auswählen
    c.chart.subscribeClick((param) => {
      if (!param.point || !state.focus) return;
      const data = state.data.get(state.focus.symbol + "|" + state.tf);
      if (!data || !data.candles.length) return;
      if (!draw.tool) {
        const h = c.draws.hit(param.point.x, param.point.y);
        draw.sel = h ? h.it.id : null; redrawDrawings(); return;
      }
      const price = c.candles.coordinateToPrice(param.point.y);
      if (price == null) return;
      const k = data.candles, step = k[k.length - 1].time - k[k.length - 2].time;
      const t0 = param.time != null ? param.time - TZ : k[k.length - 1].time;
      const items = focusItems();
      let it;
      if (draw.tool === "hline") it = { id: uid(), type: "hline", price };
      else {
        // Stop-Abstand: 1,5 × durchschnittliche Kerzenspanne der letzten 14 Kerzen, Ziel = 2 × Risiko
        const rec = k.slice(-14), atr = rec.reduce((s, x) => s + (x.high - x.low), 0) / rec.length;
        const risk = 1.5 * atr, long = draw.tool === "long";
        it = { id: uid(), type: draw.tool, t0, t1: t0 + 30 * step, entry: price,
          stop: long ? price - risk : price + risk, target: long ? price + 2 * risk : price - 2 * risk };
      }
      items.push(it); draw.sel = it.id; setTool(null);
      saveDrawings(state.focus.symbol); redrawDrawings();
    });
    // Ziehen mit der Maus
    el.addEventListener("mousedown", (e) => {
      if (draw.tool || e.button !== 0 || !state.focus) return;
      const r = el.getBoundingClientRect(), h = c.draws.hit(e.clientX - r.left, e.clientY - r.top);
      if (!h) return;
      e.preventDefault(); e.stopPropagation();
      draw.sel = h.it.id;
      const t2x = timeMapper(c.chart, c.draws.times);
      draw.drag = { ...h, y0: e.clientY - r.top, x0: e.clientX - r.left, orig: { ...h.it }, rect: r, t2x };
      c.chart.applyOptions({ handleScroll: false, handleScale: false });
      redrawDrawings();
    }, true);
    window.addEventListener("mousemove", (e) => {
      const d = draw.drag;
      if (!d) return;
      const y = e.clientY - d.rect.top, x = e.clientX - d.rect.left;
      const price = c.candles.coordinateToPrice(y), price0 = c.candles.coordinateToPrice(d.y0);
      if (price == null || price0 == null) return;
      const it = d.it, o = d.orig, dp = price - price0;
      const T = c.draws.times, step = T[T.length - 1] - T[T.length - 2];
      const ox0 = d.t2x(o.t0), pxPerSec = ox0 != null && d.t2x(o.t0 + step) != null ? (d.t2x(o.t0 + step) - ox0) / step : 0;
      const dt = pxPerSec ? Math.round((x - d.x0) / pxPerSec / step) * step : 0;
      if (d.part === "price") it.price = price;
      else if (d.part === "target") it.target = price;
      else if (d.part === "stop") it.stop = price;
      else if (d.part === "end") it.t1 = Math.max(o.t0 + step, o.t1 + dt);
      else if (d.part === "move") { it.entry = o.entry + dp; it.stop = o.stop + dp; it.target = o.target + dp; it.t0 = o.t0 + dt; it.t1 = o.t1 + dt; }
      // Stop und Ziel müssen auf der richtigen Seite bleiben
      if (it.type === "long") { it.stop = Math.min(it.stop, it.entry * 0.9999); it.target = Math.max(it.target, it.entry * 1.0001); }
      if (it.type === "short") { it.stop = Math.max(it.stop, it.entry * 1.0001); it.target = Math.min(it.target, it.entry * 0.9999); }
      c.draws.set(c.draws.candles, c.draws.items, true);
    });
    window.addEventListener("mouseup", () => {
      if (!draw.drag) return;
      draw.drag = null;
      c.chart.applyOptions({ handleScroll: true, handleScale: true });
      if (state.focus) saveDrawings(state.focus.symbol);
      redrawDrawings();
    });
    // Mauszeiger über Griffen ändern
    el.addEventListener("mousemove", (e) => {
      if (draw.drag || draw.tool) return;
      const r = el.getBoundingClientRect(), h = c.draws.hit(e.clientX - r.left, e.clientY - r.top);
      el.style.cursor = !h ? "" : h.part === "move" ? "move" : h.part === "end" ? "ew-resize" : "ns-resize";
    });
    // Werkzeugleiste links im Chart
    const bar = document.createElement("div");
    bar.id = "draw-tools"; bar.className = "draw-tools";
    bar.innerHTML = `<button data-tool="long" title="Long-Position einzeichnen (Klick in den Chart)">📈<span>Long</span></button>
      <button data-tool="short" title="Short-Position einzeichnen (Klick in den Chart)">📉<span>Short</span></button>
      <button data-tool="hline" title="Horizontale Linie (Klick in den Chart)">➖<span>Linie</span></button>
      <button data-act="del" title="Ausgewählte Zeichnung löschen (Entf)">🗑<span>Löschen</span></button>`;
    el.appendChild(bar);
    bar.addEventListener("mousedown", (e) => e.stopPropagation());
    bar.querySelectorAll("[data-tool]").forEach((b) => b.addEventListener("click", (e) => { e.stopPropagation(); setTool(b.dataset.tool); }));
    bar.querySelector("[data-act=del]").addEventListener("click", (e) => { e.stopPropagation(); deleteSelected(); });
  }

  const stratInfo = (key) => key === "regime" ? { name: "Trendampel", short: "A", color: "#26a69a" }
    : state.strategies.find((x) => x.key === key) || { name: key, short: "?", color: "#8b949e" };
  // Ohne eigene Auswahl: nur Strategien, die im Backtest nicht klar verloren haben
  const stratEnabled = (key) => {
    if (state.stratOn !== null) return state.stratOn.includes(key);
    const st = state.strategies.find((x) => x.key === key);
    return !st || !st.stats || st.stats.avg_r >= -0.03;
  };
  const pctDe = (x) => x == null ? "–" : Math.round(x * 100) + " %";
  const rDe = (x) => x == null ? "–" : (x >= 0 ? "+" : "") + x.toFixed(2).replace(".", ",") + " R";

  // ---------- Chart ----------
  function buildChart(el, big) {
    const chart = LC.createChart(el, {
      autoSize: true,
      layout: { background: { color: "transparent" }, textColor: "#8b949e", fontSize: big ? 12 : 11 },
      grid: { vertLines: { color: "rgba(42,49,60,0.5)" }, horzLines: { color: "rgba(42,49,60,0.5)" } },
      rightPriceScale: { borderColor: "#2a313c" },
      timeScale: { borderColor: "#2a313c", timeVisible: true, secondsVisible: false, rightOffset: 6 },
      crosshair: { mode: LC.CrosshairMode.Normal },
      handleScroll: big, handleScale: big,
      localization: { locale: "de-DE" },
    });
    const candles = chart.addCandlestickSeries({
      upColor: COLORS.up, downColor: COLORS.down, borderVisible: false,
      wickUpColor: COLORS.up, wickDownColor: COLORS.down, priceLineVisible: true,
    });
    const volume = chart.addHistogramSeries({ priceScaleId: "vol", priceFormat: { type: "volume" }, lastValueVisible: false, priceLineVisible: false });
    chart.priceScale("vol").applyOptions({ scaleMargins: { top: 0.82, bottom: 0 } });
    const line = (color, width = 1, style = 0) => chart.addLineSeries({
      color, lineWidth: width, lineStyle: style, priceLineVisible: false, lastValueVisible: false, crosshairMarkerVisible: false });
    return {
      chart, candles, volume,
      ema20: line(COLORS.ema20), ema50: line(COLORS.ema50), ema200: line(COLORS.ema200, 2),
      bbUp: line(COLORS.bb, 1, 2), bbLo: line(COLORS.bb, 1, 2), st: line("#c678dd", 2, 0), sma50: (() => { const l = line("#26a69a", 3, 0); l.applyOptions({ autoscaleInfoProvider: () => null }); return l; })(),
      priceLines: [], big, fitted: false, zones: (() => { const z = new ZonesPrimitive(); candles.attachPrimitive(z); return z; })(),
      sessions: (() => { const z = new SessionsPrimitive(); candles.attachPrimitive(z); return z; })(),
      heat: (() => { const z = new HeatmapPrimitive(); candles.attachPrimitive(z); return z; })(),
      draws: (() => { const z = new DrawPrimitive(); candles.attachPrimitive(z); return z; })(),
    };
  }

  const shift = (arr) => arr.map((p) => ({ ...p, time: p.time + TZ }));

  function priceFormatFor(data) {
    const last = data.candles.length ? data.candles[data.candles.length - 1].close : 1;
    const prec = last >= 100 ? 2 : last >= 1 ? 4 : 5;
    return { type: "price", precision: prec, minMove: Math.pow(10, -prec) };
  }

  function render(c, data) {
    if (!data || !data.candles || !data.candles.length) return;
    const L = state.layers;
    c.candles.applyOptions({ priceFormat: priceFormatFor(data) });
    c.candles.setData(shift(data.candles));
    c.volume.setData(shift(data.volume));
    c.ema20.setData(L.ema ? shift(data.ema20) : []);
    c.ema50.setData(L.ema ? shift(data.ema50) : []);
    c.ema200.setData(L.ema ? shift(data.ema200) : []);
    c.bbUp.setData(L.bb ? shift(data.bb_up) : []);
    c.bbLo.setData(L.bb ? shift(data.bb_lo) : []);
    c.st.setData(L.st && data.supertrend ? shift(data.supertrend) : []);
    c.sma50.setData(L.light && data.sma50 ? shift(data.sma50) : []);
    // Kacheln: nur die zwei nächsten offenen Zonen je Seite, Vollbild: alle
    const zones = !L.zones ? [] : c.big ? data.zones
      : ["buy", "sell"].flatMap((k) => data.zones.filter((z) => z.kind === k && !z.swept).slice(0, 2));
    c.zones.set(zones, c.big);
    c.sessions.set(data.candles.map((k) => k.time), L.sessions && data.tf !== "1d", c.big);
    const hm = state.heatmap !== "off" && data.heatmap && data.heatmap.range === state.heatmap ? data.heatmap : null;
    c.heat.set(data.candles.map((k) => k.time), hm);
    c.draws.set(data.candles, drawings[data.symbol], c.big);

    // Signal-Pfeile, Farbe je Strategie
    const markers = L.signals ? data.setups.filter((s) => stratEnabled(s.strategy)).map((s) => {
      const st = stratInfo(s.strategy);
      return {
        time: s.time + TZ,
        position: s.side === "long" ? "belowBar" : "aboveBar",
        color: st.color,
        shape: s.side === "long" ? "arrowUp" : "arrowDown",
        text: st.short + (s.strategy === "score" && c.big ? s.score : ""),
      };
    }) : [];
    // Mehrere Signale auf derselben Kerze: Lightweight Charts braucht sortierte Zeiten
    markers.sort((a, b) => a.time - b.time);
    c.candles.setMarkers(markers);

    // Linien neu zeichnen
    c.priceLines.forEach((pl) => c.candles.removePriceLine(pl));
    c.priceLines = [];
    const add = (price, color, title, style = 0, width = 1, label = c.big) => {
      if (price == null) return;
      c.priceLines.push(c.candles.createPriceLine({ price, color, title, lineStyle: style, lineWidth: width, axisLabelVisible: label }));
    };
    if (L.fib && data.fib) {
      data.fib.levels.forEach((l) => add(l.price, COLORS.fib[l.ratio] || COLORS.fib[0],
        "Fib " + (l.ratio * 100).toFixed(1).replace(".", ",") + "%", 2, 1));
    }
    const a = activeSignal(data);
    if (L.signals && a) {
      add(a.entry, COLORS.entry, "Einstieg", 0, 2, true);
      add(a.stop, COLORS.stop, "Stop", 0, 2, true);
      add(a.target1, COLORS.target, "Ziel 1", 0, 1, true);
      add(a.target2, COLORS.target, "Ziel 2", 0, 1, true);
    }
    if (!c.fitted) {
      const n = data.candles.length;
      let from = n - (c.big ? 220 : 120);
      if (hm) { // Heatmap-Zeitraum ganz zeigen
        const t0 = hm.times[0]; let i = data.candles.findIndex((k) => k.time >= t0);
        if (i >= 0) from = Math.min(from, i - 3);
      }
      c.chart.timeScale().setVisibleLogicalRange({ from, to: n + 5 });
      c.fitted = true;
    }
  }

  function activeSignal(data) {
    const list = (data.active_all || []).filter((s) => stratEnabled(s.strategy));
    return list.length ? list[list.length - 1] : null;
  }

  // ---------- Kacheln ----------
  function makeTile(coin) {
    const el = document.createElement("article");
    el.className = "tile";
    el.tabIndex = 0;
    el.innerHTML = `
      <div class="tile-head">
        <span class="tile-sym">${coinName(coin.symbol)}</span>${coin.extra ? `<span class="badge">${coin.kind || ""}</span>` : ""}
        <span class="tile-price"></span><span class="tile-chg"></span>
        <span class="badge tile-light" hidden></span><span class="badge tile-trend"></span><span class="badge tile-sig" hidden></span>
      </div>
      <div class="tile-chart"></div>
      <div class="tile-empty">Lade Daten…</div>
      ${coin.extra ? `<button class="tile-x" title="Kachel entfernen">✕</button>` : ""}`;
    $("#grid").insertBefore(el, picker.el);
    if (coin.extra) $(".tile-x", el).addEventListener("click", async (e) => {
      e.stopPropagation();
      await getJSON(`/api/watch/remove?symbol=${encodeURIComponent(coin.symbol)}`).catch(() => {});
      refreshState();
    });
    const tile = { el, symbol: coin.symbol, chart: buildChart($(".tile-chart", el), false) };
    const open = () => openFocus(coin.symbol);
    el.addEventListener("click", open);
    el.addEventListener("keydown", (e) => { if (e.key === "Enter") open(); });
    state.tiles.set(coin.symbol, tile);
    return tile;
  }

  function updateTileHead(tile, coin) {
    const el = tile.el;
    $(".tile-price", el).textContent = fmt(coin.price);
    const chg = $(".tile-chg", el);
    chg.textContent = pct(coin.change24h);
    chg.className = "tile-chg " + (coin.change24h >= 0 ? "up" : "down");
    const tr = $(".tile-trend", el);
    tr.textContent = { up: "Tagestrend ↑", down: "Tagestrend ↓", flat: "Seitwärts" }[coin.trend];
    tr.className = "badge tile-trend " + (coin.trend === "flat" ? "" : coin.trend);
    el.classList.toggle("alert", state.alerts.has(coin.symbol));
    const lt = $(".tile-light", el), r = coin.regime;
    lt.hidden = !r;
    if (r) {
      lt.textContent = r.state === "long" ? `🚦 Halten · ${Math.round(r.size * 100)} %` : "🚦 Raus";
      lt.className = "badge tile-light light-" + r.state;
      lt.title = lightText(r);
    }
  }

  const dateDe = (ms) => new Date(ms).toLocaleDateString("de-DE", { day: "2-digit", month: "2-digit", year: "numeric" });
  function lightText(r) {
    return (r.state === "long" ? "Trendampel grün: Tagesschluss über dem 50-Tage-Schnitt" : "Trendampel aus: Tagesschluss unter dem 50-Tage-Schnitt") +
      ` · seit ${dateDe(r.since)} (${pct(r.since_change)})`;
  }

  // Trendampel-Wechsel: Kachel blinkt wie bei einem Signal
  function checkRegime(coin) {
    const r = coin.regime;
    if (!r) return;
    const prev = state.regimeSeen[coin.symbol];
    state.regimeSeen[coin.symbol] = r.since;
    if (prev === undefined || prev === r.since) return;
    raiseAlert({ id: "r" + r.since, symbol: coin.symbol, side: r.state === "long" ? "long" : "short", timeframe: "1d",
      strategy: "regime", entry: r.close, stop: r.sma,
      title: `${coinName(coin.symbol)} Trendampel: ${r.state === "long" ? "HALTEN / KAUFEN" : "RAUS"}` });
  }

  function loadChartApply(symbol, data) {
    const tile = state.tiles.get(symbol);
    if (!tile) return;
    render(tile.chart, data);
    const sig = $(".tile-sig", tile.el);
    const act = activeSignal(data);
    if (act) {
      sig.hidden = false;
      sig.textContent = `${sideDe(act.side)} · ${stratInfo(act.strategy).name}`;
      sig.className = "badge tile-sig sig-" + act.side;
    } else sig.hidden = true;
  }

  async function loadChart(symbol) {
    const data = await getJSON(`/api/chart?symbol=${encodeURIComponent(symbol)}&tf=${state.tf}`);
    if (state.heatmap !== "off") {
      try { data.heatmap = await getJSON(`/api/heatmap?symbol=${encodeURIComponent(symbol)}&range=${state.heatmap}`); }
      catch (e) { data.heatmap = null; }
    }
    state.data.set(symbol + "|" + state.tf, data);
    const tile = state.tiles.get(symbol);
    if (tile) {
      $(".tile-empty", tile.el).hidden = !!data.candles.length;
      render(tile.chart, data);
      const sig = $(".tile-sig", tile.el);
      const act = activeSignal(data);
      if (act) {
        sig.hidden = false;
        sig.textContent = `${sideDe(act.side)} · ${stratInfo(act.strategy).name}`;
        sig.className = "badge tile-sig sig-" + act.side;
      } else sig.hidden = true;
    }
    if (state.focus && state.focus.symbol === symbol && state.focus.tf === state.tf) renderFocus(data);
    return data;
  }

  async function loadAllCharts() {
    for (const sym of state.tiles.keys()) {
      try { await loadChart(sym); } catch (e) { console.error(e); }
    }
  }

  // ---------- Alarm ----------
  let audioCtx;
  function beep() {
    if (!state.sound) return;
    try {
      audioCtx = audioCtx || new (window.AudioContext || window.webkitAudioContext)();
      [0, 0.25, 0.5].forEach((t, i) => {
        const o = audioCtx.createOscillator(), g = audioCtx.createGain();
        o.frequency.value = i === 2 ? 1320 : 880;
        g.gain.setValueAtTime(0.0001, audioCtx.currentTime + t);
        g.gain.exponentialRampToValueAtTime(0.25, audioCtx.currentTime + t + 0.02);
        g.gain.exponentialRampToValueAtTime(0.0001, audioCtx.currentTime + t + 0.2);
        o.connect(g).connect(audioCtx.destination);
        o.start(audioCtx.currentTime + t); o.stop(audioCtx.currentTime + t + 0.22);
      });
    } catch { /* kein Ton möglich */ }
  }

  let titleTimer = null;
  function flashTitle(on) {
    clearInterval(titleTimer);
    document.title = "Krypto-Signale";
    if (!on) return;
    let t = false;
    titleTimer = setInterval(() => { t = !t; document.title = t ? "🔔 NEUES SIGNAL" : "Krypto-Signale"; }, 800);
  }

  function raiseAlert(sig) {
    state.alerts.add(sig.symbol);
    store.set("alerts", [...state.alerts]);
    const tile = state.tiles.get(sig.symbol);
    if (tile) tile.el.classList.add("alert");
    beep();
    flashTitle(true);
    if ("Notification" in window && Notification.permission === "granted") {
      try {
        const n = new Notification(sig.title || `${coinName(sig.symbol)} ${sideDe(sig.side)} (${sig.timeframe})`, {
          body: `${stratInfo(sig.strategy || "score").name} · Einstieg ~${fmt(sig.entry)} · Stop ${fmt(sig.stop)}`, tag: "sig" + sig.id });
        n.onclick = () => { window.focus(); openFocus(sig.symbol); };
      } catch { /* egal */ }
    }
  }

  function clearAlert(symbol) {
    state.alerts.delete(symbol);
    store.set("alerts", [...state.alerts]);
    const tile = state.tiles.get(symbol);
    if (tile) tile.el.classList.remove("alert");
    if (!state.alerts.size) flashTitle(false);
  }

  // ---------- Status + Signal-Liste ----------
  function renderSignals(signals) {
    const ul = $("#signal-list");
    if (!signals.length) { ul.innerHTML = '<li class="muted">Noch keine Signale</li>'; return; }
    ul.innerHTML = "";
    signals.forEach((s) => {
      const li = document.createElement("li");
      if (state.newIds.has(s.id)) li.className = "new";
      const when = new Date(s.bar_ts).toLocaleString("de-DE", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });
      li.innerHTML = `
        <div class="row"><strong>${coinName(s.symbol)} <span class="${s.side === "long" ? "up" : "down"}">${sideDe(s.side)}</span></strong>
        <span class="muted">${s.timeframe} · ${when}</span></div>
        <div class="row"><span>Einstieg ${fmt(s.entry)}</span><span style="color:${stratInfo(s.strategy || "score").color}">${stratInfo(s.strategy || "score").name}</span></div>
        <div class="row muted"><span>Stop ${fmt(s.stop)}</span><span>Ziel ${fmt(s.target1)}</span></div>`;
      li.addEventListener("click", () => { state.tf = s.timeframe; saveTf(); openFocus(s.symbol); });
      ul.appendChild(li);
    });
  }

  async function refreshState() {
    let st;
    try { st = await getJSON("/api/state"); }
    catch (e) {
      const el = $("#status"); el.textContent = "Keine Verbindung zum Bot – läuft das Programm noch?"; el.className = "status err";
      return;
    }
    const el = $("#status");
    const t = st.last_update ? new Date(st.last_update * 1000).toLocaleTimeString("de-DE", { hour: "2-digit", minute: "2-digit" }) : null;
    el.textContent = st.status + (t ? ` · Stand ${t}` : "") + (st.error ? ` · ${st.error}` : "");
    el.className = "status " + (st.error ? "err" : st.status === "Live" ? "live" : "");

    if (st.timeframes && st.timeframes.join() !== state.timeframes.join()) { state.timeframes = st.timeframes; renderTfButtons(); }
    const firstStrat = !state.strategies.length;
    state.strategies = st.strategies || [];
    if (firstStrat || !$("#strat-panel").matches(":hover")) renderStrategyPanel();
    const btn = $("#bt-run");
    if (btn) { btn.disabled = !!st.backtest_running; btn.textContent = st.backtest_running ? "Backtest läuft… (einige Minuten)" : "Mit eigenen Daten neu berechnen"; }
    if (state.btWasRunning && !st.backtest_running && !$("#backtest").classList.contains("hidden")) openBacktest();
    state.btWasRunning = !!st.backtest_running;

    const live = new Set(st.coins.map((c) => c.symbol));
    state.tiles.forEach((t, sym) => { if (!live.has(sym)) { t.chart.chart.remove(); t.el.remove(); state.tiles.delete(sym); } });
    st.coins.forEach((coin) => {
      names[coin.symbol] = coin.name;
      const isNew = !state.tiles.has(coin.symbol);
      const tile = state.tiles.get(coin.symbol) || makeTile(coin);
      updateTileHead(tile, coin);
      checkRegime(coin);
      if (coin.loading) $(".tile-empty", tile.el).textContent = "Lade Kurs-Historie…";
      // neue Kachel oder Laden gerade fertig: Chart holen
      if ((isNew && state.started) || (tile.wasLoading && !coin.loading)) loadChart(coin.symbol).catch(console.error);
      tile.wasLoading = coin.loading;
    });
    store.set("regimeSeen", state.regimeSeen);
    state.trendLight = st.trend_light;
    state.coins = st.coins;

    const maxId = st.signals.reduce((m, s) => Math.max(m, s.id), 0);
    if (state.lastSeenId === null) state.lastSeenId = maxId; // erster Start: alte Signale nicht als neu melden
    const fresh = st.signals.filter((s) => s.id > state.lastSeenId && stratEnabled(s.strategy || "score")).reverse();
    fresh.forEach((s) => { state.newIds.add(s.id); raiseAlert(s); });
    if (fresh.length) { state.lastSeenId = maxId; await loadAllCharts(); }
    store.set("lastSeenId", state.lastSeenId);
    renderSignals(st.signals);
    return st;
  }

  // ---------- Vollbild ----------
  let focusChart = null;
  function openFocus(symbol) {
    clearAlert(symbol);
    state.focus = { symbol, tf: state.tf };
    const box = $("#focus");
    box.classList.remove("hidden");
    if (!focusChart) { focusChart = buildChart($("#focus-chart"), true); setupDrawing(focusChart, $("#focus-chart")); }
    draw.sel = null; setTool(null);
    focusChart.fitted = false;
    $("#focus-title").textContent = symbol.includes("/") ? symbol : `${coinName(symbol)} · ${symbol}`;
    renderFocusStrats();
    renderTfButtons();
    const cached = state.data.get(symbol + "|" + state.tf);
    if (cached) renderFocus(cached);
    loadChart(symbol).catch(console.error);
    if (document.fullscreenEnabled && !document.fullscreenElement) box.requestFullscreen().catch(() => {});
  }

  function closeFocus() {
    state.focus = null;
    $("#focus").classList.add("hidden");
    if (document.fullscreenElement) document.exitFullscreen().catch(() => {});
  }

  function renderFocus(data) {
    render(focusChart, data);
    const row = (k, v, cls = "") => `<tr><td>${k}</td><td class="${cls}">${v}</td></tr>`;
    const acts = (data.active_all || []).filter((s) => stratEnabled(s.strategy)).slice().reverse();
    let html = "";
    const coin = (state.coins || []).find((c) => c.symbol === data.symbol);
    const r = coin && coin.regime;
    if (r) {
      html += `<h3>Trendampel (Tagesfilter)</h3><div class="light-card ${r.state}">
        <div class="row"><span class="badge light-${r.state}">${r.state === "long" ? "🚦 HALTEN" : "🚦 RAUS"}</span>
        <span class="muted">seit ${dateDe(r.since)} · ${pct(r.since_change)}</span></div>
        <table>${row("Tagesschluss", fmt(r.close))}${row("50-Tage-Schnitt", fmt(r.sma))}${row("Abstand", pct(r.distance), r.distance >= 0 ? "up" : "down")}
        ${row("Empfohlener Anteil", r.state === "long" ? Math.round(r.size * 100) + " %" : "0 %")}</table>
        <p class="muted">Grün = Coin halten, grau = draußen bleiben (kein Short). Anteil = wie viel deines Budgets für diesen Coin, kleiner wenn der Kurs stark schwankt. Grüne/graue Linie im Chart = 50-Tage-Schnitt.</p></div>`;
    }
    const sel = (drawings[data.symbol] || []).find((x) => x.id === draw.sel && x.type !== "hline");
    if (sel) {
      const t = positionText(sel), ps = positionSize(sel), st = positionStatus(sel, data.candles);
      html += `<h3>Deine ${sel.type === "long" ? "Long" : "Short"}-Position</h3><div class="light-card ${sel.type === "long" ? "long" : ""}"><table>
        ${row("Einstieg", fmt(sel.entry))}${row("Ziel", `${fmt(sel.target)} (${pct(t.tp)})`, "up")}${row("Stop", `${fmt(sel.stop)} (${pct(t.sl)})`, "down")}
        ${row("Chance/Risiko", "1 : " + t.rr.toFixed(2).replace(".", ","))}
        ${row("Status", { stop: "Stop getroffen", target: "Ziel erreicht", open: "läuft", waiting: "wartet auf Einstieg" }[st.state])}
        ${ps ? row(`Positionsgröße bei ${String(paperOpt.risk).replace(".", ",")} % Risiko`, `${ps.qty.toLocaleString("de-DE", { maximumSignificantDigits: 4 })} ${coinName(data.symbol)}`) +
          row("Wert der Position", ps.value.toLocaleString("de-DE", { style: "currency", currency: "EUR", maximumFractionDigits: 0 })) +
          row("Verlust beim Stop", "−" + ps.money.toLocaleString("de-DE", { style: "currency", currency: "EUR", maximumFractionDigits: 0 }), "down") : ""}
        </table><p class="muted">Ziehen: obere/untere Linie = Ziel/Stop, Fläche = ganze Position verschieben, rechter Rand = Länge. Entf löscht. Kapital und Risiko stellst du im Papier-Test ein.</p></div>`;
    }
    const H = state.heatmap !== "off" && data.heatmap ? data.heatmap : null;
    if (H) {
      const z = H.zones.slice().sort((a, b) => b.price - a.price);
      html += `<h3>Liquidations-Heatmap (${H.range === "3d" ? "3 Tage" : "1 Woche"})</h3><table>` +
        z.map((q) => row(`${q.side === "above" ? "▲" : "▼"} ${fmt(q.price)}`,
          `${pct(q.distance)} · <span class="hm-bar"><i style="width:${Math.round(q.strength * 100)}%"></i></span>`, q.side === "above" ? "down" : "up")).join("") +
        `</table><p class="muted">Geschätzt aus Kursen und Volumen: wo gehebelte Trader (10x–100x) liquidiert würden. Gelb = viel Liquidität. Der Kurs läuft solche Zonen oft an, danach verschwinden sie (abgeholt). Kein echtes Orderbuch, nur ein Modell.</p>`;
    }
    html += `<h3>Börsenzeiten (deine Uhrzeit)</h3><table>` + sessionStatus().map((s) => {
      const x = s.open ? s.cur : s.next;
      return row(`<span class="sess-dot" style="--c:${s.color}" title="${s.where}"></span><span title="${s.where}">${s.name}</span>`,
        (x ? `${s.open ? "offen " : dayDe(x.start)}${timeDe(x.start)}–${timeDe(x.end)}` : "–"), s.open ? "up nowrap" : "nowrap");
    }).join("") + `</table><p class="muted">Asien = Tokio/Hongkong, Europa = London/Frankfurt, USA = New Yorker Börse. Farbige Streifen oben im Chart = Börsen offen. Die meiste Bewegung kommt oft zur US-Eröffnung und wenn Europa und USA gleichzeitig offen sind. US-Wirtschaftsdaten kommen meist eine Stunde vor der US-Eröffnung. Feiertage sind nicht berücksichtigt.</p>`;
    html += `<h3>Aktuelle Signale</h3>`;
    if (!acts.length) html += `<p class="muted">Gerade kein Signal der eingeschalteten Strategien.</p>`;
    acts.forEach((a, idx) => {
      const st = stratInfo(a.strategy);
      const rr = Math.abs(a.target1 - a.entry) / Math.abs(a.entry - a.stop);
      const hist = a.trades ? `Trefferquote im Backtest: <strong>${pctDe(a.winrate)}</strong> (${a.trades} Trades, Ø ${rDe(a.avg_r)})`
        : "Noch kein Backtest für diese Strategie";
      html += `<div class="sig-card" style="border-left-color:${st.color}">
        <div class="row"><span class="badge sig-${a.side}">${sideDe(a.side)}</span><strong style="color:${st.color}">${st.name}</strong></div>
        <div class="muted">${hist}</div>
        ${idx === 0 ? `<table>${row("Einstieg", fmt(a.entry))}${row("Stop", fmt(a.stop), "down")}${row("Ziel 1", fmt(a.target1), "up")}
        ${row("Ziel 2", fmt(a.target2), "up")}${row("Chance/Risiko", "1 : " + rr.toFixed(1).replace(".", ","))}</table>` :
        `<div class="muted">Einstieg ${fmt(a.entry)} · Stop ${fmt(a.stop)} · Ziel ${fmt(a.target1)}</div>`}
        <ul>${a.reasons.map((r) => `<li>${r}</li>`).join("")}</ul></div>`;
    });
    if (data.rsi != null) html += `<h3>Indikatoren</h3><table>${row("RSI (14)", data.rsi.toFixed(0))}${row("Tagestrend", { up: "aufwärts", down: "abwärts", flat: "seitwärts" }[data.trend] || "–")}</table>`;
    const zones = (data.zones || []).filter((z) => !z.swept);
    if (zones.length) {
      html += `<h3>Liquiditätszonen</h3><table>` + zones.sort((x, y) => y.top - x.top).map((z) =>
        row((z.kind === "buy" ? "Buy-Side" : "Sell-Side") + (z.touches > 1 ? ` (${z.touches}×)` : ""),
          fmt(z.bottom) + " – " + fmt(z.top), z.kind === "buy" ? "down" : "up")).join("") + "</table>" +
        `<p class="muted">Über Hochs liegen Stops von Short-Tradern (Buy-Side), unter Tiefs Stops von Long-Tradern (Sell-Side). Der Kurs läuft oft dorthin, um sie „abzuholen“. Mehrfach berührte Zonen (Equal Highs/Lows) sind stärker.</p>`;
    }
    if (data.fib) {
      html += `<h3>Fibonacci (${data.fib.direction === "up" ? "Aufwärtsimpuls" : "Abwärtsimpuls"})</h3><table>` +
        data.fib.levels.map((l) => row((l.ratio * 100).toFixed(1).replace(".", ",") + " %", fmt(l.price))).join("") + "</table>";
    }
    html += `<h3>Signale im Chart</h3><p class="muted">${data.setups.filter((s) => stratEnabled(s.strategy)).length} Signale. Buchstabe = Strategie (siehe „Strategien“). Mausrad = Zoom, Ziehen = Verschieben.</p>
      <p class="disclaimer">Trefferquoten stammen aus der Vergangenheit und sind keine Garantie. Immer mit Stop handeln, max. 1–2 % Risiko pro Trade.</p>`;
    $("#focus-info").innerHTML = html;
  }

  // ---------- Kachel „Markt hinzufügen“ ----------
  const picker = (() => {
    const el = document.createElement("article");
    el.className = "tile picker";
    el.innerHTML = `<div class="tile-head"><span class="tile-sym">＋ Markt hinzufügen</span></div>
      <div class="picker-body">
        <input type="search" class="picker-q" placeholder="Suchen: Gold, S&P 500, DAX, Nvidia, PEPE …" aria-label="Markt suchen">
        <ul class="picker-list"><li class="muted">Lade…</li></ul>
        <p class="muted">Krypto von der Börse, alles andere (Aktien, Indizes, Rohstoffe, Devisen) kostenlos von Yahoo Finance.</p>
      </div>`;
    $("#grid").appendChild(el);
    const q = $(".picker-q", el), list = $(".picker-list", el);
    let timer = null, seq = 0;
    async function run() {
      const my = ++seq;
      let res = [];
      try { res = await getJSON(`/api/search?q=${encodeURIComponent(q.value)}`); }
      catch (e) { list.innerHTML = '<li class="muted">Suche gerade nicht möglich</li>'; return; }
      if (my !== seq) return;
      if (!res.length) { list.innerHTML = '<li class="muted">Nichts gefunden</li>'; return; }
      list.innerHTML = "";
      res.forEach((r) => {
        const li = document.createElement("li");
        li.innerHTML = `<strong>${r.name}</strong> <span class="muted">${r.symbol}</span><span class="badge">${r.type || ""}</span>`;
        li.addEventListener("click", async () => {
          li.classList.add("busy");
          await getJSON(`/api/watch/add?symbol=${encodeURIComponent(r.symbol)}&name=${encodeURIComponent(r.name)}&type=${encodeURIComponent(r.type || "")}`).catch(() => {});
          q.value = ""; run();
          refreshState();
        });
        list.appendChild(li);
      });
    }
    q.addEventListener("input", () => { clearTimeout(timer); timer = setTimeout(run, 300); });
    el.addEventListener("click", (e) => e.stopPropagation());
    return { el, run };
  })();

  // ---------- Strategien im Vollbild ----------
  function renderFocusStrats() {
    const box = $("#focus-strats");
    box.innerHTML = "";
    state.strategies.forEach((st) => {
      const b = document.createElement("button");
      const on = stratEnabled(st.key);
      b.className = "chip" + (on ? " on" : "");
      b.style.setProperty("--c", st.color);
      b.title = st.description + (st.stats ? ` · Backtest: ${pctDe(st.stats.winrate)}, ${rDe(st.stats.avg_r)}` : "");
      b.innerHTML = `<span class="dot" style="background:${st.color}">${st.short}</span>${st.name}`;
      b.addEventListener("click", () => {
        const cur = state.strategies.filter((x) => stratEnabled(x.key)).map((x) => x.key);
        state.stratOn = on ? cur.filter((k) => k !== st.key) : [...cur, st.key];
        store.set("stratOn", state.stratOn);
        renderFocusStrats(); renderStrategyPanel(); rerenderAll();
        state.tiles.forEach((t, sym) => { const d = state.data.get(sym + "|" + state.tf); if (d) loadChartApply(sym, d); });
      });
      box.appendChild(b);
    });
  }

  // ---------- Strategien-Auswahl ----------
  function renderStrategyPanel() {
    const box = $("#strat-panel");
    box.innerHTML = state.strategies.map((st) => `
      <label class="strat-item" title="${st.description}">
        <input type="checkbox" data-strat="${st.key}" ${stratEnabled(st.key) ? "checked" : ""}>
        <span class="dot" style="background:${st.color}">${st.short}</span>
        <span class="strat-name">${st.name}</span>
        <span class="muted">${st.stats ? pctDe(st.stats.winrate) + " · " + rDe(st.stats.avg_r) : "kein Backtest"}</span>
      </label>`).join("") +
      `<p class="muted">Prozent = Trefferquote im Backtest, R = Ø Ergebnis pro Trade nach Gebühren. Nur angehakte Strategien werden gezeigt und lösen Alarm aus. Standard: nur Strategien, die im Backtest nicht klar verloren haben.</p>`;
    box.querySelectorAll("[data-strat]").forEach((cb) => cb.addEventListener("change", () => {
      state.stratOn = [...box.querySelectorAll("[data-strat]:checked")].map((x) => x.dataset.strat);
      store.set("stratOn", state.stratOn);
      if (state.focus) renderFocusStrats();
      rerenderAll();
      state.tiles.forEach((t, sym) => { const d = state.data.get(sym + "|" + state.tf); if (d) loadChartApply(sym, d); });
    }));
  }


  // ---------- Papier-Test ----------
  const paperOpt = Object.assign({ light: false, enabledOnly: true, capital: 1000, risk: 1 }, store.get("paperOpt", {}));
  function paperStats(ts) {
    const closed = ts.filter((t) => ["win", "loss", "timeout"].includes(t.status)).sort((a, b) => a.exit_ts - b.exit_ts);
    const open = ts.filter((t) => t.status === "open");
    let eq = 0, peak = 0, dd = 0;
    const curve = closed.map((t) => { eq += t.r; peak = Math.max(peak, eq); dd = Math.max(dd, peak - eq); return [t.exit_ts, eq]; });
    const wins = closed.filter((t) => t.status === "win").length;
    return { n: closed.length, wins, winrate: closed.length ? wins / closed.length : null, total: eq,
      avg: closed.length ? eq / closed.length : null, dd, open: open.length, openR: open.reduce((s, t) => s + (t.r || 0), 0), curve };
  }
  function curveSvg(curve) {
    if (curve.length < 2) return "";
    const W = 640, H = 120, xs = curve.map((p) => p[0]), ys = [0, ...curve.map((p) => p[1])];
    const x0 = xs[0], x1 = xs[xs.length - 1] || x0 + 1, y0 = Math.min(...ys), y1 = Math.max(...ys) || 1;
    const X = (x) => ((x - x0) / Math.max(1, x1 - x0)) * (W - 10) + 5, Y = (y) => H - 8 - ((y - y0) / Math.max(1e-9, y1 - y0)) * (H - 16);
    const d = curve.map((p, i) => `${i ? "L" : "M"}${X(p[0]).toFixed(1)},${Y(p[1]).toFixed(1)}`).join("");
    const last = curve[curve.length - 1][1];
    return `<svg class="paper-curve" viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" role="img" aria-label="Verlauf in R">
      <line x1="0" x2="${W}" y1="${Y(0)}" y2="${Y(0)}" stroke="var(--border)" stroke-dasharray="4 4"/>
      <path d="${d}" fill="none" stroke="${last >= 0 ? "var(--up)" : "var(--down)"}" stroke-width="2" vector-effect="non-scaling-stroke"/></svg>`;
  }
  async function openPaper() {
    const box = $("#paper"); box.classList.remove("hidden");
    const body = $("#paper-body");
    let r;
    try { r = await getJSON("/api/paper"); } catch (e) { body.innerHTML = '<p class="muted">Konnte den Papier-Test nicht laden.</p>'; return; }
    const draw = () => {
      let ts = r.trades.filter((t) => t.status !== "skipped" && t.status !== "waiting");
      if (paperOpt.enabledOnly) ts = ts.filter((t) => stratEnabled(t.strategy));
      if (paperOpt.light) ts = ts.filter((t) => t.follows_light);
      const s = paperStats(ts);
      const eur = (R) => (R * paperOpt.capital * paperOpt.risk / 100).toLocaleString("de-DE", { style: "currency", currency: "EUR", maximumFractionDigits: 0 });
      const cls = (x) => x == null ? "" : x >= 0 ? "up" : "down";
      const since = r.since ? new Date(r.since).toLocaleDateString("de-DE") : null;
      let html = `<div class="paper-opts">
        <label><input type="checkbox" id="po-light" ${paperOpt.light ? "checked" : ""}> Nur Trades, für die die Trendampel sprach</label>
        <label><input type="checkbox" id="po-en" ${paperOpt.enabledOnly ? "checked" : ""}> Nur eingeschaltete Strategien</label>
        <label>Kapital <input type="number" id="po-cap" min="0" step="100" value="${paperOpt.capital}"> €</label>
        <label>Risiko pro Trade <input type="number" id="po-risk" min="0.1" max="10" step="0.1" value="${paperOpt.risk}"> %</label></div>`;
      if (!r.trades.length) {
        html += `<p>Noch keine Signale aufgezeichnet. Ab jetzt wird jedes neue Signal automatisch als virtueller Trade mitgeschrieben, solange das Programm läuft. Nichts wird wirklich gekauft.</p>`;
        body.innerHTML = html; bindPaper(draw); return;
      }
      html += `<p class="muted">Aufgezeichnet seit ${since}. Gleiche Regeln wie im Backtest: Einstieg zur nächsten Kerze, Stop vor Ziel, 0,1 % Gebühr pro Seite. Nichts wird wirklich gehandelt.</p>
        <div class="paper-kpis">
          <div><span class="muted">Abgeschlossen</span><b>${s.n}</b></div>
          <div><span class="muted">Trefferquote</span><b>${s.winrate == null ? "–" : pctDe(s.winrate)}</b></div>
          <div><span class="muted">Ergebnis</span><b class="${cls(s.total)}">${rDe(s.total)}</b><span class="${cls(s.total)}">${eur(s.total)}</span></div>
          <div><span class="muted">Ø pro Trade</span><b class="${cls(s.avg)}">${s.avg == null ? "–" : rDe(s.avg)}</b></div>
          <div><span class="muted">Größter Rückgang</span><b>${s.n ? "−" + s.dd.toFixed(1).replace(".", ",") + " R" : "–"}</b><span>${s.n ? eur(-s.dd) : ""}</span></div>
          <div><span class="muted">Offen</span><b>${s.open}</b><span class="${cls(s.openR)}">${s.open ? rDe(s.openR) : ""}</span></div>
        </div>${curveSvg(s.curve)}
        <h3>Je Strategie</h3><div class="table-wrap"><table class="bt"><thead><tr><th>Strategie</th><th>Trades</th><th>Trefferquote</th><th>Ergebnis</th><th>Ø pro Trade</th><th>Offen</th></tr></thead><tbody>` +
        state.strategies.map((st) => {
          const m = paperStats(ts.filter((t) => t.strategy === st.key));
          if (!m.n && !m.open) return "";
          return `<tr><td><span class="dot" style="background:${st.color}">${st.short}</span> ${st.name}</td><td>${m.n}</td><td>${m.winrate == null ? "–" : pctDe(m.winrate)}</td>
            <td class="${cls(m.total)}">${rDe(m.total)}</td><td class="${cls(m.avg)}">${m.avg == null ? "–" : rDe(m.avg)}</td><td>${m.open}</td></tr>`;
        }).join("") + `</tbody></table></div>
        <h3>Trades</h3><div class="table-wrap"><table class="bt"><thead><tr><th>Signal</th><th class="l">Markt</th><th class="l">Strategie</th><th>Richtung</th><th>Ampel</th><th>Einstieg</th><th>Stop</th><th>Ziel</th><th>Status</th><th>Ergebnis</th></tr></thead><tbody>` +
        ts.slice(0, 200).map((t) => {
          const st = stratInfo(t.strategy);
          const status = { open: "offen", win: "Ziel erreicht", loss: "Stop", timeout: "Zeit abgelaufen" }[t.status] || t.status;
          const when = new Date(t.bar_ts).toLocaleString("de-DE", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });
          return `<tr><td>${when} · ${t.timeframe}</td><td class="l">${coinName(t.symbol)}</td><td class="l"><span class="dot" style="background:${st.color}">${st.short}</span> ${st.name}</td>
            <td class="${t.side === "long" ? "up" : "down"}">${sideDe(t.side)}</td><td>${t.light == null ? "–" : t.follows_light ? "✓" : "✗"}</td>
            <td>${fmt(t.entry)}</td><td>${fmt(t.stop)}</td><td>${fmt(t.target1)}</td><td>${status}</td>
            <td class="${cls(t.r)}">${t.r == null ? "–" : rDe(t.r)}</td></tr>`;
        }).join("") + `</tbody></table></div>
        <p class="muted">Ampel ✓ = Long bei grüner Trendampel bzw. Short bei ausgeschalteter Ampel. Erst nach einigen Wochen und mindestens 30–50 Trades sagt das Ergebnis etwas aus.</p>`;
      body.innerHTML = html; bindPaper(draw);
    };
    draw();
  }
  function bindPaper(draw) {
    const save = () => { store.set("paperOpt", paperOpt); draw(); };
    $("#po-light").addEventListener("change", (e) => { paperOpt.light = e.target.checked; save(); });
    $("#po-en").addEventListener("change", (e) => { paperOpt.enabledOnly = e.target.checked; save(); });
    $("#po-cap").addEventListener("change", (e) => { paperOpt.capital = Math.max(0, +e.target.value || 0); save(); });
    $("#po-risk").addEventListener("change", (e) => { paperOpt.risk = Math.min(10, Math.max(0.1, +e.target.value || 1)); save(); });
  }

  // ---------- Coin-Scanner ----------
  const scanOpt = Object.assign({ all: false }, store.get("scanOpt", {}));
  let scanTimer = null;
  async function openScanner() {
    $("#scan").classList.remove("hidden");
    const body = $("#scan-body");
    let r;
    try { r = await getJSON("/api/scanner"); } catch (e) { body.innerHTML = '<p class="muted">Konnte den Scanner nicht laden.</p>'; return; }
    const btn = $("#scan-run");
    btn.disabled = r.running || !r.online;
    btn.textContent = r.running ? "Scanne… (etwa eine Minute)" : "Jetzt neu scannen";
    clearTimeout(scanTimer);
    if (r.running) scanTimer = setTimeout(() => { if (!$("#scan").classList.contains("hidden")) openScanner(); }, 4000);
    const res = r.result;
    const num = (x, d = 0) => x == null ? "–" : x.toLocaleString("de-DE", { minimumFractionDigits: d, maximumFractionDigits: d });
    const sp = (x) => x == null ? "–" : (x > 0 ? "+" : "") + num(x) + " %";
    const cls = (x) => x == null ? "" : x >= 0 ? "up" : "down";
    const money = (x) => x == null ? "–" : x >= 1e9 ? num(x / 1e9, 1) + " Mrd." : num(x / 1e6, 0) + " Mio.";
    let html = "";
    if (r.error) html += `<p class="down">Letzter Scan fehlgeschlagen: ${r.error}</p>`;
    if (!res) {
      html += r.online ? `<p>Noch kein Scan vorhanden. Der erste läuft kurz nach dem Start automatisch, danach alle ${num(r.every_hours)} Stunden.</p>`
        : `<p>Noch kein Scan vorhanden (Offline-Modus).</p>`;
      body.innerHTML = html + scanHelp(r.test); return;
    }
    const when = new Date(res.created_at).toLocaleString("de-DE", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });
    const rows = res.coins.filter((c) => scanOpt.all || c.on);
    html += `<p class="muted">Stand ${when} · ${res.scanned} Coins mit dem höchsten 24h-Volumen auf ${res.exchange} (${res.quote}) · BTC 30 Tage ${sp(res.btc_ret30)}.
      Neu gescannt wird alle ${num(r.every_hours)} Stunden.</p>
      ${res.btc_on === false ? '<p class="down">⚠️ Die BTC-Trendampel steht auf RAUS. In dieser Lage haben im historischen Test auch Altcoins mit grüner Ampel meist verloren.</p>' : ""}
      <div class="paper-kpis">
        <div><span class="muted">Marktbreite</span><b>${num(res.breadth)} %</b><span>${res.green} von ${res.scanned} Coins mit grüner Trendampel</span></div>
        <div><span class="muted">BTC-Trendampel</span><b>${res.btc_on == null ? "–" : res.btc_on ? "🟢 grün" : "⚪ raus"}</b></div>
        <div><span class="muted">Platz 1 außerhalb deiner Liste</span><b>${(res.coins.find((c) => c.on && !c.watched) || {}).name || "–"}</b></div>
      </div>
      <div class="scan-opts"><label><input type="checkbox" id="so-all" ${scanOpt.all ? "checked" : ""}> Auch Coins mit roter Ampel zeigen</label></div>
      <div class="table-wrap"><table class="bt"><thead><tr><th>#</th><th class="l">Coin</th><th>Score</th><th>Kurs</th><th>24 h</th><th>7 Tage</th><th>30 T vs. BTC</th>
      <th>Volumen 24 h</th><th>Volumen-Schub</th><th>Ampel</th><th>Abstand 50-T.</th><th>Anteil</th><th></th></tr></thead><tbody>` +
      rows.map((c, i) => {
        const flags = (c.on && c.days_on != null && c.days_on <= 5 ? `<span class="flag new">${c.days_on ? "frisch grün" : "heute grün"}</span>` : "") +
          (c.high20 ? '<span class="flag">20-Tage-Hoch</span>' : "") + (c.focus ? '<span class="flag">Haupt-Coin</span>' : "");
        const light = c.on ? `🟢 seit ${c.days_on + 1} T.` : "⚪ raus";
        return `<tr class="${c.watched ? "mine" : ""}"><td>${i + 1}</td><td class="l"><strong>${c.name}</strong>${flags}</td><td>${c.score ?? "–"}</td>
          <td>${fmt(c.price)}</td><td class="${cls(c.change24h)}">${sp(c.change24h)}</td><td class="${cls(c.ret7)}">${sp(c.ret7)}</td>
          <td class="${cls(c.rs30)}">${sp(c.rs30)}</td><td>${money(c.volume24h)}</td><td>${c.vol_surge == null ? "–" : "×" + num(c.vol_surge, 1)}</td>
          <td>${light}</td><td>${sp(c.distance)}</td><td>${c.on ? num(c.size * 100) + " %" : "–"}</td>
          <td class="add">${c.watched ? '<span class="muted">im Chart</span>' : `<button class="btn" data-add="${c.symbol}">＋ Chart</button>`}</td></tr>`;
      }).join("") + `</tbody></table></div>`;
    body.innerHTML = html + scanHelp(r.test);
    $("#so-all").addEventListener("change", (e) => { scanOpt.all = e.target.checked; store.set("scanOpt", scanOpt); openScanner(); });
    body.querySelectorAll("[data-add]").forEach((b) => b.addEventListener("click", async () => {
      b.disabled = true; b.textContent = "…";
      const sym = b.dataset.add;
      await getJSON(`/api/watch/add?symbol=${encodeURIComponent(sym)}&name=${encodeURIComponent(sym.split("/")[0])}&type=Krypto`).catch(() => {});
      await refreshState();
      openScanner();
    }));
  }
  function scanHelp(t) {
    let html = `<h3>So liest du das</h3><ul>
      <li><strong>Trendampel grün</strong>: Tagesschluss über dem 50-Tage-Schnitt, dieselbe Regel wie bei deinen Haupt-Coins. Nur grüne Coins bekommen einen Score.</li>
      <li><strong>Score</strong> (0–100) vergleicht die grünen Coins untereinander: „Rücksetzer im Aufwärtstrend“, je zur Hälfte nah am 50-Tage-Schnitt und
        in den letzten 30 Tagen nicht schon stärker als BTC gelaufen. Coins, die schon davongelaufen waren, fielen im Test danach im Schnitt zurück. Der Score ist eine Rangliste, keine Trefferwahrscheinlichkeit.</li>
      <li><strong>Marktbreite</strong>: Anteil der Coins mit grüner Ampel. Über 50 % ist der Gesamtmarkt eher stark, unter 30 % eher schwach.</li>
      <li><strong>Anteil</strong>: wie viel deines Budgets für diesen Coin die Trendampel nach seiner Schwankung empfehlen würde.</li>
      <li><strong>Volumen-Schub</strong>: Handelsvolumen der letzten 3 Tage gegen die 30 davor. Nur zur Info, im Test kein Vorteil.</li>
      <li>Kleine Coins schwanken stark und können schnell abstürzen. Im Test 2022–2026 hat keine Altcoin-Auswahl BTC mit Trendampel geschlagen. Der Scanner ist eine Beobachtungsliste, kein Kaufsignal.</li></ul>`;
    if (t && t.summary) html += `<h3>Historischer Test</h3><p class="muted">${t.summary}</p>`;
    return html;
  }

  // ---------- Backtest-Ansicht ----------
  async function openBacktest() {
    const box = $("#backtest");
    box.classList.remove("hidden");
    const body = $("#backtest-body");
    body.innerHTML = '<p class="muted">Lade…</p>';
    let r = null;
    try { r = await getJSON("/api/backtest"); } catch (e) { /* egal */ }
    if (!r) {
      body.innerHTML = `<p>Noch kein Backtest vorhanden.</p>`;
      return;
    }
    const when = new Date(r.created_at).toLocaleDateString("de-DE");
    const rows = Object.entries(r.strategies).sort((a, b) => (b[1].all.avg_r ?? -99) - (a[1].all.avg_r ?? -99));
    const pf = (x) => x == null ? "–" : x.toFixed(2).replace(".", ",");
    const cell = (v) => v && v.trades ? `${pctDe(v.winrate)} <span class="muted">(${v.trades})</span>` : "–";
    let html = `<p class="muted">${r.days} Tage bis ${when} · Daten: ${r.exchange} · ${r.symbols.map(coinName).join(", ")} · ${r.timeframes.join(", ")}.
      Treffer = Ziel 1 vor dem Stop, Einstieg zum nächsten Eröffnungskurs, 0,1 % Gebühr pro Seite.</p>
      <div class="table-wrap"><table class="bt">
      <thead><tr><th>Strategie</th><th>Trades</th><th>Trefferquote</th><th>Ø pro Trade</th><th>Summe</th><th>Profit-Faktor</th><th>Max. Rückgang</th><th>Long</th><th>Short</th>
      ${r.timeframes.map((t) => `<th>${t}</th>`).join("")}</tr></thead><tbody>`;
    const tl = state.trendLight;
    if (tl) {
      let tlHtml = `<h3>Trendampel (Tagesfilter, 2021–2026)</h3><p class="muted">${tl.focus}, gleich gewichtet, Zeitraum jeweils 11.10.–10.10., 0,1 % Gebühr pro Seite. Regeln wurden nur auf 2021–2025 ausgewählt, 2025/26 ist das unberührte Prüfjahr.</p>
        <div class="table-wrap"><table class="bt"><thead><tr><th>Jahr</th><th>Trendampel</th><th>Kaufen &amp; Halten</th></tr></thead><tbody>` +
        tl.rows.map(([y, a, b]) => `<tr><td>${y}</td><td class="${a >= 0 ? "up" : "down"}">${a > 0 ? "+" : ""}${a} %</td><td class="${b >= 0 ? "up" : "down"}">${b > 0 ? "+" : ""}${b} %</td></tr>`).join("") +
        `<tr><td>Größter Rückgang</td><td>${tl.maxdd[0]} %</td><td>${tl.maxdd[1]} %</td></tr></tbody></table></div>
        <p class="muted">Die Trendampel verdient nicht in jedem Jahr mehr, aber sie halbiert die großen Abstürze. In starken Bullenjahren liegt Kaufen &amp; Halten vorne.</p>
        <h3>Einzel-Signale (1h/4h)</h3>`;
      html = tlHtml + html;
    }
    for (const [key, s] of rows) {
      const a = s.all, st = stratInfo(key);
      const good = a.avg_r != null && a.avg_r > 0;
      html += `<tr><td><span class="dot" style="background:${st.color}">${st.short}</span> ${s.name}</td>
        <td>${a.trades || 0}</td><td>${a.trades ? pctDe(a.winrate) : "–"}</td>
        <td class="${a.trades ? (good ? "up" : "down") : ""}">${a.trades ? rDe(a.avg_r) : "–"}</td>
        <td>${a.trades ? rDe(a.total_r) : "–"}</td><td>${pf(a.profit_factor)}</td><td>${a.trades ? "−" + a.max_dd_r.toFixed(1).replace(".", ",") + " R" : "–"}</td>
        <td>${cell(s.long)}</td><td>${cell(s.short)}</td>${r.timeframes.map((t) => `<td>${cell(s.by_tf[t])}</td>`).join("")}</tr>`;
    }
    html += `</tbody></table></div>`;
    const o = r.overall;
    if (o && o.trades) html += `<p><strong>Alle zusammen:</strong> ${o.trades} Trades, Trefferquote ${pctDe(o.winrate)}, Ø ${rDe(o.avg_r)} pro Trade.</p>`;
    html += `<h3>Je Coin</h3><div class="table-wrap"><table class="bt"><thead><tr><th>Strategie</th>${r.symbols.map((x) => `<th>${coinName(x)}</th>`).join("")}</tr></thead><tbody>` +
      rows.map(([key, s]) => `<tr><td>${s.name}</td>${r.symbols.map((x) => `<td>${cell(s.by_symbol[x])}</td>`).join("")}</tr>`).join("") + `</tbody></table></div>`;
    html += `<h3>Score-Modell: Trefferquote je Score</h3><table class="bt"><thead><tr><th>Score</th><th>Trades</th><th>Trefferquote</th><th>Ø pro Trade</th></tr></thead><tbody>` +
      r.score_buckets.map((b) => `<tr><td>${b.from}–${b.to}</td><td>${b.trades || 0}</td><td>${b.trades ? pctDe(b.winrate) : "–"}</td><td>${b.trades ? rDe(b.avg_r) : "–"}</td></tr>`).join("") + `</tbody></table>
      <h3>So liest du das</h3><ul>
      <li><strong>R</strong> = dein Risiko pro Trade (Abstand Einstieg–Stop). +0,30 R heißt: im Schnitt 30 % des Risikos gewonnen.</li>
      <li><strong>Ø pro Trade über 0</strong> heißt: nach Gebühren profitabel. Eine hohe Trefferquote allein reicht nicht, wenn die Gewinne klein sind.</li>
      <li><strong>Profit-Faktor</strong> = Gewinne / Verluste. Über 1,2 ist brauchbar, unter 1 verliert Geld.</li>
      <li>Strategien mit wenigen Trades (unter ~30) sind statistisch wenig aussagekräftig.</li>
      <li>Vergangene Ergebnisse sind keine Garantie für die Zukunft.</li></ul>`;
    body.innerHTML = html;
  }

  async function runBacktest() {
    try { await getJSON("/api/backtest/run?days=365"); } catch (e) { /* egal */ }
    $("#bt-run").disabled = true;
    $("#bt-run").textContent = "Backtest läuft… (einige Minuten)";
  }

  // ---------- Bedienung ----------
  function saveTf() { store.set("tf", state.tf); }

  function renderHeatButtons() {
    const box = $("#hm-buttons");
    const labels = { off: "Aus", "3d": "3 Tage", "1w": "1 Woche" };
    box.innerHTML = `<span class="muted">Heatmap</span>`;
    Object.entries(labels).forEach(([k, label]) => {
      const b = document.createElement("button");
      b.className = "btn" + (k === state.heatmap ? " active" : "");
      b.textContent = label;
      b.addEventListener("click", (e) => {
        e.stopPropagation();
        state.heatmap = k; store.set("heatmap", k); renderHeatButtons();
        state.tiles.forEach((t) => { t.chart.fitted = false; });
        if (focusChart) focusChart.fitted = false;
        loadAllCharts();
        if (state.focus) loadChart(state.focus.symbol).catch(console.error);
      });
      box.appendChild(b);
    });
  }

  function renderTfButtons() {
    const labels = { "15m": "15 Min", "1h": "1 Std", "4h": "4 Std", "1d": "1 Tag" };
    [$("#tf-buttons"), $("#focus-tf")].forEach((box) => {
      box.innerHTML = "";
      state.timeframes.forEach((tf) => {
        const b = document.createElement("button");
        b.className = "btn" + (tf === state.tf ? " active" : "");
        b.textContent = labels[tf] || tf;
        b.addEventListener("click", (e) => {
          e.stopPropagation();
          state.tf = tf; saveTf(); renderTfButtons();
          state.tiles.forEach((t) => { t.chart.fitted = false; });
          if (focusChart) focusChart.fitted = false;
          if (state.focus) state.focus.tf = tf;
          loadAllCharts();
        });
        box.appendChild(b);
      });
    });
  }

  function rerenderAll() {
    state.tiles.forEach((t, sym) => { const d = state.data.get(sym + "|" + state.tf); if (d) render(t.chart, d); });
    if (state.focus) { const d = state.data.get(state.focus.symbol + "|" + state.tf); if (d) renderFocus(d); }
  }

  document.querySelectorAll("[data-layer]").forEach((cb) => {
    cb.checked = !!state.layers[cb.dataset.layer];
    cb.addEventListener("change", () => { state.layers[cb.dataset.layer] = cb.checked; store.set("layers", state.layers); rerenderAll(); });
  });

  const soundBtn = $("#sound-btn");
  const paintSound = () => { soundBtn.textContent = state.sound ? "🔔 Ton an" : "🔕 Ton aus"; };
  paintSound();
  soundBtn.addEventListener("click", () => {
    state.sound = !state.sound; store.set("sound", state.sound); paintSound();
    if (state.sound) beep();
    if ("Notification" in window && Notification.permission === "default") Notification.requestPermission();
  });

  $("#focus-close").addEventListener("click", closeFocus);
  $("#bt-open").addEventListener("click", openBacktest);
  $("#paper-open").addEventListener("click", openPaper);
  $("#paper-close").addEventListener("click", () => $("#paper").classList.add("hidden"));
  $("#scan-open").addEventListener("click", openScanner);
  $("#scan-close").addEventListener("click", () => $("#scan").classList.add("hidden"));
  $("#scan-run").addEventListener("click", async () => { await getJSON("/api/scanner/run").catch(() => {}); openScanner(); });
  $("#bt-close").addEventListener("click", () => $("#backtest").classList.add("hidden"));
  $("#bt-run").addEventListener("click", runBacktest);
  $("#strat-btn").addEventListener("click", (e) => { e.stopPropagation(); $("#strat-panel").classList.toggle("hidden"); });
  document.addEventListener("click", (e) => { if (!e.target.closest("#strat-panel") && !e.target.closest("#strat-btn")) $("#strat-panel").classList.add("hidden"); });
  document.addEventListener("keydown", (e) => {
    if ((e.key === "Delete" || e.key === "Backspace") && state.focus && draw.sel && !e.target.closest("input")) { deleteSelected(); return; }
    if (e.key !== "Escape") return;
    if (state.focus && (draw.tool || draw.sel)) { setTool(null); draw.sel = null; redrawDrawings(); return; }
    if (!$("#scan").classList.contains("hidden")) $("#scan").classList.add("hidden");
    else if (!$("#paper").classList.contains("hidden")) $("#paper").classList.add("hidden");
    else if (!$("#backtest").classList.contains("hidden")) $("#backtest").classList.add("hidden");
    else if (state.focus) closeFocus();
  });
  document.addEventListener("fullscreenchange", () => { if (!document.fullscreenElement && state.focus) closeFocus(); });
  // Erste Interaktion: Ton- und Benachrichtigungs-Freigabe holen
  document.addEventListener("click", () => {
    if ("Notification" in window && Notification.permission === "default") Notification.requestPermission();
  }, { once: true });

  // ---------- Start ----------
  (async () => {
    renderTfButtons();
    renderHeatButtons();
    await loadDrawings();
    await refreshState();
    await loadAllCharts();
    state.started = true;
    picker.run();
    setInterval(refreshState, 15000);
    setInterval(loadAllCharts, 60000);
    renderSessionClock();
    setInterval(renderSessionClock, 30000);
  })();
})();
