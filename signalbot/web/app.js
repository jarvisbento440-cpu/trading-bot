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
    layers: Object.assign({ signals: true, ema: true, fib: false, zones: true, bb: false, st: false }, store.get("layers", {})),
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
  };

  const $ = (s, el = document) => el.querySelector(s);
  const fmt = (p) => p == null ? "–" : p.toLocaleString("de-DE", {
    minimumFractionDigits: p >= 100 ? 2 : p >= 1 ? 4 : 5, maximumFractionDigits: p >= 100 ? 2 : p >= 1 ? 4 : 5 });
  const pct = (v) => v == null ? "" : (v >= 0 ? "+" : "") + v.toFixed(2).replace(".", ",") + " %";
  const coinName = (s) => s.split("/")[0];
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

  const stratInfo = (key) => state.strategies.find((x) => x.key === key) || { name: key, short: "?", color: "#8b949e" };
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
      bbUp: line(COLORS.bb, 1, 2), bbLo: line(COLORS.bb, 1, 2), st: line("#c678dd", 2, 0),
      priceLines: [], big, fitted: false, zones: (() => { const z = new ZonesPrimitive(); candles.attachPrimitive(z); return z; })(),
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
    // Kacheln: nur die zwei nächsten offenen Zonen je Seite, Vollbild: alle
    const zones = !L.zones ? [] : c.big ? data.zones
      : ["buy", "sell"].flatMap((k) => data.zones.filter((z) => z.kind === k && !z.swept).slice(0, 2));
    c.zones.set(zones, c.big);

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
      c.chart.timeScale().setVisibleLogicalRange({ from: n - (c.big ? 220 : 120), to: n + 5 });
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
        <span class="tile-sym">${coinName(coin.symbol)}</span>
        <span class="tile-price"></span><span class="tile-chg"></span>
        <span class="badge tile-trend"></span><span class="badge tile-sig" hidden></span>
      </div>
      <div class="tile-chart"></div>
      <div class="tile-empty">Lade Daten…</div>`;
    $("#grid").appendChild(el);
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
        const n = new Notification(`${coinName(sig.symbol)} ${sideDe(sig.side)} (${sig.timeframe})`, {
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

    st.coins.forEach((coin) => {
      const tile = state.tiles.get(coin.symbol) || makeTile(coin);
      updateTileHead(tile, coin);
    });

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
    if (!focusChart) focusChart = buildChart($("#focus-chart"), true);
    focusChart.fitted = false;
    $("#focus-title").textContent = symbol;
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
    let html = `<h3>Aktuelle Signale</h3>`;
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
      rerenderAll();
      state.tiles.forEach((t, sym) => { const d = state.data.get(sym + "|" + state.tf); if (d) loadChartApply(sym, d); });
    }));
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
  $("#bt-close").addEventListener("click", () => $("#backtest").classList.add("hidden"));
  $("#bt-run").addEventListener("click", runBacktest);
  $("#strat-btn").addEventListener("click", (e) => { e.stopPropagation(); $("#strat-panel").classList.toggle("hidden"); });
  document.addEventListener("click", (e) => { if (!e.target.closest("#strat-panel") && !e.target.closest("#strat-btn")) $("#strat-panel").classList.add("hidden"); });
  document.addEventListener("keydown", (e) => {
    if (e.key !== "Escape") return;
    if (!$("#backtest").classList.contains("hidden")) $("#backtest").classList.add("hidden");
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
    await refreshState();
    await loadAllCharts();
    setInterval(refreshState, 15000);
    setInterval(loadAllCharts, 60000);
  })();
})();
