const STORAGE_KEY = 'global-knowledge-journal-entries';

const entryForm = document.getElementById('entry-form');
const entriesContainer = document.getElementById('entries');
const clearButton = document.getElementById('clear-button');

function loadEntries() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw ? JSON.parse(raw) : [];
  } catch {
    return [];
  }
}const latestEl = document.getElementById("latest-report");
const reportListEl = document.getElementById("report-list");
const reportCountEl = document.getElementById("report-count");
const latestDateEl = document.getElementById("latest-date");
const siteStatusEl = document.getElementById("site-status");

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function normalizeAssetPath(value) {
  if (!value || value === "...") {
    return "";
  }

  const text = String(value).replaceAll("\\", "/");

  if (text.includes("outputs/")) {
    return `outputs/${text.split("outputs/")[1]}`;
  }

  return text;
}

function getHtmlUrl(report) {
  return normalizeAssetPath(report.html_url || report.html_path || "");
}

function getPdfUrl(report) {
  return normalizeAssetPath(report.pdf_url || report.pdf_path || "");
}

function getCategory(report) {
  const main = report.main_category || report.category || "";
  const middle = report.mid_category || "";
  const sub = report.sub_category || "";

  return [main, middle, sub].filter(Boolean).join(" / ");
}

function renderActions(report) {
  const htmlUrl = getHtmlUrl(report);
  const pdfUrl = getPdfUrl(report);

  const htmlButton = htmlUrl
    ? `<a class="button secondary" href="${escapeHtml(htmlUrl)}" target="_blank" rel="noopener">HTML 보기</a>`
    : "";

  const pdfButton = pdfUrl
    ? `<a class="button" href="${escapeHtml(pdfUrl)}" target="_blank" rel="noopener">PDF 보기</a>`
    : "";

  return `
    <div class="report-actions">
      ${pdfButton}
      ${htmlButton}
    </div>
  `;
}

function renderReportCard(report, isLatest = false) {
  const category = getCategory(report);

  return `
    <article class="${isLatest ? "latest-card" : "report-card"}">
      <div class="report-meta">
        <span class="badge">${escapeHtml(report.date || "-")}</span>
        ${category ? `<span class="badge">${escapeHtml(category)}</span>` : ""}
        ${report.status ? `<span class="badge">${escapeHtml(report.status)}</span>` : ""}
      </div>

      <h3 class="report-title">${escapeHtml(report.title || "Untitled Report")}</h3>

      ${
        report.subtitle
          ? `<p class="report-subtitle">${escapeHtml(report.subtitle)}</p>`
          : ""
      }

      ${renderActions(report)}
    </article>
  `;
}

async function loadJson(path) {
  const response = await fetch(path, { cache: "no-store" });

  if (!response.ok) {
    throw new Error(`${path} 파일을 불러오지 못했습니다.`);
  }

  return response.json();
}

async function init() {
  try {
    const reports = await loadJson("public/reports.json");

    const normalizedReports = Array.isArray(reports)
      ? reports
          .filter((report) => report && typeof report === "object")
          .sort((a, b) => String(b.date || "").localeCompare(String(a.date || "")))
      : [];

    if (normalizedReports.length === 0) {
      siteStatusEl.textContent = "No reports";
      reportCountEl.textContent = "0";
      latestDateEl.textContent = "-";
      latestEl.innerHTML = `<div class="empty">아직 공개된 리포트가 없습니다.</div>`;
      reportListEl.innerHTML = `<div class="empty">리포트 목록이 비어 있습니다.</div>`;
      return;
    }

    const latest = normalizedReports[0];

    siteStatusEl.textContent = "Active";
    reportCountEl.textContent = String(normalizedReports.length);
    latestDateEl.textContent = latest.date || "-";

    latestEl.outerHTML = renderReportCard(latest, true);

    reportListEl.classList.remove("loading-card");
    reportListEl.innerHTML = normalizedReports
      .map((report) => renderReportCard(report, false))
      .join("");
  } catch (error) {
    console.error(error);

    siteStatusEl.textContent = "Error";
    latestEl.innerHTML = `
      <div class="empty">
        리포트 데이터를 불러오지 못했습니다. public/reports.json 파일을 확인하세요.
      </div>
    `;
    reportListEl.innerHTML = `
      <div class="empty">
        ${escapeHtml(error.message)}
      </div>
    `;
  }
}

init();

function saveEntries(entries) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(entries));
}

function renderEntries() {
  const entries = loadEntries();

  if (entries.length === 0) {
    entriesContainer.innerHTML = '<div class="empty">No entries yet. Add your first insight above.</div>';
    return;
  }

  entriesContainer.innerHTML = entries
    .map(
      (entry) => `
        <article class="entry-card">
          <h3>${entry.title}</h3>
          <p>${entry.content}</p>
          <div class="meta">
            ${entry.tags
              .map((tag) => `<span class="tag">${tag}</span>`)
              .join('')}
          </div>
        </article>
      `
    )
    .join('');
}

entryForm.addEventListener('submit', (event) => {
  event.preventDefault();

  const title = document.getElementById('title').value.trim();
  const content = document.getElementById('content').value.trim();
  const tags = document.getElementById('tags').value
    .split(',')
    .map((tag) => tag.trim())
    .filter(Boolean);

  if (!title || !content) {
    return;
  }

  const entries = loadEntries();
  entries.unshift({ title, content, tags });
  saveEntries(entries);
  entryForm.reset();
  renderEntries();
});

clearButton.addEventListener('click', () => {
  localStorage.removeItem(STORAGE_KEY);
  renderEntries();
});

renderEntries();
