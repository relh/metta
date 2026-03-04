const AUTO_REFRESH_MS = 45_000;
const HOT_RELOAD_MS = 2_000;
let isRefreshing = false;

function escapeHtml(value) {
  return String(value || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function setStatus(text, isError = false) {
  const node = document.getElementById("status");
  if (!node) {
    return;
  }
  node.textContent = text;
  if (isError) {
    node.classList.add("error");
  } else {
    node.classList.remove("error");
  }
}

function formatDate(value) {
  if (!value) {
    return "-";
  }
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return String(value);
  }
  return parsed.toLocaleString();
}

function formatNumber(value, digits = 2) {
  return Number(value).toFixed(digits);
}

function compactPrinciple(principle) {
  const parenthetical = /\(([^)]+)\)\s*$/.exec(principle || "");
  if (parenthetical) {
    return parenthetical[1];
  }
  return String(principle || "");
}

function axisPanelHtml(panel) {
  const hasEvidence = Number(panel.evidence_count) > 0;
  const wins = panel.best_wins
    .map((win) => {
      return `
        <li>
          <span class="label">${escapeHtml(win.name)}</span>
          <span class="mult">×${formatNumber(win.expected_multiplier)}</span>
          <span class="meta">${escapeHtml(win.summary)}</span>
        </li>
      `;
    })
    .join("");
  const evidenceItems = (panel.evidence_titles || [])
    .slice(0, 3)
    .map((title) => `<span class="evidence-chip">${escapeHtml(title)}</span>`)
    .join("");
  const evidenceHtml = hasEvidence && evidenceItems
    ? `<div class="evidence-inline"><span class="evidence-label">Evidence</span>${evidenceItems}</div>`
    : "";
  const winsHtml = hasEvidence ? `<ul class="wins">${wins}</ul>` : "";

  return `
    <article class="panel">
      <div class="panel-title-line">
        <h2>${panel.index}. ${escapeHtml(panel.title)}</h2>
        <span class="panel-tagline">${escapeHtml(compactPrinciple(panel.principle))}</span>
      </div>
      <div class="metric-row">
        <span class="metric">Proj <strong>×${formatNumber(panel.projected_multiplier)}</strong></span>
        <span class="metric">Prior ×${formatNumber(panel.prior_multiplier)}</span>
        <span class="metric">Conf ${(Number(panel.confidence) * 100).toFixed(0)}%</span>
        <span class="metric">Ev ${Number(panel.evidence_count)}</span>
        <span class="metric">Score ${formatNumber(panel.opportunity_score, 3)}</span>
      </div>
      ${evidenceHtml}
      ${winsHtml}
    </article>
  `;
}

function betItemHtml(panel) {
  if (Number(panel.evidence_count) <= 0) {
    return "";
  }
  const topWin = panel.best_wins[0];
  if (!topWin) {
    return "";
  }
  return `
    <li>
      <div class="bet-axis">${escapeHtml(panel.title)}</div>
      <div class="bet-title">${escapeHtml(topWin.name)}</div>
      <div class="bet-meta">expected ×${formatNumber(topWin.expected_multiplier)} | axis ×${formatNumber(panel.projected_multiplier)} | score ${formatNumber(panel.opportunity_score, 3)}</div>
    </li>
  `;
}

function bucketHtml(label, toneClass, panels) {
  const items = panels.map(betItemHtml).filter(Boolean).join("");
  const content = items || '<li><div class="bet-meta">No bets available.</div></li>';
  return `
    <article class="bet-column ${toneClass}">
      <h3>${escapeHtml(label)}</h3>
      <ul class="bet-list">${content}</ul>
    </article>
  `;
}

async function fetchDashboard() {
  const response = await fetch("/api/v1/dashboard");
  if (!response.ok) {
    const message = await response.text();
    throw new Error(`request failed: ${response.status} ${message.slice(0, 200)}`);
  }
  return response.json();
}

function renderDashboard(snapshot) {
  const combinedNode = document.getElementById("combinedMultiplier");
  const generatedNode = document.getElementById("generatedAt");
  const panelRoot = document.getElementById("axisPanels");
  const topBetsRoot = document.getElementById("topBetsBuckets");
  if (!combinedNode || !generatedNode || !panelRoot || !topBetsRoot) {
    return;
  }

  combinedNode.innerHTML = `combined <strong>x${formatNumber(snapshot.combined_multiplier)}</strong>`;
  generatedNode.textContent = `generated: ${formatDate(snapshot.generated_at)}`;

  panelRoot.innerHTML = snapshot.ranked_axes.map(axisPanelHtml).join("");
  const nowPanels = snapshot.ranked_axes.slice(0, 2);
  const nextPanels = snapshot.ranked_axes.slice(2, 4);
  const laterPanels = snapshot.ranked_axes.slice(4, 6);
  topBetsRoot.innerHTML = [
    bucketHtml("Now", "now", nowPanels),
    bucketHtml("Next", "next", nextPanels),
    bucketHtml("Later", "later", laterPanels),
  ].join("");
}

async function refreshDashboard(trigger = "manual") {
  if (isRefreshing) {
    return;
  }
  isRefreshing = true;
  setStatus(trigger === "auto" ? "Auto-refreshing board..." : "Refreshing board...");
  try {
    const snapshot = await fetchDashboard();
    renderDashboard(snapshot);
    setStatus(
      `Updated ${formatDate(snapshot.generated_at)} | ${snapshot.ranked_axes.length} axes | auto-refresh ${Math.floor(AUTO_REFRESH_MS / 1000)}s`,
    );
  } catch (error) {
    setStatus(`Failed to load dashboard: ${error.message}`, true);
  } finally {
    isRefreshing = false;
  }
}

function init() {
  const query = new URLSearchParams(window.location.search);
  if (query.get("hot") === "1") {
    window.setInterval(() => {
      window.location.reload();
    }, HOT_RELOAD_MS);
  }
  void refreshDashboard("initial");
  window.setInterval(() => {
    void refreshDashboard("auto");
  }, AUTO_REFRESH_MS);
}

init();
