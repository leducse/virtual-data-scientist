const state = {
  schema: null,
  serviceStatus: null,
  report: null,
  previews: {},
  activeBlockId: null,
  selectedDataSourceId: "demo_warehouse",
  analysis: {
    session: null,
    dataset: null,
    lightRun: null,
    deepRun: null,
    profile: null,
    artifacts: [],
    pollTimer: null,
  },
};

const view = document.body.dataset.view;

function $(selector, root = document) {
  return root.querySelector(selector);
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  const payload = await response.json();
  if (!response.ok || payload.ok === false) {
    throw new Error(payload.error || `Request failed: ${response.status}`);
  }
  return payload;
}

function showToast(message) {
  const toast = $("#toast");
  if (!toast) return;
  toast.textContent = message;
  toast.classList.remove("hidden");
  window.clearTimeout(showToast.timeout);
  showToast.timeout = window.setTimeout(() => {
    toast.classList.add("hidden");
  }, 3600);
}

function formatValue(key, value) {
  if (value === null || value === undefined) return "-";
  if (typeof value === "number") {
    const lower = String(key).toLowerCase();
    if (lower.includes("pct") || lower.includes("rate")) return `${value.toFixed(1)}%`;
    if (lower.includes("revenue") || lower.includes("margin") || lower.includes("target")) {
      return new Intl.NumberFormat("en-US", {
        style: "currency",
        currency: "USD",
        maximumFractionDigits: 0,
      }).format(value);
    }
    return new Intl.NumberFormat("en-US", { maximumFractionDigits: 1 }).format(value);
  }
  return String(value);
}

function humanize(key) {
  return String(key)
    .replaceAll("_", " ")
    .replace(/\b\w/g, (char) => char.toUpperCase());
}

function currentParameters(report = state.report) {
  if (!report) return {};
  return Object.fromEntries(
    report.parameters.map((param) => [param.name, param.value ?? param.default])
  );
}

async function loadServiceStatus() {
  state.serviceStatus = await api("/api/config/status");
  renderServiceStatus();
}

async function loadSchema(dataSourceId = state.selectedDataSourceId) {
  state.selectedDataSourceId = dataSourceId || "demo_warehouse";
  state.schema = await api(`/api/schema?data_source_id=${encodeURIComponent(state.selectedDataSourceId)}`);
  state.selectedDataSourceId = state.schema.active_data_source_id || state.selectedDataSourceId;
  renderSchema();
  renderAnalysisTableOptions();
}

function renderSchema() {
  const sourceList = $("#data-source-list");
  const schemaList = $("#schema-list");
  if (!sourceList || !schemaList || !state.schema) return;

  const selector = $("#data-source-select");
  if (selector) {
    selector.innerHTML = state.schema.data_sources
      .map(
        (source) => `
          <option value="${escapeHtml(source.id)}" ${
            source.id === state.selectedDataSourceId ? "selected" : ""
          }>${escapeHtml(source.name)}</option>
        `
      )
      .join("");
  }

  sourceList.innerHTML = state.schema.data_sources
    .map(
      (source) => `
        <div class="data-source-card ${source.id === state.selectedDataSourceId ? "active" : ""}">
          <strong>${escapeHtml(source.name)}</strong>
          <span>${escapeHtml(source.type)} · ${source.read_only ? "read only" : "write capable"} · ${
            source.real_service ? "real" : "local"
          }</span>
        </div>
      `
    )
    .join("");

  schemaList.innerHTML = state.schema.tables
    .map(
      (table) => {
        const rowCount =
          typeof table.row_count === "number" ? `${table.row_count.toLocaleString()} rows` : "row count not loaded";
        return `
        <details class="schema-card">
          <summary>${escapeHtml(table.name)}</summary>
          <small>${escapeHtml(rowCount)}</small>
          <div class="schema-columns">
            ${table.columns
              .map(
                (column) => `
                  <div class="schema-column">
                    <code>${escapeHtml(column.name)}</code>
                    <span>${escapeHtml(column.type)}</span>
                  </div>
                `
              )
              .join("")}
          </div>
        </details>
      `;
      }
    )
    .join("");

  renderAnalysisTableOptions();
}

function renderAnalysisTableOptions() {
  const selector = $("#analysis-table-select");
  if (!selector || !state.schema) return;
  const current = selector.value;
  const options = [
    `<option value="">All visible tables</option>`,
    ...state.schema.tables.map(
      (table) => `<option value="${escapeHtml(table.name)}">${escapeHtml(table.name)}</option>`
    ),
  ];
  selector.innerHTML = options.join("");
  if ([...selector.options].some((option) => option.value === current)) {
    selector.value = current;
  }
}

function renderServiceStatus() {
  const container = $("#service-status-list");
  if (!container || !state.serviceStatus) return;
  const items = [
    ["Bedrock", state.serviceStatus.bedrock.available, state.serviceStatus.bedrock.model_id || state.serviceStatus.bedrock.dependency],
    ["Postgres", state.serviceStatus.postgres.available, state.serviceStatus.postgres.dependency],
    ["S3", state.serviceStatus.s3.available, state.serviceStatus.s3.bucket || state.serviceStatus.s3.dependency],
  ];
  container.innerHTML = items
    .map(
      ([name, ready, detail]) => `
        <div class="service-card ${ready ? "ready" : "missing"}">
          <strong>${escapeHtml(name)}</strong>
          <span>${escapeHtml(ready ? "available" : "not configured")} · ${escapeHtml(detail || "")}</span>
        </div>
      `
    )
    .join("");
}

function addChatMessage(role, text) {
  const feed = $("#chat-feed");
  if (!feed) return;
  const message = document.createElement("div");
  message.className = `chat-message ${role}`;
  message.textContent = text;
  feed.appendChild(message);
  feed.scrollTop = feed.scrollHeight;
}

function setAgentState(text, tone = "") {
  const pill = $("#agent-state");
  if (!pill) return;
  pill.textContent = text;
  pill.className = `pill ${tone}`.trim();
}

function setAnalysisSessionPill(text, tone = "muted") {
  const pill = $("#analysis-session-pill");
  if (!pill) return;
  pill.textContent = text;
  pill.className = `pill ${tone}`.trim();
}

function selectedAnalysisQuestion() {
  return $("#analysis-question")?.value.trim() || "Explore this dataset.";
}

function selectedAnalysisTable() {
  return $("#analysis-table-select")?.value || "";
}

async function ensureAnalysisSession() {
  if (state.analysis.session) return state.analysis.session;
  const sessionResult = await api("/api/analysis/sessions", {
    method: "POST",
    body: JSON.stringify({
      user_goal: selectedAnalysisQuestion(),
      data_source_id: state.selectedDataSourceId,
      table_name: selectedAnalysisTable() || null,
    }),
  });
  state.analysis.session = sessionResult.session;
  setAnalysisSessionPill("Session active");
  return state.analysis.session;
}

function mergeArtifacts(artifacts) {
  const byId = new Map(state.analysis.artifacts.map((artifact) => [artifact.id, artifact]));
  for (const artifact of artifacts || []) {
    byId.set(artifact.id, artifact);
  }
  state.analysis.artifacts = [...byId.values()].sort((a, b) =>
    String(b.created_at || "").localeCompare(String(a.created_at || ""))
  );
}

async function runLightAnalysis() {
  const button = $("#light-analysis-button");
  button.disabled = true;
  setAnalysisSessionPill("Light running", "warn");
  renderAnalysisOutput({ loading: "Profiling data and generating code artifact." });

  try {
    const session = await ensureAnalysisSession();
    const result = await api("/api/analysis/light", {
      method: "POST",
      body: JSON.stringify({
        session_id: session.id,
        user_question: selectedAnalysisQuestion(),
        data_source_id: state.selectedDataSourceId,
        table_name: selectedAnalysisTable() || null,
      }),
    });
    state.analysis.session = result.session;
    state.analysis.dataset = result.dataset;
    state.analysis.lightRun = result.run;
    state.analysis.profile = result.profile;
    mergeArtifacts(result.artifacts);
    setAnalysisSessionPill("Light complete");
    renderAnalysisOutput();
    addChatMessage(
      "agent",
      `Light analysis completed for ${result.profile.table_name}. Saved ${result.artifacts.length} artifacts.`
    );
  } catch (error) {
    setAnalysisSessionPill("Analysis error", "warn");
    renderAnalysisOutput({ error: error.message });
    showToast(error.message);
  } finally {
    button.disabled = false;
  }
}

async function requestDeepAnalysis() {
  const button = $("#deep-analysis-button");
  button.disabled = true;
  try {
    const session = await ensureAnalysisSession();
    if (!state.analysis.lightRun) {
      await runLightAnalysis();
      if (!state.analysis.lightRun) {
        throw new Error("Run light analysis successfully before requesting deep analysis.");
      }
    }
    const result = await api("/api/analysis/deep", {
      method: "POST",
      body: JSON.stringify({
        session_id: session.id,
        user_question: selectedAnalysisQuestion(),
        constraints: {
          max_runtime_minutes: 15,
          privacy_mode: "registered_dataset_only",
        },
      }),
    });
    state.analysis.deepRun = result.run;
    mergeArtifacts(result.artifacts);
    setAnalysisSessionPill("Deep queued", "warn");
    renderAnalysisOutput();
    startDeepRunPolling(result.run.id);
  } catch (error) {
    setAnalysisSessionPill("Deep error", "warn");
    renderAnalysisOutput({ error: error.message });
    showToast(error.message);
  } finally {
    button.disabled = false;
  }
}

function startDeepRunPolling(runId) {
  if (state.analysis.pollTimer) {
    window.clearInterval(state.analysis.pollTimer);
  }
  state.analysis.pollTimer = window.setInterval(async () => {
    try {
      const result = await api(`/api/analysis/runs/${encodeURIComponent(runId)}`);
      state.analysis.deepRun = result.run;
      mergeArtifacts(result.artifacts);
      if (["succeeded", "failed", "cancelled"].includes(result.run.status)) {
        window.clearInterval(state.analysis.pollTimer);
        state.analysis.pollTimer = null;
        setAnalysisSessionPill(result.run.status === "succeeded" ? "Deep complete" : "Deep stopped");
      } else {
        setAnalysisSessionPill(`Deep ${result.run.status}`, "warn");
      }
      renderAnalysisOutput();
    } catch (error) {
      window.clearInterval(state.analysis.pollTimer);
      state.analysis.pollTimer = null;
      setAnalysisSessionPill("Polling error", "warn");
      showToast(error.message);
    }
  }, 1000);
}

function renderAnalysisOutput(status = {}) {
  const container = $("#analysis-output");
  if (!container) return;
  container.classList.remove("empty-state");

  if (status.loading) {
    container.innerHTML = `<p class="analysis-note">${escapeHtml(status.loading)}</p>`;
    return;
  }
  if (status.error) {
    container.innerHTML = `<div class="error-box">${escapeHtml(status.error)}</div>`;
    return;
  }

  const profile = state.analysis.profile;
  const deepRun = state.analysis.deepRun;
  if (!profile && !deepRun) {
    container.classList.add("empty-state");
    container.innerHTML = "<p>Run light analysis to create a profile, code artifact, and method suggestions.</p>";
    return;
  }

  const methods = profile?.candidate_methods || [];
  const warnings = profile?.warnings || [];
  const tables = profile?.tables || [];
  const artifacts = state.analysis.artifacts || [];

  container.innerHTML = `
    ${
      profile
        ? `
          <div class="analysis-summary-grid">
            <div class="analysis-metric">
              <strong>${escapeHtml(profile.table_count || tables.length)}</strong>
              <span>tables</span>
            </div>
            <div class="analysis-metric">
              <strong>${escapeHtml(
                tables.reduce((total, table) => total + Number(table.row_count || 0), 0).toLocaleString()
              )}</strong>
              <span>rows profiled</span>
            </div>
            <div class="analysis-metric">
              <strong>${escapeHtml(methods.length)}</strong>
              <span>candidate paths</span>
            </div>
          </div>
          <div class="analysis-section">
            <h5>Candidate Methods</h5>
            <ul>
              ${methods
                .map((method) => `<li><strong>${escapeHtml(humanize(method.type))}</strong>: ${escapeHtml(method.reason)}</li>`)
                .join("")}
            </ul>
          </div>
          ${
            warnings.length
              ? `<div class="analysis-section warn-section">
                  <h5>Warnings</h5>
                  <ul>${warnings.map((warning) => `<li>${escapeHtml(warning)}</li>`).join("")}</ul>
                </div>`
              : ""
          }
        `
        : ""
    }
    ${
      deepRun
        ? `<div class="analysis-section">
            <h5>Deep Analysis</h5>
            <p>Status: <strong>${escapeHtml(deepRun.status)}</strong></p>
            <p class="muted-text">Run ID: ${escapeHtml(deepRun.id)}</p>
          </div>`
        : ""
    }
    <div class="analysis-section">
      <h5>Artifacts</h5>
      <div class="artifact-list">
        ${
          artifacts.length
            ? artifacts.map(renderArtifactCard).join("")
            : `<p class="muted-text">No artifacts yet.</p>`
        }
      </div>
    </div>
  `;
}

function renderArtifactCard(artifact) {
  const content = artifact.content;
  let preview = artifact.summary || "";
  if (typeof content === "string") {
    preview = content.slice(0, 420);
  } else if (content && artifact.artifact_type === "context_bundle") {
    preview = `Dataset: ${content.dataset_id || "pending"} · Light code: ${
      content.light_analysis_code_id || "missing"
    }`;
  } else if (content && artifact.artifact_type === "profile") {
    preview = `${content.table_count || content.tables?.length || 0} table(s), ${
      content.candidate_methods?.length || 0
    } candidate analysis path(s).`;
  } else if (content && artifact.artifact_type === "report") {
    preview = content.summary || artifact.summary || JSON.stringify(content).slice(0, 420);
  }
  return `
    <article class="artifact-card">
      <div>
        <strong>${escapeHtml(artifact.title)}</strong>
        <span>${escapeHtml(artifact.artifact_type)} · ${escapeHtml(artifact.content_type)}</span>
      </div>
      <pre>${escapeHtml(preview)}</pre>
    </article>
  `;
}

async function generateDraft() {
  const prompt = $("#prompt-input").value.trim();
  if (!prompt) {
    showToast("Enter a report prompt first.");
    return;
  }

  setAgentState("Drafting", "warn");
  $("#generate-button").disabled = true;
  addChatMessage("user", prompt);

  try {
    const report = await api("/api/agent/draft", {
      method: "POST",
      body: JSON.stringify({ prompt, data_source_id: state.selectedDataSourceId }),
    });
    state.report = report;
    state.previews = {};
    state.activeBlockId = report.blocks[0]?.id || null;
    addChatMessage(
      "agent",
      `Created ${report.blocks.length} SQL-backed report blocks using ${report.template}.`
    );
    renderBuilderState();
    await previewAllBlocks();
    setAgentState("Ready");
  } catch (error) {
    setAgentState("Error", "warn");
    showToast(error.message);
  } finally {
    $("#generate-button").disabled = false;
  }
}

function renderBuilderState() {
  if (!state.report) return;
  $("#workspace-title").textContent = state.report.title;
  $("#preview-state").textContent = state.report.status;
  $("#preview-state").className = "pill";
  $("#block-count").textContent = String(state.report.blocks.length);
  renderParameterControls();
  renderBlockEditors();
  renderReport($("#report-preview"), state.report, state.previews, { editable: true });
}

function renderParameterControls() {
  const container = $("#parameter-controls");
  if (!container || !state.report) return;
  container.innerHTML = `
    <div class="parameter-grid">
      ${state.report.parameters
        .map((param) => {
          if (param.type === "select") {
            return `
              <div class="field">
                <label for="param-${escapeHtml(param.name)}">${escapeHtml(param.label)}</label>
                <select id="param-${escapeHtml(param.name)}" data-param="${escapeHtml(param.name)}">
                  ${(param.options || [])
                    .map(
                      (option) =>
                        `<option value="${escapeHtml(option)}" ${
                          option === (param.value ?? param.default) ? "selected" : ""
                        }>${escapeHtml(option)}</option>`
                    )
                    .join("")}
                </select>
              </div>
            `;
          }
          return `
            <div class="field">
              <label for="param-${escapeHtml(param.name)}">${escapeHtml(param.label)}</label>
              <input id="param-${escapeHtml(param.name)}" type="${escapeHtml(param.type)}" value="${escapeHtml(
                param.value ?? param.default
              )}" data-param="${escapeHtml(param.name)}">
            </div>
          `;
        })
        .join("")}
    </div>
    <button id="refresh-preview-button" class="button secondary" type="button">Refresh Preview</button>
  `;

  container.querySelectorAll("[data-param]").forEach((control) => {
    control.addEventListener("change", () => {
      const param = state.report.parameters.find((item) => item.name === control.dataset.param);
      if (param) param.value = control.value;
      renderReport($("#report-preview"), state.report, state.previews, { editable: true });
    });
  });
  $("#refresh-preview-button").addEventListener("click", previewAllBlocks);
}

function renderBlockEditors() {
  const container = $("#block-editor-list");
  if (!container || !state.report) return;

  container.innerHTML = state.report.blocks
    .map((block) => {
      const preview = state.previews[block.id];
      const meta = preview?.ok
        ? `${preview.row_count} rows · ${preview.elapsed_ms} ms`
        : preview?.error
          ? "Preview failed"
          : "Not previewed";
      return `
        <article class="block-editor" data-editor="${escapeHtml(block.id)}">
          <div class="block-editor-header">
            <strong title="${escapeHtml(block.title)}">${escapeHtml(block.title)}</strong>
            <span class="pill muted">${escapeHtml(block.visual_type)}</span>
          </div>
          <div class="block-editor-body">
            <textarea class="sql-textarea" data-sql-block="${escapeHtml(block.id)}">${escapeHtml(
              block.sql_template
            )}</textarea>
            <div class="block-actions">
              <span class="preview-meta">${escapeHtml(meta)}</span>
              <button class="button secondary" type="button" data-preview-block="${escapeHtml(
                block.id
              )}">Preview</button>
            </div>
            ${preview?.error ? `<div class="error-box">${escapeHtml(preview.error)}</div>` : ""}
          </div>
        </article>
      `;
    })
    .join("");

  container.querySelectorAll("[data-sql-block]").forEach((textarea) => {
    textarea.addEventListener("input", () => {
      const block = state.report.blocks.find((item) => item.id === textarea.dataset.sqlBlock);
      if (block) {
        block.sql_template = textarea.value;
        delete state.previews[block.id];
        renderReport($("#report-preview"), state.report, state.previews, { editable: true });
      }
    });
  });

  container.querySelectorAll("[data-preview-block]").forEach((button) => {
    button.addEventListener("click", () => previewBlock(button.dataset.previewBlock));
  });
}

async function previewBlock(blockId, options = {}) {
  const block = state.report.blocks.find((item) => item.id === blockId);
  if (!block) return;

  try {
    const preview = await api("/api/query/preview", {
      method: "POST",
      body: JSON.stringify({
        sql_template: block.sql_template,
        parameters: currentParameters(),
        limit: options.limit || 100,
        data_source_id: block.data_source_id || state.report.data_source_id || state.selectedDataSourceId,
      }),
    });
    state.previews[block.id] = preview;
  } catch (error) {
    state.previews[block.id] = { ok: false, error: error.message, rows: [], columns: [] };
  }

  renderBuilderState();
}

async function previewAllBlocks() {
  if (!state.report) return;
  $("#preview-state").textContent = "Refreshing";
  $("#preview-state").className = "pill warn";
  for (const block of state.report.blocks) {
    await previewBlock(block.id, { limit: 100 });
  }
  $("#preview-state").textContent = "Previewed";
  $("#preview-state").className = "pill";
}

async function publishReport() {
  if (!state.report) {
    showToast("Generate a draft before publishing.");
    return;
  }

  $("#publish-button").disabled = true;
  try {
    const published = await api("/api/reports/publish", {
      method: "POST",
      body: JSON.stringify({ report: state.report }),
    });
    state.report = published;
    renderBuilderState();
    const link = $("#published-link");
    link.href = published.published_path;
    link.classList.remove("hidden");
    showToast("Report published.");
  } catch (error) {
    showToast(error.message);
  } finally {
    $("#publish-button").disabled = false;
  }
}

async function uploadCsv() {
  const input = $("#csv-file");
  const file = input.files?.[0];
  if (!file) {
    showToast("Choose a CSV file first.");
    return;
  }

  try {
    const csvText = await file.text();
    const result = await api("/api/csv/upload", {
      method: "POST",
      body: JSON.stringify({ name: file.name.replace(/\.csv$/i, ""), csv_text: csvText }),
    });
    state.schema = result.schema;
    state.selectedDataSourceId = result.schema.active_data_source_id || state.selectedDataSourceId;
    renderSchema();
    const cloud = result.s3?.uploaded ? ` and ${result.s3.uri}` : "";
    showToast(`Uploaded ${result.table_name} with ${result.row_count} rows${cloud}.`);
  } catch (error) {
    showToast(error.message);
  }
}

function postgresPayload() {
  return {
    name: $("#pg-name").value.trim(),
    host: $("#pg-host").value.trim(),
    port: Number($("#pg-port").value || 5432),
    database: $("#pg-database").value.trim(),
    user: $("#pg-user").value.trim(),
    password: $("#pg-password").value,
    sslmode: $("#pg-sslmode").value,
  };
}

async function testPostgresConnection() {
  const status = $("#postgres-status");
  status.textContent = "Testing";
  try {
    const result = await api("/api/data-sources/postgres/test", {
      method: "POST",
      body: JSON.stringify(postgresPayload()),
    });
    status.textContent = `Connected · ${result.table_count} tables`;
  } catch (error) {
    status.textContent = error.message;
  }
}

async function savePostgresConnection() {
  const status = $("#postgres-status");
  status.textContent = "Saving";
  try {
    const result = await api("/api/data-sources/postgres/save", {
      method: "POST",
      body: JSON.stringify(postgresPayload()),
    });
    state.schema = result.schema;
    state.selectedDataSourceId = result.source.id;
    renderSchema();
    status.textContent = `Saved for this session · ${result.schema.tables.length} tables`;
    showToast("Postgres source saved for this server session.");
  } catch (error) {
    status.textContent = error.message;
  }
}

function renderReport(container, report, previews, options = {}) {
  if (!container || !report) return;
  container.classList.remove("empty-state");
  container.innerHTML = "";

  const doc = document.createElement("div");
  doc.className = "report-document";
  const params = currentParameters(report);
  const generatedAt = report.published_at || report.updated_at || report.created_at;

  doc.innerHTML = `
    <section class="report-hero">
      <div>
        <p class="eyebrow">${escapeHtml(report.template)}</p>
        <h2>${escapeHtml(report.title)}</h2>
      </div>
      <p>${escapeHtml(report.prompt || "Generated report")}</p>
      <div class="report-meta-row">
        <span class="meta-chip">${escapeHtml(report.status)}</span>
        <span class="meta-chip">${escapeHtml(params.start_date)} to ${escapeHtml(params.end_date)}</span>
        <span class="meta-chip">${escapeHtml(params.region || "All regions")}</span>
        <span class="meta-chip">Updated ${escapeHtml(new Date(generatedAt).toLocaleString())}</span>
      </div>
    </section>
  `;

  const grid = document.createElement("section");
  grid.className = "report-section-grid";
  const chartTasks = [];

  for (const block of report.blocks) {
    const preview = previews[block.id];
    const section = document.createElement("article");
    section.className = `report-section ${
      block.visual_type === "kpi" || block.visual_type === "table" ? "full-span" : ""
    }`.trim();
    section.innerHTML = `
      <div>
        <h3>${escapeHtml(block.title)}</h3>
        <p>${escapeHtml(block.narrative || "")}</p>
      </div>
    `;

    if (!preview) {
      const placeholder = document.createElement("div");
      placeholder.className = "empty-state";
      placeholder.innerHTML = "<p>Waiting for preview data.</p>";
      section.appendChild(placeholder);
    } else if (preview.error) {
      const error = document.createElement("div");
      error.className = "error-box";
      error.textContent = preview.error;
      section.appendChild(error);
    } else if (block.visual_type === "kpi") {
      section.appendChild(renderKpis(preview));
    } else if (block.visual_type === "table") {
      section.appendChild(renderDataTable(preview, 10));
    } else {
      const frame = document.createElement("div");
      frame.className = "chart-frame";
      const canvas = document.createElement("canvas");
      frame.appendChild(canvas);
      section.appendChild(frame);
      chartTasks.push({ canvas, block, preview });
    }

    grid.appendChild(section);
  }

  doc.appendChild(grid);
  container.appendChild(doc);
  window.requestAnimationFrame(() => {
    for (const task of chartTasks) drawChart(task.canvas, task.block, task.preview);
  });
}

function renderKpis(preview) {
  const row = preview.rows[0] || {};
  const grid = document.createElement("div");
  grid.className = "kpi-grid";
  for (const key of Object.keys(row)) {
    const tile = document.createElement("div");
    tile.className = "kpi-tile";
    tile.innerHTML = `
      <div class="kpi-label">${escapeHtml(humanize(key))}</div>
      <div class="kpi-value">${escapeHtml(formatValue(key, row[key]))}</div>
    `;
    grid.appendChild(tile);
  }
  return grid;
}

function renderDataTable(preview, maxRows = 8) {
  const wrap = document.createElement("div");
  wrap.className = "data-table-wrap";
  const columns = preview.columns || [];
  const rows = (preview.rows || []).slice(0, maxRows);
  wrap.innerHTML = `
    <table class="data-table">
      <thead>
        <tr>${columns.map((column) => `<th>${escapeHtml(humanize(column))}</th>`).join("")}</tr>
      </thead>
      <tbody>
        ${rows
          .map(
            (row) => `
              <tr>
                ${columns
                  .map((column) => `<td>${escapeHtml(formatValue(column, row[column]))}</td>`)
                  .join("")}
              </tr>
            `
          )
          .join("")}
      </tbody>
    </table>
  `;
  return wrap;
}

function setupCanvas(canvas) {
  const rect = canvas.getBoundingClientRect();
  const dpr = window.devicePixelRatio || 1;
  const width = Math.max(320, Math.floor(rect.width || 640));
  const height = Math.max(220, Math.floor(rect.height || 240));
  canvas.width = width * dpr;
  canvas.height = height * dpr;
  const ctx = canvas.getContext("2d");
  ctx.scale(dpr, dpr);
  ctx.clearRect(0, 0, width, height);
  return { ctx, width, height };
}

function drawChart(canvas, block, preview) {
  const rows = preview.rows || [];
  if (!rows.length) return;
  if (block.visual_type === "line") drawLineChart(canvas, rows, block.x, block.y);
  if (block.visual_type === "bar") drawBarChart(canvas, rows, block.x, block.y);
}

function drawAxes(ctx, width, height, margin) {
  ctx.strokeStyle = "#d8e0e7";
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.moveTo(margin.left, margin.top);
  ctx.lineTo(margin.left, height - margin.bottom);
  ctx.lineTo(width - margin.right, height - margin.bottom);
  ctx.stroke();

  ctx.strokeStyle = "#eef3f6";
  for (let i = 1; i <= 4; i += 1) {
    const y = margin.top + ((height - margin.top - margin.bottom) * i) / 5;
    ctx.beginPath();
    ctx.moveTo(margin.left, y);
    ctx.lineTo(width - margin.right, y);
    ctx.stroke();
  }
}

function drawBarChart(canvas, rows, xKey, yKey) {
  const { ctx, width, height } = setupCanvas(canvas);
  const margin = { top: 22, right: 18, bottom: 54, left: 54 };
  drawAxes(ctx, width, height, margin);

  const values = rows.map((row) => Number(row[yKey]) || 0);
  const max = Math.max(...values, 1);
  const plotW = width - margin.left - margin.right;
  const plotH = height - margin.top - margin.bottom;
  const barGap = 10;
  const barW = Math.max(14, (plotW - barGap * (rows.length - 1)) / rows.length);

  rows.forEach((row, index) => {
    const value = Number(row[yKey]) || 0;
    const x = margin.left + index * (barW + barGap);
    const barH = (value / max) * plotH;
    const y = height - margin.bottom - barH;
    ctx.fillStyle = index % 3 === 0 ? "#0f766e" : index % 3 === 1 ? "#2563eb" : "#b45309";
    ctx.fillRect(x, y, barW, barH);

    ctx.fillStyle = "#637181";
    ctx.font = "11px system-ui, sans-serif";
    ctx.textAlign = "center";
    const label = String(row[xKey] ?? "").slice(0, 12);
    ctx.fillText(label, x + barW / 2, height - margin.bottom + 18);
  });

  ctx.fillStyle = "#263442";
  ctx.font = "12px system-ui, sans-serif";
  ctx.textAlign = "left";
  ctx.fillText(formatValue(yKey, max), 12, margin.top + 4);
}

function drawLineChart(canvas, rows, xKey, yKey) {
  const { ctx, width, height } = setupCanvas(canvas);
  const margin = { top: 22, right: 22, bottom: 48, left: 58 };
  drawAxes(ctx, width, height, margin);

  const values = rows.map((row) => Number(row[yKey]) || 0);
  const max = Math.max(...values, 1);
  const min = Math.min(...values, 0);
  const range = Math.max(max - min, 1);
  const plotW = width - margin.left - margin.right;
  const plotH = height - margin.top - margin.bottom;

  const points = rows.map((row, index) => {
    const x = margin.left + (rows.length === 1 ? plotW / 2 : (plotW * index) / (rows.length - 1));
    const y = height - margin.bottom - (((Number(row[yKey]) || 0) - min) / range) * plotH;
    return { x, y, label: String(row[xKey] ?? "") };
  });

  ctx.strokeStyle = "#0f766e";
  ctx.lineWidth = 3;
  ctx.beginPath();
  points.forEach((point, index) => {
    if (index === 0) ctx.moveTo(point.x, point.y);
    else ctx.lineTo(point.x, point.y);
  });
  ctx.stroke();

  ctx.fillStyle = "#ffffff";
  ctx.strokeStyle = "#0f766e";
  ctx.lineWidth = 2;
  points.forEach((point) => {
    ctx.beginPath();
    ctx.arc(point.x, point.y, 4, 0, Math.PI * 2);
    ctx.fill();
    ctx.stroke();
  });

  ctx.fillStyle = "#637181";
  ctx.font = "11px system-ui, sans-serif";
  ctx.textAlign = "center";
  points.forEach((point, index) => {
    if (index % Math.ceil(points.length / 6) === 0 || index === points.length - 1) {
      ctx.fillText(point.label, point.x, height - margin.bottom + 18);
    }
  });

  ctx.fillStyle = "#263442";
  ctx.font = "12px system-ui, sans-serif";
  ctx.textAlign = "left";
  ctx.fillText(formatValue(yKey, max), 12, margin.top + 4);
}

async function loadPublishedReport() {
  const reportId = window.location.pathname.split("/").filter(Boolean).pop();
  const status = $("#published-status");

  try {
    const report = await api(`/api/reports/${reportId}`);
    state.report = report;
    $("#published-title").textContent = report.title;
    status.textContent = `Published ${new Date(report.published_at).toLocaleString()} · refreshing live preview data`;

    for (const block of report.blocks) {
      await previewPublishedBlock(block);
    }

    status.textContent = `Published ${new Date(report.published_at).toLocaleString()} · live query preview`;
    renderReport($("#published-report"), report, state.previews);
  } catch (error) {
    status.textContent = error.message;
    status.classList.add("error-box");
  }
}

async function previewPublishedBlock(block) {
  try {
    const preview = await api("/api/query/preview", {
      method: "POST",
      body: JSON.stringify({
        sql_template: block.sql_template,
        parameters: currentParameters(),
        limit: 250,
        data_source_id: block.data_source_id || state.report.data_source_id || "demo_warehouse",
      }),
    });
    state.previews[block.id] = preview;
  } catch (error) {
    state.previews[block.id] = { ok: false, error: error.message, rows: [], columns: [] };
  }
}

async function initBuilder() {
  addChatMessage("agent", "Connected to the demo warehouse. Ready to draft a report.");
  await Promise.all([loadServiceStatus(), loadSchema()]);
  $("#generate-button").addEventListener("click", generateDraft);
  $("#publish-button").addEventListener("click", publishReport);
  $("#upload-csv-button").addEventListener("click", uploadCsv);
  $("#light-analysis-button").addEventListener("click", runLightAnalysis);
  $("#deep-analysis-button").addEventListener("click", requestDeepAnalysis);
  $("#reload-schema-button").addEventListener("click", () => loadSchema(state.selectedDataSourceId));
  $("#data-source-select").addEventListener("change", (event) => loadSchema(event.target.value));
  $("#test-postgres-button").addEventListener("click", testPostgresConnection);
  $("#save-postgres-button").addEventListener("click", savePostgresConnection);
  $("#csv-file").addEventListener("change", (event) => {
    const file = event.target.files?.[0];
    $("#csv-file-label").textContent = file ? file.name : "Choose CSV";
  });
}

if (view === "published") {
  loadPublishedReport();
} else {
  initBuilder().catch((error) => showToast(error.message));
}
