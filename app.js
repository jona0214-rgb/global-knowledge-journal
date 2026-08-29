const latestEl = document.getElementById("latest-report");
const reportListEl = document.getElementById("report-list");
const reportCountEl = document.getElementById("report-count");
const latestDateEl = document.getElementById("latest-date");
const siteStatusEl = document.getElementById("site-status");
const automationStatusEl = document.getElementById("automation-status");
const generationHistoryEl = document.getElementById("generation-history");
const archiveCategoryEl = document.getElementById("archive-category");
const archiveMonthEl = document.getElementById("archive-month");
const archiveSortEl = document.getElementById("archive-sort");
const archiveResetEl = document.getElementById("archive-reset");
const archiveResultCountEl = document.getElementById("archive-result-count");

const CATEGORY_ORDER = [
  "인문·철학",
  "사회·정치·법",
  "경제·경영",
  "과학·수학",
  "기술·공학",
  "생명·건강",
  "자연·환경·지리",
  "역사·문화",
  "예술·디자인",
  "언어·미디어·지식",
];

const LEGACY_MIDDLE_CATEGORY_MAP = {
  "식생활·가전문화": "역사·문화",
  도시인프라: "기술·공학",
  행정인프라: "사회·정치·법",
  에너지정책: "경제·경영",
  "위험과 제도": "경제·경영",
  "재료와 문명": "기술·공학",
  물환경공학: "기술·공학",
  동물행동: "생명·건강",
  "생물과 구조": "과학·수학",
  생태환경: "자연·환경·지리",
};

const LEGACY_MAIN_CATEGORY_MAP = {
  "인문·철학": "인문·철학",
  "역사·문화": "역사·문화",
  "과학·공학": "기술·공학",
  "경제·사회": "경제·경영",
  "자연사·생태": "자연·환경·지리",
  "예술·미학": "예술·디자인",
  "생활기술·일상문화": "기술·공학",
  "언어·문자": "언어·미디어·지식",
};

const CATEGORY_CLASS_MAP = new Map(
  CATEGORY_ORDER.map((category, index) => [category, `category-tone-${index + 1}`]),
);

let publishedReports = [];

function formatKstTimestamp(value) {
  const date = new Date(String(value || ""));
  if (Number.isNaN(date.getTime())) {
    return "-";
  }
  return new Intl.DateTimeFormat("ko-KR", {
    timeZone: "Asia/Seoul",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  }).format(date);
}

function formatDuration(totalSeconds) {
  const seconds = Number(totalSeconds);
  if (!Number.isFinite(seconds) || seconds < 0) {
    return "-";
  }
  const minutes = Math.floor(seconds / 60);
  const remainder = Math.round(seconds % 60);
  return minutes > 0 ? `${minutes}분 ${remainder}초` : `${remainder}초`;
}

function renderGenerationHistory(history) {
  const entries = Array.isArray(history)
    ? history.filter((item) => item && typeof item === "object").slice(0, 10)
    : [];

  generationHistoryEl.classList.remove("loading-card");
  if (entries.length === 0) {
    automationStatusEl.textContent = "측정 대기";
    generationHistoryEl.innerHTML = `
      <div class="empty">05:00 예약 변경 이후의 측정 기록이 아직 없습니다.</div>
    `;
    return;
  }

  const latest = entries[0];
  automationStatusEl.textContent = `${latest.date || "-"} · 정상`;
  generationHistoryEl.innerHTML = entries
    .map((entry) => {
      const scheduleLabel = entry.scheduled_for_kst
        ? formatKstTimestamp(entry.scheduled_for_kst)
        : "수동 실행";
      const runLink = entry.run_url
        ? `<a href="${escapeHtml(entry.run_url)}" target="_blank" rel="noopener">Actions 로그</a>`
        : "";
      return `
        <article class="timeline-card">
          <div class="timeline-heading">
            <strong>${escapeHtml(entry.date || "-")}</strong>
            <span>${escapeHtml(entry.title || "제목 없음")}</span>
            ${runLink}
          </div>
          <dl class="timeline-grid">
            <div><dt>예약</dt><dd>${escapeHtml(scheduleLabel)}</dd></div>
            <div><dt>실제 시작</dt><dd>${escapeHtml(formatKstTimestamp(entry.workflow_started_at))}</dd></div>
            <div><dt>저장 완료</dt><dd>${escapeHtml(formatKstTimestamp(entry.catalog_updated_at))}</dd></div>
            <div><dt>예약 지연</dt><dd>${escapeHtml(formatDuration(entry.scheduler_delay_seconds))}</dd></div>
            <div><dt>환경 준비</dt><dd>${escapeHtml(formatDuration(entry.setup_duration_seconds))}</dd></div>
            <div><dt>생성·검증</dt><dd>${escapeHtml(formatDuration(entry.generation_duration_seconds))}</dd></div>
          </dl>
        </article>
      `;
    })
    .join("");
}

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

function getRawCategory(report) {
  const category =
    report.category && typeof report.category === "object" ? report.category : {};

  return {
    main:
      report.main_category ||
      category.main ||
      (typeof report.category === "string" ? report.category : ""),
    middle: report.mid_category || category.middle || "",
    sub: report.sub_category || category.sub || "",
    detail: report.detail_category || category.detail || "",
  };
}

function getMainCategory(report) {
  const category = getRawCategory(report);

  if (CATEGORY_ORDER.includes(category.main)) {
    return category.main;
  }

  return (
    LEGACY_MIDDLE_CATEGORY_MAP[category.middle] ||
    LEGACY_MAIN_CATEGORY_MAP[category.main] ||
    category.main ||
    "미분류"
  );
}

function getFieldPath(report) {
  const { middle, sub, detail } = getRawCategory(report);
  const seen = new Set();

  return [middle, sub, detail]
    .map((value) => String(value || "").trim())
    .filter((value) => {
      if (!value || seen.has(value)) {
        return false;
      }
      seen.add(value);
      return true;
    })
    .join(" › ");
}

function getMonthKey(date) {
  const match = String(date || "").match(/^(\d{4})-(\d{2})/);
  return match ? `${match[1]}-${match[2]}` : "";
}

function formatMonth(monthKey) {
  const match = String(monthKey).match(/^(\d{4})-(\d{2})$/);
  if (!match) {
    return monthKey;
  }

  return `${match[1]}년 ${Number(match[2])}월`;
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
  const mainCategory = getMainCategory(report);
  const fieldPath = getFieldPath(report);
  const categoryClass = CATEGORY_CLASS_MAP.get(mainCategory) || "category-tone-default";

  return `
    <article class="${isLatest ? "latest-card" : "report-card"}">
      <div class="report-meta">
        <time class="badge" datetime="${escapeHtml(report.date || "")}">
          ${escapeHtml(report.date || "-")}
        </time>
        <span class="badge published-badge">정식 발행</span>
      </div>

      <dl class="report-taxonomy">
        <div class="taxonomy-item taxonomy-main">
          <dt>대분류</dt>
          <dd class="category-pill ${categoryClass}">${escapeHtml(mainCategory)}</dd>
        </div>
        ${
          fieldPath
            ? `<div class="taxonomy-item taxonomy-field">
                <dt>분야</dt>
                <dd>${escapeHtml(fieldPath)}</dd>
              </div>`
            : ""
        }
      </dl>

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

function updateArchiveUrl() {
  const params = new URLSearchParams(window.location.search);
  const category = archiveCategoryEl.value;
  const month = archiveMonthEl.value;
  const sort = archiveSortEl.value;

  if (category) {
    params.set("category", category);
  } else {
    params.delete("category");
  }

  if (month) {
    params.set("month", month);
  } else {
    params.delete("month");
  }

  if (sort === "oldest") {
    params.set("sort", sort);
  } else {
    params.delete("sort");
  }

  const query = params.toString();
  const nextUrl = `${window.location.pathname}${query ? `?${query}` : ""}${window.location.hash}`;
  window.history.replaceState(null, "", nextUrl);
}

function renderArchive({ updateUrl = true } = {}) {
  const selectedCategory = archiveCategoryEl.value;
  const selectedMonth = archiveMonthEl.value;
  const sortDirection = archiveSortEl.value;

  const filteredReports = publishedReports
    .filter(
      (report) =>
        (!selectedCategory || getMainCategory(report) === selectedCategory) &&
        (!selectedMonth || getMonthKey(report.date) === selectedMonth),
    )
    .sort((left, right) => {
      const comparison = String(right.date || "").localeCompare(
        String(left.date || ""),
      );
      return sortDirection === "oldest" ? -comparison : comparison;
    });

  reportListEl.classList.remove("loading-card");
  const activeLabels = [
    selectedCategory,
    selectedMonth ? formatMonth(selectedMonth) : "",
  ].filter(Boolean);
  archiveResultCountEl.textContent = activeLabels.length
    ? `${activeLabels.join(" · ")} · ${filteredReports.length}건`
    : `전체 공개 리포트 ${filteredReports.length}건`;

  archiveResetEl.disabled =
    !selectedCategory && !selectedMonth && sortDirection === "newest";

  if (filteredReports.length === 0) {
    reportListEl.innerHTML = `
      <div class="empty">
        선택한 대분류와 발행 월에 해당하는 공개 리포트가 없습니다.
      </div>
    `;
  } else {
    reportListEl.innerHTML = filteredReports
      .map((report) => renderReportCard(report))
      .join("");
  }

  if (updateUrl) {
    updateArchiveUrl();
  }
}

function configureArchiveFilters(reports) {
  const categoryCounts = new Map();
  const monthCounts = new Map();

  reports.forEach((report) => {
    const category = getMainCategory(report);
    const month = getMonthKey(report.date);
    categoryCounts.set(category, (categoryCounts.get(category) || 0) + 1);
    if (month) {
      monthCounts.set(month, (monthCounts.get(month) || 0) + 1);
    }
  });

  const categories = [...categoryCounts.keys()].sort((left, right) => {
    const leftIndex = CATEGORY_ORDER.indexOf(left);
    const rightIndex = CATEGORY_ORDER.indexOf(right);
    return (
      (leftIndex === -1 ? CATEGORY_ORDER.length : leftIndex) -
      (rightIndex === -1 ? CATEGORY_ORDER.length : rightIndex)
    );
  });
  const months = [...monthCounts.keys()].sort((left, right) =>
    right.localeCompare(left),
  );

  archiveCategoryEl.innerHTML = [
    '<option value="">전체 대분류</option>',
    ...categories.map(
      (category) =>
        `<option value="${escapeHtml(category)}">${escapeHtml(category)} (${categoryCounts.get(category)})</option>`,
    ),
  ].join("");

  archiveMonthEl.innerHTML = [
    '<option value="">전체 월</option>',
    ...months.map(
      (month) =>
        `<option value="${escapeHtml(month)}">${escapeHtml(formatMonth(month))} (${monthCounts.get(month)})</option>`,
    ),
  ].join("");

  archiveCategoryEl.disabled = categories.length === 0;
  archiveMonthEl.disabled = months.length === 0;

  const params = new URLSearchParams(window.location.search);
  const requestedCategory = params.get("category") || "";
  const requestedMonth = params.get("month") || "";
  const requestedSort = params.get("sort") || "newest";

  archiveCategoryEl.value = categories.includes(requestedCategory)
    ? requestedCategory
    : "";
  archiveMonthEl.value = months.includes(requestedMonth) ? requestedMonth : "";
  archiveSortEl.value = requestedSort === "oldest" ? "oldest" : "newest";
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
    const [reports, generationHistory] = await Promise.all([
      loadJson("public/reports.json"),
      loadJson("public/generation-history.json").catch(() => []),
    ]);

    renderGenerationHistory(generationHistory);

    publishedReports = Array.isArray(reports)
      ? reports
          .filter(
            (report) =>
              report &&
              typeof report === "object" &&
              report.status === "published_api",
          )
          .sort((left, right) =>
            String(right.date || "").localeCompare(String(left.date || "")),
          )
      : [];

    if (publishedReports.length === 0) {
      siteStatusEl.textContent = "No reports";
      reportCountEl.textContent = "0";
      latestDateEl.textContent = "-";
      latestEl.innerHTML = `<div class="empty">아직 정식 발행된 리포트가 없습니다.</div>`;
      reportListEl.innerHTML = `<div class="empty">리포트 목록이 비어 있습니다.</div>`;
      archiveResultCountEl.textContent = "전체 공개 리포트 0건";
      archiveCategoryEl.disabled = true;
      archiveMonthEl.disabled = true;
      archiveResetEl.disabled = true;
      return;
    }

    const latest = publishedReports[0];

    siteStatusEl.textContent = "Active";
    reportCountEl.textContent = String(publishedReports.length);
    latestDateEl.textContent = latest.date || "-";
    latestEl.classList.remove("latest-card", "loading-card");
    latestEl.innerHTML = renderReportCard(latest, true);

    configureArchiveFilters(publishedReports);
    renderArchive();
  } catch (error) {
    console.error(error);

    siteStatusEl.textContent = "Error";
    automationStatusEl.textContent = "확인 필요";
    reportCountEl.textContent = "-";
    latestDateEl.textContent = "-";
    archiveCategoryEl.disabled = true;
    archiveMonthEl.disabled = true;
    archiveSortEl.disabled = true;
    archiveResetEl.disabled = true;
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

[archiveCategoryEl, archiveMonthEl, archiveSortEl].forEach((element) => {
  element.addEventListener("change", () => renderArchive());
});

archiveResetEl.addEventListener("click", () => {
  archiveCategoryEl.value = "";
  archiveMonthEl.value = "";
  archiveSortEl.value = "newest";
  renderArchive();
});

init();
