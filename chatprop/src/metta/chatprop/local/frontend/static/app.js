const MAX_BRANCH_ROWS = 500;
const MAX_SESSION_ROWS = 800;
const DEFAULT_FLOWCHART_OPTIONS = {
  minNodeCount: 1,
  minEdgeCount: 1,
  maxNodes: 120,
  maxEdges: 350,
};

const state = {
  catalog: null,
  branchFilter: "",
  sessionFilter: "",
  flowchart: {
    mermaid: "",
    selectedGraph: null,
    options: { ...DEFAULT_FLOWCHART_OPTIONS },
  },
};

let mermaidClientPromise = null;

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

function formatConfidenceRange(low, high) {
  const lowNumber = Number(low);
  const highNumber = Number(high);
  if (!Number.isFinite(lowNumber) || !Number.isFinite(highNumber)) return "-";
  return `${lowNumber.toFixed(2)}-${highNumber.toFixed(2)}`;
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

function setFlowchartStatus(text, isError = false) {
  const node = document.getElementById("flowchartStatus");
  if (!node) return;
  node.textContent = text;
  if (isError) {
    node.classList.add("error");
  } else {
    node.classList.remove("error");
  }
}

function setUploadStatus(text, isError = false) {
  const node = document.getElementById("uploadStatus");
  if (!node) return;
  node.textContent = text;
  if (isError) {
    node.classList.add("error");
  } else {
    node.classList.remove("error");
  }
}

function setDendrogramStatus(text, isError = false) {
  const node = document.getElementById("dendrogramStatus");
  if (!node) return;
  node.textContent = text;
  if (isError) {
    node.classList.add("error");
  } else {
    node.classList.remove("error");
  }
}

function parseBoundedInt(rawValue, fallback, minValue, maxValue) {
  const value = Number.parseInt(String(rawValue ?? ""), 10);
  if (!Number.isFinite(value)) return fallback;
  return Math.max(minValue, Math.min(maxValue, value));
}

function readFlowchartOptions() {
  const minNodeInput = document.getElementById("flowchartMinNodeCount");
  const minEdgeInput = document.getElementById("flowchartMinEdgeCount");
  const maxNodesInput = document.getElementById("flowchartMaxNodes");
  const maxEdgesInput = document.getElementById("flowchartMaxEdges");
  const minNodeCount = parseBoundedInt(
    minNodeInput ? minNodeInput.value : DEFAULT_FLOWCHART_OPTIONS.minNodeCount,
    DEFAULT_FLOWCHART_OPTIONS.minNodeCount,
    1,
    100000,
  );
  const minEdgeCount = parseBoundedInt(
    minEdgeInput ? minEdgeInput.value : DEFAULT_FLOWCHART_OPTIONS.minEdgeCount,
    DEFAULT_FLOWCHART_OPTIONS.minEdgeCount,
    1,
    100000,
  );
  const maxNodes = parseBoundedInt(
    maxNodesInput ? maxNodesInput.value : DEFAULT_FLOWCHART_OPTIONS.maxNodes,
    DEFAULT_FLOWCHART_OPTIONS.maxNodes,
    1,
    10000,
  );
  const maxEdges = parseBoundedInt(
    maxEdgesInput ? maxEdgesInput.value : DEFAULT_FLOWCHART_OPTIONS.maxEdges,
    DEFAULT_FLOWCHART_OPTIONS.maxEdges,
    1,
    20000,
  );
  const options = { minNodeCount, minEdgeCount, maxNodes, maxEdges };
  state.flowchart.options = options;
  return options;
}

function flowchartRequestPayload(options) {
  return {
    workflow_graph: state.catalog?.workflow_graph || {},
    min_node_count: options.minNodeCount,
    min_edge_count: options.minEdgeCount,
    max_nodes: options.maxNodes,
    max_edges: options.maxEdges,
  };
}

function renderFlowchartSummary(selectedGraph) {
  const node = document.getElementById("flowchartSummary");
  if (!node) return;
  const nodeCount = Number(selectedGraph?.node_count || 0).toLocaleString();
  const edgeCount = Number(selectedGraph?.edge_count || 0).toLocaleString();
  const graphScope = selectedGraph?.graph_scope || "unknown_scope";
  const revisionScope = selectedGraph?.revision_prevention_scope || "unknown_scope";
  node.textContent = `nodes=${nodeCount} edges=${edgeCount} | ${graphScope} | ${revisionScope}`;
}

function renderFlowchartSource(mermaidText) {
  const node = document.getElementById("flowchartSource");
  if (!node) return;
  node.textContent = mermaidText || "";
}

async function ensureMermaidClient() {
  if (!mermaidClientPromise) {
    mermaidClientPromise = import("https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.esm.min.mjs").then(
      (module) => {
        const mermaid = module.default;
        mermaid.initialize({
          startOnLoad: false,
          securityLevel: "loose",
          flowchart: { htmlLabels: true, useMaxWidth: false },
        });
        return mermaid;
      },
    );
  }
  return mermaidClientPromise;
}

async function renderMermaidCanvas({ canvasId, mermaidText, emptyMessage, renderPrefix }) {
  const canvas = document.getElementById(canvasId);
  if (!canvas) return;
  if (!mermaidText) {
    canvas.innerHTML = `<div class="hint-line">${escapeHtml(emptyMessage)}</div>`;
    return;
  }

  try {
    const mermaid = await ensureMermaidClient();
    const renderId = `${renderPrefix}_${Date.now()}_${Math.floor(Math.random() * 10000)}`;
    const rendered = await mermaid.render(renderId, mermaidText);
    canvas.innerHTML = rendered.svg;
  } catch (error) {
    canvas.innerHTML = `<pre>${escapeHtml(mermaidText)}</pre>`;
    throw error;
  }
}

async function renderFlowchartCanvas(mermaidText) {
  await renderMermaidCanvas({
    canvasId: "flowchartCanvas",
    mermaidText,
    emptyMessage: "No flowchart data yet.",
    renderPrefix: "chatprop_flowchart",
  });
}

function applyFlowchartPayload(payload) {
  state.flowchart.mermaid = payload?.mermaid || "";
  state.flowchart.selectedGraph = payload?.selected_graph || null;
  renderFlowchartSummary(state.flowchart.selectedGraph);
  renderFlowchartSource(state.flowchart.mermaid);
}

async function renderFlowchartFromCatalog() {
  const graph = state.catalog?.workflow_graph;
  if (!graph || typeof graph !== "object") {
    setFlowchartStatus("Flowchart unavailable: workflow graph missing.", true);
    return;
  }

  const cachedPayload = state.catalog?.workflow_flowchart;
  if (cachedPayload && typeof cachedPayload === "object" && typeof cachedPayload.mermaid === "string") {
    applyFlowchartPayload(cachedPayload);
    try {
      await renderFlowchartCanvas(state.flowchart.mermaid);
      setFlowchartStatus(
        `Flowchart ready: ${Number(state.flowchart.selectedGraph?.node_count || 0).toLocaleString()} nodes, ${Number(state.flowchart.selectedGraph?.edge_count || 0).toLocaleString()} edges.`,
      );
    } catch (error) {
      setFlowchartStatus(`Flowchart rendered as Mermaid text fallback: ${error.message}`, true);
    }
    return;
  }

  await renderFlowchartWithCurrentOptions();
}

async function renderFlowchartWithCurrentOptions() {
  const graph = state.catalog?.workflow_graph;
  if (!graph || typeof graph !== "object") {
    setFlowchartStatus("Load catalog first to render flowchart.", true);
    return;
  }

  const options = readFlowchartOptions();
  setFlowchartStatus("Rendering flowchart...");
  try {
    const payload = await fetchJsonWithPayload("/api/flowchart/render", flowchartRequestPayload(options));
    applyFlowchartPayload(payload);
    await renderFlowchartCanvas(state.flowchart.mermaid);
    setFlowchartStatus(
      `Flowchart ready: ${Number(payload.selected_graph?.node_count || 0).toLocaleString()} nodes, ${Number(payload.selected_graph?.edge_count || 0).toLocaleString()} edges.`,
    );
  } catch (error) {
    setFlowchartStatus(`Flowchart render failed: ${error.message}`, true);
  }
}

async function saveFlowchartArtifacts() {
  const graph = state.catalog?.workflow_graph;
  if (!graph || typeof graph !== "object") {
    setFlowchartStatus("Load catalog first before saving flowchart.", true);
    return;
  }

  const options = readFlowchartOptions();
  const mermaidPathInput = document.getElementById("flowchartMermaidPath");
  const jsonPathInput = document.getElementById("flowchartJsonPath");
  const mermaidPath = mermaidPathInput ? mermaidPathInput.value.trim() : "";
  const jsonPath = jsonPathInput ? jsonPathInput.value.trim() : "";

  setFlowchartStatus("Saving flowchart artifacts...");
  try {
    const payload = await fetchJsonWithPayload("/api/flowchart/save", {
      ...flowchartRequestPayload(options),
      mermaid_path: mermaidPath,
      json_path: jsonPath,
    });
    setFlowchartStatus(
      `Saved flowchart: ${payload.mermaid_path}${payload.json_path ? ` | ${payload.json_path}` : ""}`,
    );
  } catch (error) {
    setFlowchartStatus(`Flowchart save failed: ${error.message}`, true);
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
          <td>
            <div>${Number(row.session_count || 0).toLocaleString()}</div>
            <div class="metrics-line">features: ${Number(row.feature_count || 0).toLocaleString()} | revisions: ${Number(row.revision_feature_count || 0).toLocaleString()}</div>
          </td>
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
      const featureCount = Number(row.feature_count || 0);
      const revisionFeatureCount = Number(row.revision_feature_count || 0);
      const featureLine =
        featureCount > 0
          ? `<div class="metrics-line">features: ${featureCount.toLocaleString()} | revisions: ${revisionFeatureCount.toLocaleString()}</div>`
          : "";

      return `
        <tr>
          <td class="mono"><span class="truncate" title="${escapeHtml(row.session_id || "")}">${escapeHtml(row.session_id || "")}</span></td>
          <td>${escapeHtml(row.source || "")}</td>
          <td><span title="${escapeHtml(formatDate(row.started_at))}">${escapeHtml(formatDateCompact(row.started_at))}</span></td>
          <td><span title="${escapeHtml(formatDate(row.ended_at))}">${escapeHtml(formatDateCompact(row.ended_at))}</span></td>
          <td>${escapeHtml(formatBytes(row.size_bytes))}</td>
          <td><div class="branch-tags">${branchTags}${moreTag}</div>${sequenceLine}${featureLine}</td>
        </tr>
      `;
    })
    .join("");
}

function renderWorkflowGraphPanel() {
  const summaryNode = document.getElementById("workflowSummary");
  const nodeBody = document.getElementById("skillNodesBody");
  const edgeBody = document.getElementById("skillEdgesBody");
  const hintBody = document.getElementById("revisionHintsBody");
  if (!summaryNode || !nodeBody || !edgeBody || !hintBody) return;

  const graph = state.catalog?.workflow_graph || {};
  const nodes = Array.isArray(graph.nodes) ? graph.nodes.slice() : [];
  const edges = Array.isArray(graph.edges) ? graph.edges.slice() : [];
  const hints = Array.isArray(graph.revision_prevention) ? graph.revision_prevention.slice() : [];
  const nodeCount = Number(graph.node_count || 0);
  const edgeCount = Number(graph.edge_count || 0);
  const graphScope = graph.graph_scope || "unknown_scope";
  const revisionScope = graph.revision_prevention_scope || "unknown_scope";
  summaryNode.textContent = `nodes=${nodeCount.toLocaleString()} edges=${edgeCount.toLocaleString()} | ${graphScope} | ${revisionScope}`;

  const topNodes = nodes.sort((a, b) => Number(b.count || 0) - Number(a.count || 0)).slice(0, 18);
  if (topNodes.length === 0) {
    nodeBody.innerHTML = '<tr><td colspan="4">No skill nodes inferred yet.</td></tr>';
  } else {
    nodeBody.innerHTML = topNodes
      .map((node) => {
        const label = node.label || node.id || "-";
        const kind = node.kind || "-";
        const count = Number(node.count || 0).toLocaleString();
        const confidence = formatConfidenceRange(node.confidence_low, node.confidence_high);
        const args = Array.isArray(node.argument_samples) ? node.argument_samples.slice(0, 2).join(", ") : "";
        const argsLine = args ? `<div class="hint-line mono">args: ${escapeHtml(args)}</div>` : "";
        return `
          <tr>
            <td><span class="mono truncate" title="${escapeHtml(label)}">${escapeHtml(label)}</span>${argsLine}</td>
            <td>${escapeHtml(kind)}</td>
            <td>${escapeHtml(count)}</td>
            <td>${escapeHtml(confidence)}</td>
          </tr>
        `;
      })
      .join("");
  }

  const topEdges = edges.sort((a, b) => Number(b.count || 0) - Number(a.count || 0)).slice(0, 18);
  if (topEdges.length === 0) {
    edgeBody.innerHTML = '<tr><td colspan="3">No skill edges inferred yet.</td></tr>';
  } else {
    edgeBody.innerHTML = topEdges
      .map((edge) => {
        const source = edge.source || "-";
        const target = edge.target || "-";
        const pair = `${source} -> ${target}`;
        const phase = edge.phase || "-";
        const count = Number(edge.count || 0).toLocaleString();
        return `
          <tr>
            <td><span class="mono truncate" title="${escapeHtml(pair)}">${escapeHtml(pair)}</span></td>
            <td>${escapeHtml(phase)}</td>
            <td>${escapeHtml(count)}</td>
          </tr>
        `;
      })
      .join("");
  }

  const topHints = hints.sort((a, b) => Number(b.count || 0) - Number(a.count || 0)).slice(0, 25);
  if (topHints.length === 0) {
    hintBody.innerHTML = '<tr><td colspan="4">No revision-prevention suggestions yet.</td></tr>';
  } else {
    hintBody.innerHTML = topHints
      .map((hint) => {
        const planningSkill = hint.planning_skill || "-";
        const revisionSkill = hint.revision_skill || "-";
        const count = Number(hint.count || 0).toLocaleString();
        const adjustment = hint.suggested_adjustment || "-";
        const branches = Array.isArray(hint.example_branches) ? hint.example_branches.slice(0, 3).join(", ") : "";
        const hintLine = branches ? `<div class="hint-line mono">branches: ${escapeHtml(branches)}</div>` : "";
        return `
          <tr>
            <td><span class="mono truncate" title="${escapeHtml(planningSkill)}">${escapeHtml(planningSkill)}</span></td>
            <td><span class="mono truncate" title="${escapeHtml(revisionSkill)}">${escapeHtml(revisionSkill)}</span></td>
            <td>${escapeHtml(count)}</td>
            <td>${escapeHtml(adjustment)}${hintLine}</td>
          </tr>
        `;
      })
      .join("");
  }
}

function renderUploadTable() {
  const summaryNode = document.getElementById("uploadSummary");
  const body = document.getElementById("uploadSnapshotsBody");
  if (!summaryNode || !body) return;

  const uploads = Array.isArray(state.catalog?.uploaded_snapshots) ? state.catalog.uploaded_snapshots.slice() : [];
  summaryNode.textContent = `${uploads.length.toLocaleString()} snapshots`;

  if (uploads.length === 0) {
    body.innerHTML = '<tr><td colspan="6">No uploaded snapshots yet.</td></tr>';
    return;
  }

  body.innerHTML = uploads
    .map((upload) => {
      const name = upload.name || "uploaded snapshot";
      const uploadedAt = upload.uploaded_at || "-";
      const sessionCount = Number(upload.session_count || 0).toLocaleString();
      const branchCount = Number(upload.branch_count || 0).toLocaleString();
      const nodeCount = Number(upload.node_count || 0).toLocaleString();
      const edgeCount = Number(upload.edge_count || 0).toLocaleString();
      return `
        <tr>
          <td><span class="truncate" title="${escapeHtml(name)}">${escapeHtml(name)}</span></td>
          <td><span title="${escapeHtml(formatDate(uploadedAt))}">${escapeHtml(formatDateCompact(uploadedAt))}</span></td>
          <td>${escapeHtml(sessionCount)}</td>
          <td>${escapeHtml(branchCount)}</td>
          <td>${escapeHtml(nodeCount)}</td>
          <td>${escapeHtml(edgeCount)}</td>
        </tr>
      `;
    })
    .join("");
}

function renderDendrogramSummary(payload) {
  const summaryNode = document.getElementById("dendrogramSummary");
  if (!summaryNode) return;
  const skillCount = Number(payload?.skill_count || 0).toLocaleString();
  const nodeCount = Number(payload?.node_count || 0).toLocaleString();
  const edgeCount = Number(payload?.edge_count || 0).toLocaleString();
  summaryNode.textContent = `skills=${skillCount} nodes=${nodeCount} edges=${edgeCount}`;
}

function renderDendrogramSource(mermaidText) {
  const node = document.getElementById("dendrogramSource");
  if (!node) return;
  node.textContent = mermaidText || "";
}

async function renderDendrogramFromCatalog() {
  const payload = state.catalog?.skill_dendrogram;
  if (!payload || typeof payload !== "object") {
    renderDendrogramSummary(null);
    renderDendrogramSource("");
    setDendrogramStatus("Dendrogram unavailable: no explicit skill graph.");
    await renderMermaidCanvas({
      canvasId: "dendrogramCanvas",
      mermaidText: "",
      emptyMessage: "No dendrogram data yet.",
      renderPrefix: "chatprop_dendrogram",
    });
    return;
  }

  const mermaidText = typeof payload.mermaid === "string" ? payload.mermaid : "";
  renderDendrogramSummary(payload);
  renderDendrogramSource(mermaidText);
  try {
    await renderMermaidCanvas({
      canvasId: "dendrogramCanvas",
      mermaidText,
      emptyMessage: "No dendrogram data yet.",
      renderPrefix: "chatprop_dendrogram",
    });
    setDendrogramStatus(
      `Dendrogram ready: ${Number(payload.skill_count || 0).toLocaleString()} skills in ${Number(payload.node_count || 0).toLocaleString()} nodes.`,
    );
  } catch (error) {
    setDendrogramStatus(`Dendrogram rendered as Mermaid text fallback: ${error.message}`, true);
  }
}

function renderCatalogCards() {
  const catalog = state.catalog || {};
  const branches = catalog.branches || [];
  const mergedCount = branches.filter((row) => row.pr_state === "merged").length;
  const pendingCount = branches.filter((row) => row.pr_state === "pending_lookup").length;
  const resolvedCount = branches.length - pendingCount;

  const sessionsNode = document.getElementById("sessionsCount");
  const branchesNode = document.getElementById("branchesCount");
  const uploadsNode = document.getElementById("uploadedSnapshotCount");
  const mergedNode = document.getElementById("mergedCount");
  const generatedNode = document.getElementById("generatedAt");

  const totalSessions = Number(catalog.session_count || 0);
  const totalBranches = Number(catalog.branch_count || 0);
  const localSessions = Number(catalog.local_session_count || totalSessions);
  const localBranches = Number(catalog.local_branch_count || totalBranches);
  const uploadedSessions = Number(catalog.uploaded_session_count || 0);
  const uploadedBranches = Number(catalog.uploaded_branch_count || 0);
  const uploadCount = Number(catalog.uploaded_snapshot_count || 0);

  if (sessionsNode) {
    sessionsNode.textContent = totalSessions.toLocaleString();
    sessionsNode.title = uploadedSessions > 0 ? `${localSessions.toLocaleString()} local + ${uploadedSessions.toLocaleString()} uploaded` : "";
  }
  if (branchesNode) {
    branchesNode.textContent = totalBranches.toLocaleString();
    branchesNode.title = uploadedBranches > 0 ? `${localBranches.toLocaleString()} local + ${uploadedBranches.toLocaleString()} uploaded` : "";
  }
  if (uploadsNode) uploadsNode.textContent = uploadCount.toLocaleString();
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
  renderWorkflowGraphPanel();
  renderUploadTable();
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
    await renderFlowchartFromCatalog();
    await renderDendrogramFromCatalog();
    const pendingCount = (payload.branches || []).filter((row) => row.pr_state === "pending_lookup").length;
    const lookupNote =
      pendingCount > 0 ? ` (${pendingCount.toLocaleString()} PR states pending lookup)` : "";
    const uploadedCount = Number(payload.uploaded_snapshot_count || 0);
    const uploadNote = uploadedCount > 0 ? ` (${uploadedCount.toLocaleString()} uploaded snapshots)` : "";
    setCatalogStatus(
      `Catalog ready: ${Number(payload.session_count || 0).toLocaleString()} sessions, ${Number(payload.branch_count || 0).toLocaleString()} branches${lookupNote}${uploadNote}.`,
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

async function uploadSnapshotFromFile() {
  const fileInput = document.getElementById("uploadSnapshotFile");
  const nameInput = document.getElementById("uploadSnapshotName");
  if (!(fileInput instanceof HTMLInputElement) || !(nameInput instanceof HTMLInputElement)) {
    return;
  }
  const file = fileInput.files?.[0];
  if (!file) {
    setUploadStatus("Select a JSON snapshot file first.", true);
    return;
  }

  setUploadStatus(`Uploading ${file.name}...`);
  try {
    const raw = await file.text();
    const parsed = JSON.parse(raw);
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
      throw new Error("Snapshot file must contain a JSON object.");
    }

    const optionalName = nameInput.value.trim();
    const payload = optionalName.length > 0 ? { name: optionalName, snapshot: parsed } : { snapshot: parsed };
    const response = await fetchJsonWithPayload("/api/uploads", payload);
    const uploaded = response?.uploaded || {};
    const uploadedName = uploaded.name || optionalName || file.name;
    setUploadStatus(`Uploaded ${uploadedName}. Refreshing catalog...`);
    fileInput.value = "";
    await loadCatalog({ refresh: false });
    setUploadStatus(`Uploaded ${uploadedName}.`);
  } catch (error) {
    setUploadStatus(`Upload failed: ${error.message}`, true);
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

function bindUploadControls() {
  const uploadBtn = document.getElementById("uploadSnapshotBtn");
  const fileInput = document.getElementById("uploadSnapshotFile");
  const nameInput = document.getElementById("uploadSnapshotName");

  if (uploadBtn) {
    uploadBtn.addEventListener("click", () => {
      void uploadSnapshotFromFile();
    });
  }
  if (fileInput) {
    fileInput.addEventListener("change", () => {
      const element = fileInput;
      if (!(element instanceof HTMLInputElement)) return;
      if (element.files?.length) {
        setUploadStatus(`Ready to upload ${element.files[0].name}.`);
      }
    });
  }
  if (nameInput) {
    nameInput.addEventListener("keydown", (event) => {
      if (event.key === "Enter") {
        event.preventDefault();
        void uploadSnapshotFromFile();
      }
    });
  }
}

function bindFlowchartControls() {
  const renderBtn = document.getElementById("flowchartRenderBtn");
  const saveBtn = document.getElementById("flowchartSaveBtn");
  const optionInputs = [
    document.getElementById("flowchartMinNodeCount"),
    document.getElementById("flowchartMinEdgeCount"),
    document.getElementById("flowchartMaxNodes"),
    document.getElementById("flowchartMaxEdges"),
  ];

  if (renderBtn) {
    renderBtn.addEventListener("click", () => {
      void renderFlowchartWithCurrentOptions();
    });
  }
  if (saveBtn) {
    saveBtn.addEventListener("click", () => {
      void saveFlowchartArtifacts();
    });
  }

  optionInputs.forEach((input) => {
    if (!input) return;
    input.addEventListener("keydown", (event) => {
      if (event.key === "Enter") {
        event.preventDefault();
        void renderFlowchartWithCurrentOptions();
      }
    });
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
  bindUploadControls();
  bindFlowchartControls();
  bindAnalysisControls();
  await loadCatalog({ refresh: false });
}

void initialize();
