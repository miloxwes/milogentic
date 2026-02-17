const form = document.getElementById("run-form");
const submitBtn = document.getElementById("submit-btn");
const statusNode = document.getElementById("status");
const resultNode = document.getElementById("result");
const finalTextNode = document.getElementById("final-text");
const stepsNode = document.getElementById("steps");
const llmTraceNode = document.getElementById("llm-trace");
const workflowNode = document.getElementById("workflow-diagram");
const toolCatalogNode = document.getElementById("tool-catalog");

const isObjectLike = (value) => typeof value === "object" && value !== null;

const renderPrimitive = (value) => {
  const node = document.createElement("span");
  if (typeof value === "string") {
    node.className = "json-value json-string";
    node.textContent = `"${value}"`;
    return node;
  }
  if (typeof value === "number") {
    node.className = "json-value json-number";
    node.textContent = String(value);
    return node;
  }
  if (typeof value === "boolean") {
    node.className = "json-value json-boolean";
    node.textContent = String(value);
    return node;
  }
  node.className = "json-value json-null";
  node.textContent = "null";
  return node;
};

const renderJsonTree = (value, key = null, depth = 0) => {
  if (!isObjectLike(value)) {
    const line = document.createElement("div");
    line.className = "json-line";
    if (key !== null) {
      const keyNode = document.createElement("span");
      keyNode.className = "json-key";
      keyNode.textContent = `${key}: `;
      line.appendChild(keyNode);
    }
    line.appendChild(renderPrimitive(value));
    return line;
  }

  const entries = Array.isArray(value) ? value.map((v, i) => [String(i), v]) : Object.entries(value);
  const details = document.createElement("details");
  details.className = "json-node";
  details.open = depth <= 1;

  const summary = document.createElement("summary");
  summary.className = "json-summary";
  const type = Array.isArray(value) ? "array" : "object";
  const size = entries.length;
  summary.textContent = key === null ? `${type} (${size})` : `${key}: ${type} (${size})`;
  details.appendChild(summary);

  const children = document.createElement("div");
  children.className = "json-children";

  if (!entries.length) {
    const empty = document.createElement("div");
    empty.className = "json-line";
    empty.textContent = Array.isArray(value) ? "[]" : "{}";
    children.appendChild(empty);
  } else {
    entries.forEach(([childKey, childValue]) => {
      children.appendChild(renderJsonTree(childValue, childKey, depth + 1));
    });
  }

  details.appendChild(children);
  return details;
};

const markWorkflowState = (stages) => {
  workflowNode.querySelectorAll(".wf-node").forEach((node) => {
    const stage = node.dataset.stage;
    node.classList.remove("done", "active");
    if (stages.done.has(stage)) {
      node.classList.add("done");
    }
    if (stages.active === stage) {
      node.classList.add("active");
    }
  });
};

const renderToolCatalog = (tools) => {
  toolCatalogNode.innerHTML = "";
  if (!tools.length) {
    const empty = document.createElement("p");
    empty.className = "tool-meta";
    empty.textContent = "No tool descriptions available in this run.";
    toolCatalogNode.appendChild(empty);
    return;
  }

  tools.forEach((tool) => {
    const item = document.createElement("article");
    item.className = "tool-item";

    const name = document.createElement("h4");
    name.className = "tool-head";
    name.textContent = tool.name || "unknown_tool";

    const desc = document.createElement("p");
    desc.className = "tool-desc";
    desc.textContent = tool.description || "No description provided.";

    const required = tool.parameters?.required || [];
    const meta = document.createElement("p");
    meta.className = "tool-meta";
    meta.textContent =
      required.length > 0 ? `Required params: ${required.join(", ")}` : "Required params: none";

    item.appendChild(name);
    item.appendChild(desc);
    item.appendChild(meta);
    toolCatalogNode.appendChild(item);
  });
};

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  statusNode.classList.remove("error");
  statusNode.textContent = "Running agent...";
  resultNode.classList.remove("visible");
  llmTraceNode.innerHTML = "";
  toolCatalogNode.innerHTML = "";
  markWorkflowState({ done: new Set(["submitted"]), active: "agent_pickup" });
  submitBtn.disabled = true;

  const payload = {
    session_id: document.getElementById("session_id").value.trim(),
    goal: document.getElementById("goal").value.trim(),
  };

  if (!payload.session_id || !payload.goal) {
    statusNode.textContent = "Session ID and request are required.";
    statusNode.classList.add("error");
    submitBtn.disabled = false;
    return;
  }

  try {
    const response = await fetch("/agent/run", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });

    if (!response.ok) {
      throw new Error("Request failed with status " + response.status);
    }

    const data = await response.json();
    finalTextNode.textContent = data.final_text || "";
    const steps = data.steps || [];

    const hasPrompt = steps.some((step) => step.type === "llm_prompt");
    const hasResult = steps.some((step) => step.type === "llm_result");
    const hasToolActivity = steps.some((step) =>
      ["tool_result", "tool_error", "rate_limited", "blocked"].includes(step.type)
    );

    const firstPrompt = steps.find((step) => step.type === "llm_prompt");
    renderToolCatalog(firstPrompt?.prompt?.tools || []);

    const doneStages = new Set(["submitted", "agent_pickup"]);
    if (hasPrompt) {
      doneStages.add("context_ready");
      doneStages.add("llm_call");
    }
    if (hasResult) {
      doneStages.add("llm_result");
    }
    if (hasToolActivity) {
      doneStages.add("tool_exec");
    }
    if (data.final_text) {
      doneStages.add("final");
    }
    const activeStage = data.final_text
      ? "final"
      : hasResult
      ? "tool_exec"
      : hasPrompt
      ? "llm_result"
      : "agent_pickup";
    markWorkflowState({ done: doneStages, active: activeStage });

    const tracesByIteration = new Map();
    steps.forEach((step) => {
      if (step.type !== "llm_prompt" && step.type !== "llm_result") {
        return;
      }
      const iter = step.iteration || 0;
      if (!tracesByIteration.has(iter)) {
        tracesByIteration.set(iter, { prompt: null, result: null });
      }
      const current = tracesByIteration.get(iter);
      if (step.type === "llm_prompt") {
        current.prompt = step.prompt;
      } else {
        current.result = step.result;
      }
    });

    llmTraceNode.innerHTML = "";
    [...tracesByIteration.entries()]
      .sort((a, b) => a[0] - b[0])
      .forEach(([iteration, trace]) => {
        const item = document.createElement("article");
        item.className = "trace-item";
        const title = document.createElement("h4");
        title.textContent = `Iteration ${iteration}`;

        const grid = document.createElement("div");
        grid.className = "trace-grid";

        const promptBlock = document.createElement("div");
        promptBlock.className = "trace-block";
        const promptLabel = document.createElement("strong");
        promptLabel.textContent = "PROMPT";
        promptBlock.appendChild(promptLabel);
        promptBlock.appendChild(renderJsonTree(trace.prompt));

        const resultBlock = document.createElement("div");
        resultBlock.className = "trace-block";
        const resultLabel = document.createElement("strong");
        resultLabel.textContent = "RESULT";
        resultBlock.appendChild(resultLabel);
        resultBlock.appendChild(renderJsonTree(trace.result));

        grid.appendChild(promptBlock);
        grid.appendChild(resultBlock);
        item.appendChild(title);
        item.appendChild(grid);
        llmTraceNode.appendChild(item);
      });

    stepsNode.innerHTML = "";
    steps.forEach((step, index) => {
      const item = document.createElement("li");
      const label = document.createElement("code");
      label.textContent = `Step ${index + 1}`;
      item.appendChild(label);
      item.appendChild(renderJsonTree(step));
      stepsNode.appendChild(item);
    });

    resultNode.classList.add("visible");
    statusNode.textContent = "Done. Session: " + data.session_id;
  } catch (error) {
    markWorkflowState({ done: new Set(["submitted"]), active: "agent_pickup" });
    statusNode.textContent = "Error: " + error.message;
    statusNode.classList.add("error");
  } finally {
    submitBtn.disabled = false;
  }
});
