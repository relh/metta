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

function formatPercent(value, digits = 1) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) {
    return "-";
  }
  return `${(numeric * 100).toFixed(digits)}%`;
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

function healthCardHtml(label, value, meta = "") {
  return `
    <article class="health-card">
      <div class="health-label">${escapeHtml(label)}</div>
      <div class="health-value">${escapeHtml(String(value))}</div>
      <div class="health-meta">${escapeHtml(meta || "-")}</div>
    </article>
  `;
}

function kvRowHtml(label, value) {
  return `<li><span>${escapeHtml(label)}</span><strong>${escapeHtml(String(value))}</strong></li>`;
}

function funnelStageHtml(label, value, ratio) {
  const numericRatio = Number.isFinite(Number(ratio)) ? Math.max(0, Math.min(1, Number(ratio))) : 0;
  return `
    <article class="funnel-stage">
      <div class="funnel-stage-head">
        <span class="funnel-stage-title">${escapeHtml(label)}</span>
        <span class="funnel-stage-value">${escapeHtml(String(value))}</span>
      </div>
      <div class="funnel-progress"><span style="width: ${(numericRatio * 100).toFixed(1)}%"></span></div>
    </article>
  `;
}

function renderPipelineSnapshot(pipeline) {
  const cardsRoot = document.getElementById("pipelineHealthCards");
  const coverageRoot = document.getElementById("searchCoverageList");
  const meaningfulRoot = document.getElementById("meaningfulResultsSummary");
  if (!cardsRoot || !coverageRoot || !meaningfulRoot) {
    return;
  }

  if (!pipeline.available) {
    cardsRoot.innerHTML = healthCardHtml("Pipeline Metrics", "Unavailable", (pipeline.notes || [])[0] || "-");
    coverageRoot.innerHTML = kvRowHtml("Status", "Enable W&B metrics");
    meaningfulRoot.innerHTML = kvRowHtml("Status", "Not measurable");
    return;
  }

  const experiments = pipeline.experiments || {};
  const searchCoverage = pipeline.search_coverage || {};
  const meaningful = pipeline.meaningful_results || {};

  cardsRoot.innerHTML = [
    healthCardHtml("Running Now", Number(experiments.running_now || 0), "active experiments"),
    healthCardHtml(
      "7d Starts (LB)",
      Number(experiments.starts_recent_7d_lower_bound || 0),
      "running + finished + crashed",
    ),
    healthCardHtml(
      "7d Crash Rate",
      formatPercent(experiments.crash_rate_recent_7d, 1),
      `${Number(experiments.crashed_recent_7d || 0)} crashed / ${Number(experiments.finished_recent_7d || 0)} finished`,
    ),
    healthCardHtml(
      "Stale Running",
      Number(experiments.running_stale_gt_14d || 0),
      "older than 14 days",
    ),
  ].join("");

  const familyRows = (searchCoverage.dominant_families_30d || [])
    .slice(0, 5)
    .map((item) => kvRowHtml(item.family, `${item.count} (${formatPercent(item.share, 1)})`));
  coverageRoot.innerHTML = [
    kvRowHtml("Unique families", Number(searchCoverage.unique_families_30d || 0)),
    kvRowHtml("Top-family share", formatPercent(searchCoverage.top_family_share_30d, 1)),
    kvRowHtml("Coverage entropy", formatNumber(searchCoverage.family_entropy_30d, 2)),
    ...familyRows,
  ].join("");

  meaningfulRoot.innerHTML = [
    kvRowHtml("Measurable", meaningful.measurable ? "Yes" : "No"),
    kvRowHtml("Primary metric", meaningful.primary_metric || "-"),
    kvRowHtml("Metric coverage", formatPercent(meaningful.primary_metric_coverage_ratio, 1)),
    kvRowHtml("Meaningful events (7d)", Number(meaningful.meaningful_events_7d || 0)),
    kvRowHtml("Meaningful events (30d)", Number(meaningful.meaningful_events_30d || 0)),
    kvRowHtml("Weekly meaningful rate", formatNumber(meaningful.weekly_meaningful_rate, 2)),
  ].join("");
}

function renderResearchFunnel(funnel) {
  const stagesRoot = document.getElementById("researchFunnelStages");
  const summaryRoot = document.getElementById("researchFunnelSummary");
  if (!stagesRoot || !summaryRoot) {
    return;
  }
  const stages = funnel.stages || {};
  const paperSelected = Number(stages.paper_selected || 0);
  const repoFound = Number(stages.author_repo_found || 0);
  const implemented = Number(stages.implemented_in_metta || 0);

  const repoRatio = paperSelected > 0 ? repoFound / paperSelected : 0;
  const implRatio = paperSelected > 0 ? implemented / paperSelected : 0;
  stagesRoot.innerHTML = [
    funnelStageHtml("Paper selected", paperSelected, 1),
    funnelStageHtml("Author repo found", repoFound, repoRatio),
    funnelStageHtml("Implemented in metta", implemented, implRatio),
  ].join("");

  summaryRoot.innerHTML = [
    kvRowHtml("Tasks total", Number(funnel.tasks_total || 0)),
    kvRowHtml(
      "LLM coverage",
      `${Number(funnel.llm_scored_tasks || 0)}/${Number(funnel.tasks_total || 0)} (${formatPercent(funnel.llm_coverage, 1)})`,
    ),
    kvRowHtml("Paper signals", Number(funnel.paper_signal_tasks || 0)),
    kvRowHtml("Repo signals", Number(funnel.repo_signal_tasks || 0)),
    kvRowHtml("Implemented tasks", Number(funnel.implemented_tasks || 0)),
    kvRowHtml("Paper→Repo conv", formatPercent(stages.paper_to_repo_conversion, 1)),
    kvRowHtml("Repo→Impl conv", formatPercent(stages.repo_to_impl_conversion, 1)),
  ].join("");
}

async function fetchBoardData() {
  const response = await fetch("/api/v1/board");
  if (!response.ok) {
    const message = await response.text();
    throw new Error(`request failed: ${response.status} ${message.slice(0, 200)}`);
  }
  return response.json();
}

function renderDashboard(snapshot, taskRanking, pipeline, funnel) {
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

  renderPipelineSnapshot(pipeline);
  renderResearchFunnel(funnel);
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
    const pipeline = board.pipeline || {};
    const funnel = board.research_funnel || {};
    renderDashboard(snapshot, taskRanking, pipeline, funnel);
    const betCount = (taskRanking?.ranked_tasks || []).length;
    const axisCount = (snapshot?.ranked_axes || []).length;
    const llmScoredTasks = Number(snapshot?.llm_scored_tasks || 0);
    const tasksTotal = Number(snapshot?.tasks_total || 0);
    const runningNow = Number(pipeline?.experiments?.running_now || 0);
    setStatus(
      `Updated ${formatDate(snapshot.generated_at)} | running ${runningNow} | ${axisCount} axes | llm ${llmScoredTasks}/${tasksTotal} | ${betCount} ranked tasks | auto-refresh ${Math.floor(AUTO_REFRESH_MS / 1000)}s`,
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
