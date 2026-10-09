const $ = (selector) => document.querySelector(selector);

const state = {
  inspectionToken: null,
  document: null,
  jobId: null,
  pollTimer: null,
};

const inspectForm = $("#inspect-form");
const jobForm = $("#job-form");
const alertBox = $("#alert");
const documentCard = $("#document-card");
const progressSection = $("#progress-section");

function showAlert(message) {
  alertBox.textContent = message;
  alertBox.hidden = false;
}

function clearAlert() {
  alertBox.hidden = true;
  alertBox.textContent = "";
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
  });
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || "Ocorreu um erro inesperado.");
  return data;
}

inspectForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  clearAlert();
  const button = $("#inspect-button");
  button.disabled = true;
  button.querySelector("span").textContent = "A analisar…";
  jobForm.hidden = true;
  documentCard.hidden = true;
  progressSection.hidden = true;
  try {
    const data = await api("/api/inspect", {
      method: "POST",
      body: JSON.stringify({ url: $("#source-url").value }),
    });
    state.inspectionToken = data.inspection_token;
    state.document = data;
    $("#provider-tag").textContent = data.provider_label;
    $("#date-tag").textContent = data.date_label || "";
    $("#date-tag").hidden = !data.date_label;
    $("#document-title").textContent = data.title;
    $("#document-reference").textContent = data.reference;
    $("#document-repository").textContent = data.repository;
    $("#page-count").textContent = new Intl.NumberFormat("pt-PT").format(data.page_count);
    $("#output-name").value = `${data.reference} - ${data.title}`;
    documentCard.hidden = false;
    jobForm.hidden = false;
    updateSelectionSummary();
  } catch (error) {
    showAlert(error.message);
  } finally {
    button.disabled = false;
    button.querySelector("span").textContent = "Analisar";
  }
});

document.querySelectorAll('input[name="quality"]').forEach((input) => {
  input.addEventListener("change", () => {
    document.querySelectorAll(".choice").forEach((choice) => choice.classList.remove("selected"));
    input.closest(".choice").classList.add("selected");
  });
});

function estimateSelection(value, total) {
  if (!value.trim()) return total;
  const numbers = new Set();
  for (const raw of value.split(",")) {
    const token = raw.trim();
    if (/^\d+$/.test(token)) numbers.add(Number(token));
    const match = token.match(/^(\d+)\s*-\s*(\d+)$/);
    if (match) {
      const start = Number(match[1]);
      const end = Number(match[2]);
      if (end - start <= 10000) for (let page = start; page <= end; page += 1) numbers.add(page);
    }
  }
  return numbers.size || total;
}

function updateSelectionSummary() {
  if (!state.document) return;
  const value = $("#pages").value;
  const count = estimateSelection(value, state.document.page_count);
  $("#selection-summary").textContent = value.trim()
    ? `${count} ${count === 1 ? "página selecionada" : "páginas selecionadas"}`
    : `Todas as ${state.document.page_count} páginas`;
}

$("#pages").addEventListener("input", updateSelectionSummary);

jobForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  clearAlert();
  const button = $("#create-button");
  button.disabled = true;
  try {
    const data = await api("/api/jobs", {
      method: "POST",
      body: JSON.stringify({
        inspection_token: state.inspectionToken,
        pages: $("#pages").value,
        quality: $('input[name="quality"]:checked').value,
        jpeg_quality: 86,
        output_name: $("#output-name").value,
      }),
    });
    state.jobId = data.id;
    progressSection.hidden = false;
    $("#download-button").hidden = true;
    $("#resume-button").hidden = true;
    $("#cancel-button").hidden = false;
    progressSection.scrollIntoView({ behavior: "smooth", block: "center" });
    renderJob(data);
    schedulePoll();
  } catch (error) {
    showAlert(error.message);
  } finally {
    button.disabled = false;
  }
});

function renderJob(job) {
  const percent = job.status === "complete" ? 100 : job.percent;
  $("#progress-percent").textContent = `${Math.round(percent)}%`;
  $("#progress-bar").style.width = `${percent}%`;
  $("#progress-message").textContent = job.error || job.message;
  $("#progress-title").textContent = {
    queued: "Na fila…",
    downloading: "A recolher as páginas…",
    creating_pdf: "A compor o PDF…",
    complete: "O seu PDF está pronto.",
    failed: "A criação foi interrompida.",
    cancelled: "Transferência interrompida.",
  }[job.status] || "A preparar…";

  const terminal = ["complete", "failed", "cancelled"].includes(job.status);
  $("#cancel-button").hidden = terminal;
  $("#resume-button").hidden = !job.can_resume;
  if (job.download_url) {
    const download = $("#download-button");
    download.href = job.download_url;
    download.hidden = false;
  }
  return terminal;
}

function schedulePoll() {
  clearTimeout(state.pollTimer);
  state.pollTimer = setTimeout(pollJob, 700);
}

async function pollJob() {
  if (!state.jobId) return;
  try {
    const job = await api(`/api/jobs/${state.jobId}`);
    if (!renderJob(job)) schedulePoll();
  } catch (error) {
    $("#progress-message").textContent = error.message;
    schedulePoll();
  }
}

$("#cancel-button").addEventListener("click", async () => {
  if (!state.jobId) return;
  try {
    const job = await api(`/api/jobs/${state.jobId}/cancel`, { method: "POST", body: "{}" });
    renderJob(job);
    schedulePoll();
  } catch (error) {
    showAlert(error.message);
  }
});

$("#resume-button").addEventListener("click", async () => {
  if (!state.jobId) return;
  try {
    const job = await api(`/api/jobs/${state.jobId}/resume`, { method: "POST", body: "{}" });
    $("#resume-button").hidden = true;
    renderJob(job);
    schedulePoll();
  } catch (error) {
    showAlert(error.message);
  }
});
