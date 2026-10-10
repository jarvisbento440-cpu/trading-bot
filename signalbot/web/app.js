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
    layers: store.get("layers", { signals: true, ema: true, fib: true, sr: false, bb: false }),
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
      bbUp: line(COLORS.bb, 1, 2), bbLo: line(COLORS.bb, 1, 2),
      priceLines: [], big, fitted: false,
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

    // Signal-Pfeile
    const markers = L.signals ? data.setups.map((s) => ({
      time: s.time + TZ,
      position: s.side === "long" ? "belowBar" : "aboveBar",
      color: s.side === "long" ? COLORS.up : COLORS.down,
      shape: s.side === "long" ? "arrowUp" : "arrowDown",
      text: (c.big ? (s.side === "long" ? "L" : "S") : "") + s.score,
    })) : [];
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
    if (L.sr && data.sr) {
      data.sr.forEach((l) => add(l.price, l.kind === "resistance" ? COLORS.res : COLORS.sup,
        (l.kind === "resistance" ? "Widerstand" : "Unterstützung") + " (" + l.touches + "x)", 1, 2));
    }
    if (L.signals && data.active) {
      const a = data.active;
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

  async function loadChart(symbol) {
    const data = await getJSON(`/api/chart?symbol=${encodeURIComponent(symbol)}&tf=${state.tf}`);
    state.data.set(symbol + "|" + state.tf, data);
    const tile = state.tiles.get(symbol);
    if (tile) {
      $(".tile-empty", tile.el).hidden = !!data.candles.length;
      render(tile.chart, data);
      const sig = $(".tile-sig", tile.el);
      if (data.active) {
        sig.hidden = false;
        sig.textContent = `${sideDe(data.active.side)} ${data.active.score}`;
        sig.className = "badge tile-sig sig-" + data.active.side;
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
          body: `Einstieg ~${fmt(sig.entry)} · Stop ${fmt(sig.stop)} · Score ${sig.score}`, tag: "sig" + sig.id });
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
        <div class="row"><span>Einstieg ${fmt(s.entry)}</span><span>Score ${s.score}</span></div>
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

    st.coins.forEach((coin) => {
      const tile = state.tiles.get(coin.symbol) || makeTile(coin);
      updateTileHead(tile, coin);
    });

    const maxId = st.signals.reduce((m, s) => Math.max(m, s.id), 0);
    if (state.lastSeenId === null) state.lastSeenId = maxId; // erster Start: alte Signale nicht als neu melden
    const fresh = st.signals.filter((s) => s.id > state.lastSeenId).reverse();
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
    const a = data.active;
    const row = (k, v, cls = "") => `<tr><td>${k}</td><td class="${cls}">${v}</td></tr>`;
    let html = "";
    if (a) {
      const rr = Math.abs(a.target1 - a.entry) / Math.abs(a.entry - a.stop);
      html += `<h3>Aktuelles Signal</h3>
        <div class="badge sig-${a.side}" style="display:inline-block;font-size:13px">${sideDe(a.side)} · Score ${a.score}/100</div>
        <table>${row("Einstieg", fmt(a.entry))}${row("Stop", fmt(a.stop), "down")}${row("Ziel 1", fmt(a.target1), "up")}
        ${row("Ziel 2", fmt(a.target2), "up")}${row("Chance/Risiko", "1 : " + rr.toFixed(1).replace(".", ","))}</table>
        <h3>Gründe</h3><ul>${a.reasons.map((r) => `<li>${r}</li>`).join("")}</ul>`;
    } else {
      html += `<h3>Aktuelles Signal</h3><p class="muted">Gerade kein Setup über dem Mindest-Score.</p>`;
    }
    if (data.rsi != null) html += `<h3>Indikatoren</h3><table>${row("RSI (14)", data.rsi.toFixed(0))}</table>`;
    if (data.fib) {
      html += `<h3>Fibonacci (${data.fib.direction === "up" ? "Aufwärtsimpuls" : "Abwärtsimpuls"})</h3><table>` +
        data.fib.levels.map((l) => row((l.ratio * 100).toFixed(1).replace(".", ",") + " %", fmt(l.price))).join("") + "</table>";
    }
    if (data.sr && data.sr.length) {
      html += `<h3>Unterstützung / Widerstand</h3><table>` +
        data.sr.map((l) => row(l.kind === "resistance" ? "Widerstand" : "Unterstützung", fmt(l.price), l.kind === "resistance" ? "down" : "up")).join("") + "</table>";
    }
    html += `<h3>Vergangene Signale im Chart</h3><p class="muted">${data.setups.length} Signale (Pfeile mit Score). Mausrad = Zoom, Ziehen = Verschieben.</p>
      <p class="disclaimer">Der Score ist keine Gewinngarantie. Immer mit Stop handeln, max. 1–2 % Risiko pro Trade.</p>`;
    $("#focus-info").innerHTML = html;
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
  document.addEventListener("keydown", (e) => { if (e.key === "Escape" && state.focus) closeFocus(); });
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
