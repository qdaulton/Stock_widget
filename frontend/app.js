// =========================
// CONFIG
// =========================

const WS_URL = "ws://127.0.0.1:8000/ws/prices";
const TRACKED_SYMBOLS = ["AAPL", "TSLA", "NVDA", "MSFT"];

// Front-end description of the static alert rules (matches backend config)
const STATIC_ALERT_RULES = [
  {
    id: 1,
    symbol: "AAPL",
    direction: "above",
    threshold: 200,
    active: true,
    webex_enabled: true,
  },
  {
    id: 2,
    symbol: "TSLA",
    direction: "above",
    threshold: 180,
    active: true,
    webex_enabled: true,
  },
  {
    id: 3,
    symbol: "NVDA",
    direction: "above",
    threshold: 1000,
    active: true,
    webex_enabled: false,
    note: "High priority",
  },
];

// =========================
// STATE
// =========================

let latestPrices = {};
let chart = null;
let chartSymbol = "AAPL";
let chartHistory = [];
let usingMockFeed = false;

// =========================
// DOM REFERENCES
// =========================

const wsStatusPill = document.getElementById("ws-status-pill");
const stocksTableBody = document.getElementById("stocks-table-body");
const recentAlertsContainer = document.getElementById("recent-alerts");
const alertRulesList = document.getElementById("alert-rules-list");
const chartSymbolLabel = document.getElementById("chart-symbol-label");
const themeToggleBtn = document.getElementById("theme-toggle");

// =========================
// THEME HANDLING
// =========================

function refreshChartColors() {
  if (!chart) return;
  const canvas = document.getElementById("price-chart");
  if (!canvas) return;

  const styles = getComputedStyle(canvas);
  const line = styles.getPropertyValue("--chart-line").trim();
  const fill = styles.getPropertyValue("--chart-fill").trim();
  const grid = styles.getPropertyValue("--chart-grid").trim();
  const ticks = styles.getPropertyValue("--chart-ticks").trim();

  chart.data.datasets[0].borderColor = line;
  chart.data.datasets[0].backgroundColor = fill;
  chart.options.scales.x.ticks.color = ticks;
  chart.options.scales.y.ticks.color = ticks;
  chart.options.scales.y.grid.color = grid;
  chart.update("none");
}

function applyTheme(theme) {
  const root = document.documentElement;
  root.setAttribute("data-theme", theme);

  if (themeToggleBtn) {
    themeToggleBtn.textContent = theme === "dark" ? "Dark mode" : "Light mode";
  }

  refreshChartColors();
}

function initTheme() {
  const saved = localStorage.getItem("theme") || "dark";
  applyTheme(saved);

  if (themeToggleBtn) {
    themeToggleBtn.addEventListener("click", () => {
      const current =
        document.documentElement.getAttribute("data-theme") || "dark";
      const next = current === "dark" ? "light" : "dark";
      applyTheme(next);
      localStorage.setItem("theme", next);
    });
  }
}

// =========================
// WEBSOCKET STATUS PILL
// =========================

function setWsStatus(state, text) {
  if (!wsStatusPill) return;

  wsStatusPill.classList.remove("pill-connected", "pill-disconnected");

  if (state === "connected") {
    wsStatusPill.classList.add("pill-connected");
  } else if (state === "error") {
    wsStatusPill.classList.add("pill-disconnected");
  }

  wsStatusPill.textContent = text;
}

function formatTime(ts) {
  const d = ts ? new Date(ts) : new Date();
  return d.toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

// =========================
/*       LIVE PRICES TABLE */
// =========================

function renderStocksTable() {
  if (!stocksTableBody) return;

  stocksTableBody.innerHTML = "";

  TRACKED_SYMBOLS.forEach((symbol) => {
    const data = latestPrices[symbol];
    if (!data) return;

    const tr = document.createElement("tr");

    if (symbol === chartSymbol) {
      tr.classList.add("row-selected");
    }

    const isUp = data.change >= 0;
    const changeClass = isUp ? "price-up" : "price-down";
    const sign = isUp ? "+" : "";

    tr.innerHTML = `
      <td>${symbol}</td>
      <td>${data.price.toFixed(2)}</td>
      <td class="${changeClass}">${sign}${data.change.toFixed(2)}</td>
      <td class="${changeClass}">${sign}${data.percentChange.toFixed(2)}%</td>
      <td>${formatTime(data.ts)}</td>
    `;

    tr.addEventListener("click", () => {
      chartSymbol = symbol;
      chartHistory = [];
      if (chartSymbolLabel) chartSymbolLabel.textContent = symbol;
      renderStocksTable();
      updateChart(chartSymbol);
    });

    stocksTableBody.appendChild(tr);
  });
}

// =========================
/*          RECENT ALERTS  */
// =========================

function ensureAlertsPlaceholder() {
  if (!recentAlertsContainer) return;
  if (recentAlertsContainer.children.length === 0) {
    const div = document.createElement("div");
    div.className = "alert-meta alerts-placeholder";
    div.textContent = "No alerts yet. They’ll appear here when rules trigger.";
    recentAlertsContainer.appendChild(div);
  }
}

function addRecentAlert(symbol, direction, price, triggeredAt) {
  if (!recentAlertsContainer) return;

  // Remove placeholder if present
  const placeholder = recentAlertsContainer.querySelector(".alerts-placeholder");
  if (placeholder) placeholder.remove();

  const div = document.createElement("div");
  div.className = "alert-item";

  const timeLabel = triggeredAt ? formatTime(triggeredAt) : formatTime();

  div.innerHTML = `
    <span class="alert-text">${symbol} moved ${direction} to ${price.toFixed(
    2
  )}</span>
    <span class="alert-meta">${timeLabel}</span>
  `;

  recentAlertsContainer.prepend(div);

  while (recentAlertsContainer.children.length > 6) {
    recentAlertsContainer.removeChild(recentAlertsContainer.lastChild);
  }
}

function initRecentAlertsCard() {
  // just show placeholder at startup; live alerts come from WS / mock
  ensureAlertsPlaceholder();
}

// =========================
/*          ALERT RULES     */
// =========================

function renderSingleRule(rule) {
  const li = document.createElement("li");

  const symbol = rule.symbol || rule.ticker || "N/A";
  const direction =
    rule.direction ||
    rule.condition ||
    rule.operator ||
    (rule.above ? "above" : rule.below ? "below" : "");
  const threshold =
    rule.threshold ??
    rule.price ??
    rule.target_price ??
    rule.trigger_price ??
    "";

  const active = rule.active ?? rule.is_active ?? true;
  const sendWebex = rule.webex_enabled ?? rule.send_webex ?? rule.notify ?? false;

  li.innerHTML = `
    <div>
      <div class="rule-symbol">${symbol} ${
    direction ? direction.toUpperCase() : ""
  } ${threshold !== "" ? threshold : ""}</div>
      <div class="rule-meta">
        ${active ? "Active" : "Disabled"} ${
    sendWebex ? "· WebEx notifications" : ""
  } ${rule.note ? "· " + rule.note : ""} ${rule.id ? `· #${rule.id}` : ""}
      </div>
    </div>
  `;

  return li;
}

function loadAlertRules() {
  if (!alertRulesList) return;

  alertRulesList.innerHTML = "";
  STATIC_ALERT_RULES.forEach((rule) => {
    alertRulesList.appendChild(renderSingleRule(rule));
  });
}

// =========================
/*          CHART.js       */
// =========================

function initChart() {
  if (typeof Chart === "undefined") return;

  const canvas = document.getElementById("price-chart");
  if (!canvas) return;
  const ctx = canvas.getContext("2d");
  const styles = getComputedStyle(canvas);

  chart = new Chart(ctx, {
    type: "line",
    data: {
      labels: [],
      datasets: [
        {
          label: "Price",
          data: [],
          tension: 0.25,
          borderWidth: 3,
          borderColor: styles.getPropertyValue("--chart-line").trim(),
          backgroundColor: styles.getPropertyValue("--chart-fill").trim(),
          pointRadius: 0,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      scales: {
        x: {
          ticks: {
            color: styles.getPropertyValue("--chart-ticks").trim(),
          },
          grid: { display: false },
        },
        y: {
          ticks: {
            color: styles.getPropertyValue("--chart-ticks").trim(),
          },
          grid: {
            color: styles.getPropertyValue("--chart-grid").trim(),
          },
        },
      },
      plugins: {
        legend: { display: false },
      },
    },
  });
}

function updateChart(symbol) {
  if (!chart) return;
  const data = latestPrices[symbol];
  if (!data) return;

  chartHistory.push({ ts: data.ts, price: data.price });
  if (chartHistory.length > 20) chartHistory.shift();

  chart.data.labels = chartHistory.map((p) => formatTime(p.ts));
  chart.data.datasets[0].data = chartHistory.map((p) => p.price);

  chart.update();
}

// =========================
/*        WEBSOCKET        */
// =========================

function connectWebSocket() {
  try {
    const socket = new WebSocket(WS_URL);

    socket.addEventListener("open", () => {
      usingMockFeed = false;
      setWsStatus("connected", "LIVE DATA: CONNECTED");
    });

    socket.addEventListener("message", (event) => {
      let msg;
      try {
        msg = JSON.parse(event.data);
      } catch {
        return;
      }

      if (msg.type !== "price_update") return;

      msg.data.forEach((item) => {
        const prev = latestPrices[item.symbol];
        latestPrices[item.symbol] = item;

        if (prev && Math.abs(item.price - prev.price) >= 1.5) {
          addRecentAlert(
            item.symbol,
            item.price > prev.price ? "up" : "down",
            item.price
          );
        }
      });

      renderStocksTable();
      updateChart(chartSymbol);
    });

    socket.addEventListener("close", () => {
      if (!usingMockFeed) startMockFeed();
    });

    socket.addEventListener("error", () => {
      if (!usingMockFeed) startMockFeed();
    });
  } catch (err) {
    startMockFeed();
  }
}

// =========================
/*        MOCK FEED        */
// =========================

function startMockFeed() {
  usingMockFeed = true;
  setWsStatus("error", "LIVE DATA: DEMO");

  if (Object.keys(latestPrices).length === 0) {
    const now = new Date().toISOString();
    TRACKED_SYMBOLS.forEach((sym, idx) => {
      latestPrices[sym] = {
        symbol: sym,
        price: 100 + idx * 50,
        change: 0,
        percentChange: 0,
        ts: now,
      };
    });
    renderStocksTable();
    updateChart(chartSymbol);
  }

  setInterval(() => {
    const now = new Date().toISOString();

    TRACKED_SYMBOLS.forEach((sym) => {
      const prev = latestPrices[sym];
      const delta = (Math.random() - 0.5) * 4;
      const newPrice = Math.max(1, prev.price + delta);
      const change = newPrice - prev.price;
      const percentChange = (change / prev.price) * 100;

      latestPrices[sym] = {
        symbol: sym,
        price: newPrice,
        change,
        percentChange,
        ts: now,
      };

      if (Math.abs(change) >= 1.5) {
        addRecentAlert(sym, change > 0 ? "up" : "down", newPrice);
      }
    });

    renderStocksTable();
    updateChart(chartSymbol);
  }, 2500);
}

// =========================
/*   OPTIONAL SIDEBAR NAV  */
// =========================

function initSidebarNav() {
  document.querySelectorAll(".nav-item").forEach((item) => {
    item.addEventListener("click", (e) => {
      e.preventDefault();

      document
        .querySelectorAll(".nav-item")
        .forEach((i) => i.classList.remove("active"));
      item.classList.add("active");

      const targetId = item.getAttribute("data-target");

      if (targetId === "top") {
        window.scrollTo({ top: 0, behavior: "smooth" });
      } else {
        const section = document.getElementById(targetId);
        if (section) {
          section.scrollIntoView({ behavior: "smooth" });
        }
      }
    });
  });
}

// =========================
// INIT
// =========================

document.addEventListener("DOMContentLoaded", () => {
  initTheme();

  if (chartSymbolLabel) chartSymbolLabel.textContent = chartSymbol;
  initChart();

  // front-end driven cards
  loadAlertRules();
  initRecentAlertsCard();

  // live prices / alerts
  connectWebSocket();

  initSidebarNav();
});
