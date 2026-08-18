const latestEl = document.getElementById("latest-report");
const reportListEl = document.getElementById("report-list");
const reportCountEl = document.getElementById("report-count");
const latestDateEl = document.getElementById("latest-date");
const siteStatusEl = document.getElementById("site-status");
const archiveDateEl = document.getElementById("archive-date");
const archiveResultCountEl = document.getElementById("archive-result-count");

let publishedReports = [];

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
        <span class="badge published-badge">정식 발행</span>
      </div>

      <h3 class="report-title">${escapeHtml(report.title || "제목 없는 리포트")}</h3>

      ${
        report.subtitle
          ? `<p class="report-subtitle">${escapeHtml(report.subtitle)}</p>`
          : ""
      }

      ${renderActions(report)}
    </article>
  `;
}

function renderArchive(selectedDate = "") {
  const filteredReports = selectedDate
    ? publishedReports.filter((report) => report.date === selectedDate)
    : publishedReports;

  reportListEl.classList.remove("loading-card");
  archiveResultCountEl.textContent = selectedDate
    ? `${selectedDate} 리포트 ${filteredReports.length}건`
    : `전체 공개 리포트 ${filteredReports.length}건`;

  if (filteredReports.length === 0) {
    reportListEl.innerHTML = `<div class="empty">선택한 날짜에 공개된 리포트가 없습니다.</div>`;
    return;
  }

  reportListEl.innerHTML = filteredReports
    .map((report) => renderReportCard(report))
    .join("");
}

function configureDateFilter(reports) {
  const dates = [...new Set(reports.map((report) => report.date).filter(Boolean))];

  archiveDateEl.innerHTML = [
    '<option value="">전체 날짜</option>',
    ...dates.map(
      (date) => `<option value="${escapeHtml(date)}">${escapeHtml(date)}</option>`,
    ),
  ].join("");
  archiveDateEl.disabled = dates.length === 0;
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

    publishedReports = Array.isArray(reports)
      ? reports
          .filter(
            (report) =>
              report &&
              typeof report === "object" &&
              report.status === "published_api",
          )
          .sort((a, b) => String(b.date || "").localeCompare(String(a.date || "")))
      : [];

    if (publishedReports.length === 0) {
      siteStatusEl.textContent = "No reports";
      reportCountEl.textContent = "0";
      latestDateEl.textContent = "-";
      latestEl.innerHTML = `<div class="empty">아직 정식 발행된 리포트가 없습니다.</div>`;
      reportListEl.innerHTML = `<div class="empty">리포트 목록이 비어 있습니다.</div>`;
      archiveResultCountEl.textContent = "전체 공개 리포트 0건";
      return;
    }

    const latest = publishedReports[0];

    siteStatusEl.textContent = "Active";
    reportCountEl.textContent = String(publishedReports.length);
    latestDateEl.textContent = latest.date || "-";
    latestEl.classList.remove("latest-card", "loading-card");
    latestEl.innerHTML = renderReportCard(latest, true);

    configureDateFilter(publishedReports);
    renderArchive();
  } catch (error) {
    console.error(error);

    siteStatusEl.textContent = "Error";
    reportCountEl.textContent = "-";
    latestDateEl.textContent = "-";
    archiveDateEl.disabled = true;
    archiveResultCountEl.textContent = "리포트 데이터를 확인할 수 없습니다.";
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

archiveDateEl.addEventListener("change", (event) => {
  renderArchive(event.target.value);
});

init();
