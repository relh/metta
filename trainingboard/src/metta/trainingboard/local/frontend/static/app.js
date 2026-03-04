const AUTO_REFRESH_MS = 45_000;
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

function betItemHtml(task) {
  const axisNames = {
    experience_parallelism: "Experience Parallelism",
    experience_quality: "Experience Quality",
    loss_parallelism: "Loss Parallelism",
    loss_signal_quality: "Loss Signal Quality",
    parameter_parallelism: "Parameter Parallelism",
    hyperparameter_quality: "Hyperparameter Quality",
  };
  const primaryAxis = (task.top_axes || [])[0] || "";
  const axisLabel = axisNames[primaryAxis] || primaryAxis || "Unmapped";
  const taskUrl = escapeHtml(task.permalink_url || "#");
  const taskTitle = escapeHtml(task.title || task.gid || "Untitled task");
  return `
    <li>
      <div class="bet-axis">${escapeHtml(axisLabel)}</div>
      <div class="bet-title"><a href="${taskUrl}" target="_blank" rel="noopener noreferrer">${taskTitle}</a></div>
      <div class="bet-meta">priority ${formatNumber(task.priority_score, 3)} | impact ${formatNumber(task.impact_score, 3)} | feasibility ${formatNumber(task.feasibility_score, 3)}</div>
    </li>
  `;
}

function bucketHtml(label, toneClass, tasks) {
  const items = tasks.map(betItemHtml).filter(Boolean).join("");
  const content = items || '<li><div class="bet-meta">No bets available.</div></li>';
  return `
    <article class="bet-column ${toneClass}">
      <h3>${escapeHtml(label)}</h3>
      <ul class="bet-list">${content}</ul>
    </article>
  `;
}

async function fetchBoardData() {
  const response = await fetch("/api/v1/board");
  if (!response.ok) {
    const message = await response.text();
    throw new Error(`request failed: ${response.status} ${message.slice(0, 200)}`);
  }
  return response.json();
}

function renderDashboard(snapshot, taskRanking) {
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
  const rankedTasks = taskRanking?.ranked_tasks || [];
  const nowTasks = rankedTasks.slice(0, 3);
  const nextTasks = rankedTasks.slice(3, 6);
  const laterTasks = rankedTasks.slice(6, 9);
  topBetsRoot.innerHTML = [
    bucketHtml("Now", "now", nowTasks),
    bucketHtml("Next", "next", nextTasks),
    bucketHtml("Later", "later", laterTasks),
  ].join("");
}

async function refreshDashboard(trigger = "manual") {
  if (isRefreshing) {
    return;
  }
  isRefreshing = true;
  setStatus(trigger === "auto" ? "Auto-refreshing board..." : "Refreshing board...");
  try {
    const board = await fetchBoardData();
    const snapshot = board.dashboard || {};
    const taskRanking = board.task_ranking || {};
    renderDashboard(snapshot, taskRanking);
    const betCount = (taskRanking?.ranked_tasks || []).length;
    setStatus(
      `Updated ${formatDate(snapshot.generated_at)} | ${snapshot.ranked_axes.length} axes | ${betCount} ranked tasks | auto-refresh ${Math.floor(AUTO_REFRESH_MS / 1000)}s`,
    );
  } catch (error) {
    setStatus(`Failed to load dashboard: ${error.message}`, true);
  } finally {
    isRefreshing = false;
  }
}

function init() {
  void refreshDashboard("initial");
  window.setInterval(() => {
    void refreshDashboard("auto");
  }, AUTO_REFRESH_MS);
}

init();
