const generationHistoryEl = document.getElementById("generation-history");

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

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

function actionLink(url, label) {
  return url
    ? `<a href="${escapeHtml(url)}" target="_blank" rel="noopener">${escapeHtml(label)}</a>`
    : "";
}

function renderGenerationHistory(history) {
  const entries = Array.isArray(history)
    ? history.filter((item) => item && typeof item === "object").slice(0, 30)
    : [];

  generationHistoryEl.classList.remove("loading-card");
  if (entries.length === 0) {
    generationHistoryEl.innerHTML = `
      <div class="empty">자동 생성 기록이 아직 없습니다.</div>
    `;
    return;
  }

  generationHistoryEl.innerHTML = entries
    .map((entry) => {
      const scheduleLabel = entry.scheduled_for_kst
        ? formatKstTimestamp(entry.scheduled_for_kst)
        : "수동 실행";
      const publicationLabel = entry.publication_pushed_at
        ? "공개 승격 완료"
        : "공개 시각 미기록(기존)";
      return `
        <article class="timeline-card">
          <div class="timeline-heading">
            <strong>${escapeHtml(entry.date || "-")}</strong>
            <span>${escapeHtml(entry.title || "제목 없음")}</span>
            <span class="timeline-state">${escapeHtml(publicationLabel)}</span>
          </div>
          <div class="timeline-links">
            ${actionLink(entry.run_url, "생성 Actions 로그")}
            ${actionLink(entry.publication_run_url, "공개 Actions 로그")}
          </div>
          <dl class="timeline-grid">
            <div><dt>생성 예약</dt><dd>${escapeHtml(scheduleLabel)}</dd></div>
            <div><dt>생성 실제 시작</dt><dd>${escapeHtml(formatKstTimestamp(entry.workflow_started_at))}</dd></div>
            <div><dt>스테이징 저장</dt><dd>${escapeHtml(formatKstTimestamp(entry.catalog_updated_at))}</dd></div>
            <div><dt>공개 목표</dt><dd>${escapeHtml(formatKstTimestamp(entry.publication_target_kst))}</dd></div>
            <div><dt>main 승격</dt><dd>${escapeHtml(formatKstTimestamp(entry.publication_pushed_at))}</dd></div>
            <div><dt>예약 지연</dt><dd>${escapeHtml(formatDuration(entry.scheduler_delay_seconds))}</dd></div>
            <div><dt>환경 준비</dt><dd>${escapeHtml(formatDuration(entry.setup_duration_seconds))}</dd></div>
            <div><dt>생성·검증</dt><dd>${escapeHtml(formatDuration(entry.generation_duration_seconds))}</dd></div>
          </dl>
        </article>
      `;
    })
    .join("");
}

async function initLogs() {
  try {
    const response = await fetch("public/generation-history.json", {
      cache: "no-store",
    });
    if (!response.ok) {
      throw new Error("생성 이력 파일을 불러오지 못했습니다.");
    }
    renderGenerationHistory(await response.json());
  } catch (error) {
    console.error(error);
    generationHistoryEl.classList.remove("loading-card");
    generationHistoryEl.innerHTML = `
      <div class="empty">${escapeHtml(error.message)}</div>
    `;
  }
}

initLogs();
