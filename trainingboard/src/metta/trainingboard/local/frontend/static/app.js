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

function axisPanelHtml(panel) {
  const wins = panel.best_wins
    .map((win) => {
      return `
        <li>
          <span class="label">${escapeHtml(win.name)} <strong>×${Number(win.expected_multiplier).toFixed(2)}</strong></span>
          <div class="meta">${escapeHtml(win.summary)}</div>
        </li>
      `;
    })
    .join("");
  const evidenceItems = (panel.evidence_titles || [])
    .slice(0, 3)
    .map((title) => `<li>${escapeHtml(title)}</li>`)
    .join("");
  const evidenceHtml = evidenceItems
    ? `<ul class="evidence">${evidenceItems}</ul>`
    : '<div class="evidence-empty">No linked Asana research evidence yet.</div>';

  return `
    <article class="panel">
      <h2>${panel.index}. ${escapeHtml(panel.title)}</h2>
      <div class="subtitle">${escapeHtml(panel.principle)}</div>
      <div class="metric-row">
        <span class="metric">Projected <strong>×${Number(panel.projected_multiplier).toFixed(2)}</strong></span>
        <span class="metric">Prior ×${Number(panel.prior_multiplier).toFixed(2)}</span>
        <span class="metric">Confidence ${(Number(panel.confidence) * 100).toFixed(0)}%</span>
        <span class="metric">Evidence ${Number(panel.evidence_count)}</span>
      </div>
      ${evidenceHtml}
      <ul class="wins">${wins}</ul>
    </article>
  `;
}

function rankingHtml(panel, position) {
  return `
    <li>
      <span>${position}. ${escapeHtml(panel.title)}</span>
      <span class="score">score ${Number(panel.opportunity_score).toFixed(3)} | ×${Number(panel.projected_multiplier).toFixed(2)}</span>
    </li>
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
  const rankingRoot = document.getElementById("rankingList");
  if (!combinedNode || !generatedNode || !panelRoot || !rankingRoot) {
    return;
  }

  combinedNode.textContent = `combined: ×${Number(snapshot.combined_multiplier).toFixed(2)}`;
  generatedNode.textContent = `generated: ${formatDate(snapshot.generated_at)}`;

  panelRoot.innerHTML = snapshot.ranked_axes.map(axisPanelHtml).join("");
  rankingRoot.innerHTML = snapshot.ranked_axes.map((panel, index) => rankingHtml(panel, index + 1)).join("");
}

async function refreshDashboard() {
  setStatus("Refreshing dashboard...");
  try {
    const snapshot = await fetchDashboard();
    renderDashboard(snapshot);
    setStatus(`Loaded ${snapshot.ranked_axes.length} flywheel axes.`);
  } catch (error) {
    setStatus(`Failed to load dashboard: ${error.message}`, true);
  }
}

function init() {
  const refreshButton = document.getElementById("refreshButton");
  if (refreshButton) {
    refreshButton.addEventListener("click", refreshDashboard);
  }
  refreshDashboard();
}

init();
