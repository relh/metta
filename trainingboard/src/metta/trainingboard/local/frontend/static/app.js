const AUTO_REFRESH_MS = 45_000;
const BETS_PER_BUCKET = 5;
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
  const numeric = Number(value);
  return Number.isFinite(numeric) ? numeric.toFixed(digits) : "-";
}

function compactPrinciple(principle) {
  const parenthetical = /\(([^)]+)\)\s*$/.exec(principle || "");
  if (parenthetical) {
    return parenthetical[1];
  }
  return String(principle || "");
}

const IMPACT_METRIC_META = {
  experience_parallelism: { short: "1", long: "1. Experience-Level Parallelism" },
  experience_quality: { short: "2", long: "2. Experience Quality" },
  loss_parallelism: { short: "3", long: "3. Loss-Level Parallelism" },
  loss_signal_quality: { short: "4", long: "4. Loss Signal Quality" },
  parameter_parallelism: { short: "5", long: "5. Parameter-Level Parallelism" },
  hyperparameter_quality: { short: "6", long: "6. Hyperparameter Quality" },
};

const EXECUTION_METRIC_META = {
  simplicity: { short: "S", long: "Simplicity" },
  time_to_implement: { short: "T", long: "Time to Implement" },
  failure_likelihood: { short: "F", long: "Failure Likelihood" },
  dependency_load: { short: "D", long: "Dependency Load" },
  measurement_speed: { short: "M", long: "Measurement Speed" },
  reversibility: { short: "R", long: "Reversibility" },
};

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
        <span class="panel-ev">Ev ${Number(panel.evidence_count)}</span>
        <span class="panel-tagline">${escapeHtml(compactPrinciple(panel.principle))}</span>
      </div>
      ${evidenceHtml}
      ${winsHtml}
    </article>
  `;
}

function metricPillHtml(label, value, title) {
  return `
    <span class="metric-pill" title="${escapeHtml(title)}">
      <span class="metric-label">${escapeHtml(label)}</span>
      <span class="metric-value">${formatNumber(value, 2)}</span>
    </span>
  `;
}

function betItemHtml(task, impactMetrics, executionMetrics) {
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
  const axisScores = task.axis_scores || {};
  const executionScores = task.execution_scores || {};
  const orderedImpactMetrics = impactMetrics && impactMetrics.length
    ? impactMetrics
    : Object.keys(IMPACT_METRIC_META);
  const orderedExecutionMetrics = executionMetrics && executionMetrics.length
    ? executionMetrics
    : Object.keys(EXECUTION_METRIC_META);
  const metricPills = [
    ...orderedImpactMetrics.map((metricId) => {
      const meta = IMPACT_METRIC_META[metricId] || { short: metricId, long: metricId };
      return metricPillHtml(meta.short, axisScores[metricId], meta.long);
    }),
    ...orderedExecutionMetrics.map((metricId) => {
      const meta = EXECUTION_METRIC_META[metricId] || { short: metricId, long: metricId };
      return metricPillHtml(meta.short, executionScores[metricId], meta.long);
    }),
  ].join("");
  return `
    <li>
      <div class="bet-axis">${escapeHtml(axisLabel)}</div>
      <div class="bet-title"><a href="${taskUrl}" target="_blank" rel="noopener noreferrer">${taskTitle}</a></div>
      <div class="bet-metrics">${metricPills}</div>
    </li>
  `;
}

function bucketHtml(label, toneClass, tasks, impactMetrics, executionMetrics) {
  const items = tasks
    .map((task) => betItemHtml(task, impactMetrics, executionMetrics))
    .filter(Boolean)
    .join("");
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
  const generatedNode = document.getElementById("generatedAt");
  const scoringNode = document.getElementById("scoringMode");
  const panelRoot = document.getElementById("axisPanels");
  const topBetsRoot = document.getElementById("topBetsBuckets");
  if (!generatedNode || !panelRoot || !topBetsRoot || !scoringNode) {
    return;
  }

  const rankedAxes = snapshot?.ranked_axes || [];
  const llmScoredTasks = Number(snapshot?.llm_scored_tasks || 0);
  const tasksTotal = Number(snapshot?.tasks_total || 0);
  const scoringSource = snapshot?.scoring_source || "llm_only";
  const scoringLabel = scoringSource === "llm_only" ? "LLM only" : scoringSource;

  generatedNode.textContent = `generated: ${formatDate(snapshot.generated_at)}`;
  scoringNode.textContent = `scoring: ${scoringLabel} (${llmScoredTasks}/${tasksTotal})`;

  panelRoot.innerHTML = rankedAxes.map(axisPanelHtml).join("");
  const rankedTasks = taskRanking?.ranked_tasks || [];
  const impactMetrics = taskRanking?.impact_metrics || [];
  const executionMetrics = taskRanking?.execution_metrics || [];
  const nowTasks = rankedTasks.slice(0, BETS_PER_BUCKET);
  const nextTasks = rankedTasks.slice(BETS_PER_BUCKET, BETS_PER_BUCKET * 2);
  const laterTasks = rankedTasks.slice(BETS_PER_BUCKET * 2, BETS_PER_BUCKET * 3);
  topBetsRoot.innerHTML = [
    bucketHtml("Now", "now", nowTasks, impactMetrics, executionMetrics),
    bucketHtml("Next", "next", nextTasks, impactMetrics, executionMetrics),
    bucketHtml("Later", "later", laterTasks, impactMetrics, executionMetrics),
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
    const axisCount = (snapshot?.ranked_axes || []).length;
    const llmScoredTasks = Number(snapshot?.llm_scored_tasks || 0);
    const tasksTotal = Number(snapshot?.tasks_total || 0);
    setStatus(
      `Updated ${formatDate(snapshot.generated_at)} | ${axisCount} axes | llm ${llmScoredTasks}/${tasksTotal} | ${betCount} ranked tasks | auto-refresh ${Math.floor(AUTO_REFRESH_MS / 1000)}s`,
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
