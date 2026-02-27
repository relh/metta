const MAX_BRANCH_ROWS = 500;
const MAX_SESSION_ROWS = 800;

const state = {
  catalog: null,
  branchFilter: "",
  sessionFilter: "",
};

function parseBranchList(rawValue) {
  const values = (rawValue || "")
    .split(",")
    .map((value) => value.trim())
    .filter((value) => value.length > 0);
  return Array.from(new Set(values));
}

async function fetchJson(url) {
  const response = await fetch(url);
  if (!response.ok) {
    const message = await response.text();
    throw new Error(`Request failed: ${response.status} ${message.slice(0, 200)}`);
  }
  return response.json();
}

async function fetchJsonWithPayload(url, payload) {
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    const message = await response.text();
    throw new Error(`Request failed: ${response.status} ${message.slice(0, 200)}`);
  }
  return response.json();
}

function escapeHtml(value) {
  return String(value || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function formatDate(value) {
  if (!value) return "-";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return String(value);
  return parsed.toLocaleString();
}

function formatDateCompact(value) {
  if (!value) return "-";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return String(value);
  return parsed.toLocaleString([], {
    month: "numeric",
    day: "numeric",
    year: "2-digit",
    hour: "numeric",
    minute: "2-digit",
  });
}

function formatBytes(value) {
  const raw = Number(value || 0);
  if (!Number.isFinite(raw) || raw <= 0) return "0 B";
  if (raw < 1024) return `${raw.toFixed(0)} B`;
  if (raw < 1024 ** 2) return `${(raw / 1024).toFixed(1)} KB`;
  if (raw < 1024 ** 3) return `${(raw / 1024 ** 2).toFixed(1)} MB`;
  return `${(raw / 1024 ** 3).toFixed(2)} GB`;
}

function setCatalogStatus(text, isError = false) {
  const node = document.getElementById("catalogStatus");
  if (!node) return;
  node.textContent = text;
  if (isError) {
    node.classList.add("error");
  } else {
    node.classList.remove("error");
  }
}

function renderProgressBar(value, phaseText) {
  const wrap = document.getElementById("catalogProgressWrap");
  const bar = document.getElementById("catalogProgressBar");
  const text = document.getElementById("catalogProgressText");
  if (!wrap || !bar || !text) return;
  wrap.classList.remove("hidden");
  bar.style.width = `${Math.max(0, Math.min(100, value))}%`;
  text.textContent = phaseText;
}

function hideProgressBar() {
  const wrap = document.getElementById("catalogProgressWrap");
  const bar = document.getElementById("catalogProgressBar");
  if (!wrap || !bar) return;
  wrap.classList.add("hidden");
  bar.style.width = "0%";
}

function setAnalysisOutput(text) {
  const node = document.getElementById("analysisOutput");
  if (node) {
    node.textContent = text || "";
  }
}

function getAnalysisBranches() {
  const input = document.getElementById("analysisBranches");
  return parseBranchList(input ? input.value : "");
}

function setAnalysisBranches(branches) {
  const input = document.getElementById("analysisBranches");
  if (input) {
    input.value = branches.join(", ");
    input.focus();
  }
}

function renderFindResponse(payload) {
  const lines = [
    `Branches: ${(payload.branches || []).join(", ")}`,
    `Matches: ${payload.count || 0}`,
    "",
  ];

  (payload.matches || []).forEach((match) => {
    lines.push(
      `${match.source} | ${match.session_id} | ${Number(match.size_bytes || 0).toLocaleString()}B | branches: ${(match.matched_branches || []).join(", ")}`,
    );
    lines.push(`  ${match.path}`);
  });

  setAnalysisOutput(lines.join("\n"));
}

async function runAnalysisAction(action) {
  const branches = getAnalysisBranches();
  if (branches.length === 0) {
    setAnalysisOutput("Enter at least one branch name.");
    return;
  }

  setAnalysisOutput(`Running ${action} for: ${branches.join(", ")} ...`);
  try {
    const payload = await fetchJsonWithPayload(`/api/analysis/${action}`, { branches });
    if (action === "find") {
      renderFindResponse(payload);
      return;
    }
    if (action === "context") {
      setAnalysisOutput(payload.context || "No context returned.");
      return;
    }
    if (action === "run") {
      setAnalysisOutput(payload.output || "No analysis output returned.");
      return;
    }
    setAnalysisOutput(JSON.stringify(payload, null, 2));
  } catch (error) {
    setAnalysisOutput(`Analysis ${action} failed: ${error.message}`);
  }
}

function badgeClassForState(stateName) {
  switch (stateName) {
    case "merged":
      return "badge badge-merged";
    case "open":
      return "badge badge-open";
    case "closed":
      return "badge badge-closed";
    default:
      return "badge badge-none";
  }
}

function filterBranchRows(rows, filterText) {
  if (!filterText) return rows;
  const needle = filterText.toLowerCase();
  return rows.filter((row) => {
    const target = [row.repo, ...(row.repos || []), row.name, row.pr_title, row.pr_state, row.pr_base_ref]
      .filter(Boolean)
      .join(" ")
      .toLowerCase();
    return target.includes(needle);
  });
}

function filterSessionRows(rows, filterText) {
  if (!filterText) return rows;
  const needle = filterText.toLowerCase();
  return rows.filter((row) => {
    const target = [row.session_id, row.source, ...(row.branches || [])]
      .filter(Boolean)
      .join(" ")
      .toLowerCase();
    return target.includes(needle);
  });
}

function renderBranchTable() {
  const tbody = document.getElementById("branchTableBody");
  if (!tbody) return;

  const branches = (state.catalog?.branches || []).slice();
  const rows = filterBranchRows(branches, state.branchFilter).slice(0, MAX_BRANCH_ROWS);

  if (rows.length === 0) {
    tbody.innerHTML = '<tr><td colspan="8">No branches match this filter.</td></tr>';
    return;
  }

  tbody.innerHTML = rows
    .map((row) => {
      const prLabel = row.pr_number ? `#${row.pr_number}` : "-";
      const prLink = row.pr_url
        ? `<a href="${escapeHtml(row.pr_url)}" target="_blank" rel="noreferrer">${escapeHtml(prLabel)}</a>`
        : escapeHtml(prLabel);
      const prTitle = row.pr_title ? `<div>${escapeHtml(row.pr_title)}</div>` : "";
      const mergedOrClosed = row.pr_merged_at || row.pr_closed_at;
      const repoName = row.repo || "-";
      const repoExtra = Math.max(0, Number((row.repos || []).length) - (repoName === "-" ? 0 : 1));
      const repoLabel = repoExtra > 0 ? `${repoName} +${repoExtra}` : repoName;

      return `
        <tr>
          <td class="mono"><span class="truncate" title="${escapeHtml(repoLabel)}">${escapeHtml(repoLabel)}</span></td>
          <td class="mono"><span class="truncate" title="${escapeHtml(row.name || "")}">${escapeHtml(row.name || "")}</span></td>
          <td>${Number(row.session_count || 0).toLocaleString()}</td>
          <td>${prLink}${prTitle}</td>
          <td><span class="${badgeClassForState(row.pr_state)}">${escapeHtml(row.pr_state || "no_pr")}</span></td>
          <td>${escapeHtml(formatDate(mergedOrClosed))}</td>
          <td>
            <div>first: ${escapeHtml(formatDate(row.commit_first_at))}</div>
            <div>last: ${escapeHtml(formatDate(row.commit_last_at))}</div>
          </td>
          <td>
            <button type="button" class="ghost branch-action" data-branch="${escapeHtml(row.name || "")}" data-action="use">Use</button>
            <button type="button" class="ghost branch-action" data-branch="${escapeHtml(row.name || "")}" data-action="find">Find</button>
          </td>
        </tr>
      `;
    })
    .join("");
}

function renderSessionTable() {
  const tbody = document.getElementById("sessionTableBody");
  if (!tbody) return;

  const sessions = (state.catalog?.sessions || []).slice();
  const rows = filterSessionRows(sessions, state.sessionFilter).slice(0, MAX_SESSION_ROWS);

  if (rows.length === 0) {
    tbody.innerHTML = '<tr><td colspan="6">No sessions match this filter.</td></tr>';
    return;
  }

  tbody.innerHTML = rows
    .map((row) => {
      const branchTags = (row.branches || [])
        .slice(0, 6)
        .map((branch) => `<span class="tag mono">${escapeHtml(branch)}</span>`)
        .join("");
      const moreCount = Math.max(0, (row.branches || []).length - 6);
      const moreTag = moreCount > 0 ? `<span class="tag">+${moreCount} more</span>` : "";
      const sequence = Array.isArray(row.branch_sequence) ? row.branch_sequence.filter(Boolean) : [];
      const sequencePreview = sequence.slice(0, 6).join(" -> ");
      const hasSequenceContext = sequence.length > 1;
      const sequenceSuffix = sequence.length > 6 ? " -> ..." : "";
      const sequenceLine = hasSequenceContext
        ? `<div class="branch-sequence mono">${escapeHtml(`seq: ${sequencePreview}${sequenceSuffix}`)}</div>`
        : "";

      return `
        <tr>
          <td class="mono"><span class="truncate" title="${escapeHtml(row.session_id || "")}">${escapeHtml(row.session_id || "")}</span></td>
          <td>${escapeHtml(row.source || "")}</td>
          <td><span title="${escapeHtml(formatDate(row.started_at))}">${escapeHtml(formatDateCompact(row.started_at))}</span></td>
          <td><span title="${escapeHtml(formatDate(row.ended_at))}">${escapeHtml(formatDateCompact(row.ended_at))}</span></td>
          <td>${escapeHtml(formatBytes(row.size_bytes))}</td>
          <td><div class="branch-tags">${branchTags}${moreTag}</div>${sequenceLine}</td>
        </tr>
      `;
    })
    .join("");
}

function renderCatalogCards() {
  const catalog = state.catalog || {};
  const branches = catalog.branches || [];
  const mergedCount = branches.filter((row) => row.pr_state === "merged").length;
  const pendingCount = branches.filter((row) => row.pr_state === "pending_lookup").length;
  const resolvedCount = branches.length - pendingCount;

  const sessionsNode = document.getElementById("sessionsCount");
  const branchesNode = document.getElementById("branchesCount");
  const mergedNode = document.getElementById("mergedCount");
  const generatedNode = document.getElementById("generatedAt");

  if (sessionsNode) sessionsNode.textContent = Number(catalog.session_count || 0).toLocaleString();
  if (branchesNode) branchesNode.textContent = Number(catalog.branch_count || 0).toLocaleString();
  if (mergedNode) {
    if (pendingCount > 0 && resolvedCount === 0) {
      mergedNode.textContent = "—";
      mergedNode.title = "PR lookup not run yet. Click Refresh Branch Outcomes.";
    } else {
      mergedNode.textContent = Number(mergedCount).toLocaleString();
      mergedNode.title = "";
    }
  }
  if (generatedNode) generatedNode.textContent = formatDate(catalog.generated_at);
}

function renderCatalog() {
  renderCatalogCards();
  renderBranchTable();
  renderSessionTable();
}

function sleepMs(ms) {
  return new Promise((resolve) => {
    window.setTimeout(resolve, ms);
  });
}

function jobProgressText(job) {
  const message = job.message || "Loading catalog";
  const overall = Number(job.overall_percent || 0);
  return `${message} · ${overall.toFixed(1)}%`;
}

function updateProgressFromJob(job) {
  const overall = Number(job.overall_percent || 0);
  renderProgressBar(overall, jobProgressText(job));
}

async function runCatalogJob(refresh) {
  const started = await fetchJsonWithPayload("/api/catalog/jobs", { refresh });
  const jobId = started.job_id;
  if (!jobId) {
    throw new Error("Catalog job missing job_id");
  }

  for (let attempt = 0; attempt < 1200; attempt += 1) {
    const job = await fetchJson(`/api/catalog/jobs/${encodeURIComponent(jobId)}`);
    updateProgressFromJob(job);
    if (job.status === "completed") {
      return job.result;
    }
    if (job.status === "failed") {
      throw new Error(job.error || "Catalog job failed");
    }
    await sleepMs(250);
  }
  throw new Error("Catalog job timed out");
}

async function loadCatalog({ refresh }) {
  const phaseText = refresh ? "Refreshing catalog and branch outcomes" : "Loading catalog";
  setCatalogStatus(`${phaseText}...`);
  renderProgressBar(0, `${phaseText} · 0.0%`);
  try {
    const payload = await runCatalogJob(refresh);
    state.catalog = payload;
    renderCatalog();
    const pendingCount = (payload.branches || []).filter((row) => row.pr_state === "pending_lookup").length;
    const lookupNote =
      pendingCount > 0 ? ` (${pendingCount.toLocaleString()} PR states pending lookup)` : "";
    setCatalogStatus(
      `Catalog ready: ${Number(payload.session_count || 0).toLocaleString()} sessions, ${Number(payload.branch_count || 0).toLocaleString()} branches${lookupNote}.`,
    );
    renderProgressBar(100, "Catalog ready · 100.0%");
    window.setTimeout(() => {
      hideProgressBar();
    }, 250);
  } catch (error) {
    setCatalogStatus(`Catalog load failed: ${error.message}`, true);
    renderProgressBar(100, `Load failed: ${error.message}`);
  }
}

function bindCatalogControls() {
  const reloadBtn = document.getElementById("reloadCatalogBtn");
  const refreshBtn = document.getElementById("refreshCatalogBtn");
  const branchFilter = document.getElementById("branchFilter");
  const sessionFilter = document.getElementById("sessionFilter");

  if (reloadBtn) {
    reloadBtn.addEventListener("click", () => {
      void loadCatalog({ refresh: false });
    });
  }
  if (refreshBtn) {
    refreshBtn.addEventListener("click", () => {
      void loadCatalog({ refresh: true });
    });
  }
  if (branchFilter) {
    branchFilter.addEventListener("input", (event) => {
      state.branchFilter = event.target.value.trim();
      renderBranchTable();
    });
  }
  if (sessionFilter) {
    sessionFilter.addEventListener("input", (event) => {
      state.sessionFilter = event.target.value.trim();
      renderSessionTable();
    });
  }

  document.addEventListener("click", (event) => {
    const target = event.target;
    if (!(target instanceof HTMLElement)) return;
    if (!target.classList.contains("branch-action")) return;

    const branch = target.dataset.branch || "";
    const action = target.dataset.action || "";
    if (!branch) return;

    setAnalysisBranches([branch]);
    if (action === "find") {
      void runAnalysisAction("find");
    }
  });
}

function bindAnalysisControls() {
  const findBtn = document.getElementById("analysisFindBtn");
  const contextBtn = document.getElementById("analysisContextBtn");
  const runBtn = document.getElementById("analysisRunBtn");
  const branchInput = document.getElementById("analysisBranches");

  if (findBtn) findBtn.addEventListener("click", () => void runAnalysisAction("find"));
  if (contextBtn) contextBtn.addEventListener("click", () => void runAnalysisAction("context"));
  if (runBtn) runBtn.addEventListener("click", () => void runAnalysisAction("run"));

  if (branchInput) {
    branchInput.addEventListener("keydown", (event) => {
      if (event.key === "Enter") {
        event.preventDefault();
        void runAnalysisAction("find");
      }
    });
  }
}

async function initialize() {
  bindCatalogControls();
  bindAnalysisControls();
  await loadCatalog({ refresh: false });
}

void initialize();
