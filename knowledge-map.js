import {
  buildGraphIndex,
  calculateCategoryConnections,
  collectDescendants,
  createOverviewLayout,
  positionsOnRing,
  truncateLabel,
} from "./knowledge-map-core.mjs";

const SVG_NS = "http://www.w3.org/2000/svg";
const CATEGORY_COLORS = [
  "#7257a6",
  "#3f7b78",
  "#9a751f",
  "#397793",
  "#3f6f9f",
  "#4f8265",
  "#4f7c58",
  "#9a584a",
  "#975b82",
  "#536d9a",
];
const TYPE_LABELS = {
  middle: "중분류",
  sub: "소분류",
  detail: "최소분류",
  report: "리포트",
  concept: "공유 개념",
};

const svg = document.getElementById("knowledge-map");
const detailsEl = document.getElementById("map-details");
const resetEl = document.getElementById("map-reset");
const searchEl = document.getElementById("map-search");
const searchResultsEl = document.getElementById("map-search-results");
const titleEl = document.getElementById("map-title");
const descriptionEl = document.getElementById("map-description");
const errorEl = document.getElementById("map-error");

let graph;
let index;
let connectionData;
let selectedCategoryId = null;
let categoryColor = new Map();

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function svgElement(name, attributes = {}) {
  const element = document.createElementNS(SVG_NS, name);
  Object.entries(attributes).forEach(([key, value]) => {
    element.setAttribute(key, String(value));
  });
  return element;
}

function clearMap() {
  svg.replaceChildren();
}

function appendLine(group, from, to, className, width = 1) {
  if (!from || !to) return;
  group.append(
    svgElement("line", {
      x1: from.x,
      y1: from.y,
      x2: to.x,
      y2: to.y,
      class: className,
      "stroke-width": width,
    }),
  );
}

function categoryIndex(categoryId) {
  return Math.max(
    0,
    index.categories.findIndex((category) => category.id === categoryId),
  );
}

function addText(group, label, options = {}) {
  const text = svgElement("text", {
    x: options.x || 0,
    y: options.y || 0,
    class: options.className || "map-node-label",
    "text-anchor": options.anchor || "middle",
  });
  const segments = String(label).split("·");
  if (segments.length === 1 || options.singleLine) {
    text.textContent = truncateLabel(label, options.maximum || 20);
  } else {
    segments.slice(0, 2).forEach((segment, idx) => {
      const tspan = svgElement("tspan", {
        x: options.x || 0,
        dy: idx === 0 ? "0" : "1.15em",
      });
      tspan.textContent = segment.trim();
      text.append(tspan);
    });
  }
  group.append(text);
}

function addInteractiveNode({ node, position, radius, className, color, subtitle, onSelect }) {
  const group = svgElement("g", {
    class: `map-node ${className}`,
    transform: `translate(${position.x} ${position.y})`,
    tabindex: "0",
    role: "button",
    "aria-label": `${node.label}${subtitle ? `, ${subtitle}` : ""}`,
    "data-node-id": node.id,
  });
  const title = svgElement("title");
  title.textContent = `${node.label}${subtitle ? ` · ${subtitle}` : ""}`;
  group.append(title);
  group.append(
    svgElement("circle", {
      r: radius,
      fill: color || "#fffdf8",
    }),
  );
  addText(group, node.label, {
    y: className.includes("category") ? -2 : radius + 17,
    className: className.includes("category")
      ? "map-category-label"
      : "map-node-label",
    maximum: className.includes("report") ? 14 : 16,
    singleLine: !className.includes("category"),
  });
  if (subtitle && className.includes("category")) {
    addText(group, subtitle, {
      y: 28,
      className: "map-node-metric",
      maximum: 18,
      singleLine: true,
    });
  }
  group.addEventListener("click", () => onSelect(node));
  group.addEventListener("keydown", (event) => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      onSelect(node);
    }
  });
  svg.append(group);
  return group;
}

function reportLink(report, kind) {
  const url = kind === "pdf" ? report.pdf_url : report.html_url;
  if (!url) return "";
  return `<a class="detail-link" href="${escapeHtml(url)}" target="_blank" rel="noopener">${kind.toUpperCase()} 보기</a>`;
}

function reportsForConcept(conceptId) {
  return (index.conceptReports.get(conceptId) || [])
    .map((reportId) => index.nodes.get(reportId))
    .filter(Boolean)
    .sort((left, right) => String(right.date).localeCompare(String(left.date)));
}

function conceptsForReport(reportId) {
  return (index.reportConcepts.get(reportId) || [])
    .map((conceptId) => index.nodes.get(conceptId))
    .filter(Boolean)
    .sort((left, right) => (right.report_count || 0) - (left.report_count || 0));
}

function selectDetail(node) {
  if (node.type === "report") {
    const concepts = conceptsForReport(node.id);
    detailsEl.innerHTML = `
      <p class="section-kicker">REPORT</p>
      <h2>${escapeHtml(node.label)}</h2>
      <p class="detail-meta">${escapeHtml(node.date)} · ${escapeHtml(node.category_path.join(" › "))}</p>
      <div class="detail-actions">${reportLink(node, "pdf")}${reportLink(node, "html")}</div>
      <h3>연결된 공유 개념</h3>
      <div class="detail-chip-list">
        ${concepts.length ? concepts.map((concept) => `<button type="button" data-focus-node="${escapeHtml(concept.id)}">${escapeHtml(concept.label)}</button>`).join("") : "<span>아직 공유 개념이 없습니다.</span>"}
      </div>
    `;
  } else if (node.type === "concept") {
    const reports = reportsForConcept(node.id);
    detailsEl.innerHTML = `
      <p class="section-kicker">SHARED CONCEPT</p>
      <h2>${escapeHtml(node.label)}</h2>
      <p class="detail-meta">${escapeHtml(node.concept_type || "concept")} · ${reports.length}개 리포트 · ${node.main_categories.length}개 대분류</p>
      <p>이 개념이 실제로 확인된 리포트입니다. 항목을 선택하면 해당 대분류의 지도와 근거 리포트를 함께 볼 수 있습니다.</p>
      <div class="detail-report-list">
        ${reports.map((report) => `<button type="button" data-report-id="${escapeHtml(report.id)}"><span>${escapeHtml(report.main_category)}</span>${escapeHtml(report.label)}</button>`).join("")}
      </div>
    `;
  } else {
    const descendants = collectDescendants(node.id, index);
    const reports = [...descendants]
      .map((id) => index.nodes.get(id))
      .filter((item) => item?.type === "report");
    detailsEl.innerHTML = `
      <p class="section-kicker">${escapeHtml(TYPE_LABELS[node.type] || "CATEGORY")}</p>
      <h2>${escapeHtml(node.label)}</h2>
      <p>이 분류 아래에 ${reports.length}개의 발행 리포트가 있습니다.</p>
      <div class="detail-report-list">
        ${reports.map((report) => `<button type="button" data-report-id="${escapeHtml(report.id)}">${escapeHtml(report.label)}</button>`).join("")}
      </div>
    `;
  }

  detailsEl.querySelectorAll("[data-focus-node]").forEach((button) => {
    button.addEventListener("click", () => {
      const concept = index.nodes.get(button.dataset.focusNode);
      if (concept) selectDetail(concept);
    });
  });
  detailsEl.querySelectorAll("[data-report-id]").forEach((button) => {
    button.addEventListener("click", () => focusReport(button.dataset.reportId));
  });
}

function renderOverview() {
  selectedCategoryId = null;
  clearMap();
  svg.setAttribute("viewBox", "0 0 1200 820");
  titleEl.textContent = "대분류 연결 지도";
  descriptionEl.textContent = "공유 개념 연결이 가장 많은 대분류가 중앙에 배치됩니다. 대분류를 선택하면 세부 지도가 펼쳐집니다.";
  const layout = createOverviewLayout(index.categories, connectionData.scores, {
    width: 1200,
    height: 820,
  });
  const edgeGroup = svgElement("g", { class: "map-edges" });
  svg.append(edgeGroup);

  for (const [pairId, weight] of connectionData.pairs.entries()) {
    const [leftId, rightId] = pairId.split("|");
    appendLine(
      edgeGroup,
      layout.positions.get(leftId),
      layout.positions.get(rightId),
      "map-edge category-connection",
      Math.min(1 + weight * 0.45, 5),
    );
  }

  for (const category of index.categories) {
    const score = connectionData.scores.get(category.id);
    const isHub = category.id === layout.hub.id;
    addInteractiveNode({
      node: category,
      position: layout.positions.get(category.id),
      radius: isHub ? 76 : 58,
      className: `category-node ${isHub ? "hub-node" : ""}`,
      color: categoryColor.get(category.id),
      subtitle: `${score.reports}개 리포트 · ${score.concepts}개 공유 개념`,
      onSelect: renderCategory,
    });
  }

  const hubScore = connectionData.scores.get(layout.hub.id);
  detailsEl.innerHTML = `
    <p class="section-kicker">MOST CONNECTED</p>
    <h2>${escapeHtml(layout.hub.label)}</h2>
    <p>현재 ${hubScore.crossLinks}개의 대분류 간 개념 연결을 가진 중심 분류입니다. 지도에서 원하는 대분류를 선택하면 중·소분류와 리포트가 펼쳐집니다.</p>
    <div class="detail-category-grid">
      ${index.categories.map((category) => `<button type="button" data-category-id="${escapeHtml(category.id)}"><i style="--node-color:${categoryColor.get(category.id)}"></i>${escapeHtml(category.label)}</button>`).join("")}
    </div>
  `;
  detailsEl.querySelectorAll("[data-category-id]").forEach((button) => {
    button.addEventListener("click", () => {
      const category = index.nodes.get(button.dataset.categoryId);
      if (category) renderCategory(category);
    });
  });
}

function layerNodes(descendants, type) {
  return [...descendants]
    .map((id) => index.nodes.get(id))
    .filter((node) => node?.type === type)
    .sort((left, right) => String(left.label).localeCompare(String(right.label), "ko"));
}

function renderCategory(category, focusNodeId = null) {
  selectedCategoryId = category.id;
  clearMap();
  svg.setAttribute("viewBox", "0 0 1200 1000");
  titleEl.textContent = `${category.label} 지식 궤도`;
  descriptionEl.textContent = "중앙에서 바깥으로 중분류, 소분류, 최소분류, 리포트, 공유 개념이 이어집니다. 점선은 다른 대분류와의 연결입니다.";
  const center = { x: 600, y: 500 };
  const descendants = collectDescendants(category.id, index);
  const layers = {
    middle: layerNodes(descendants, "middle"),
    sub: layerNodes(descendants, "sub"),
    detail: layerNodes(descendants, "detail"),
    report: layerNodes(descendants, "report"),
  };
  const positions = new Map([[category.id, center]]);
  [
    ["middle", 105],
    ["sub", 165],
    ["detail", 225],
    ["report", 290],
  ].forEach(([type, radius], indexValue) => {
    const ring = positionsOnRing(layers[type], center, radius, -Math.PI / 2 + indexValue * 0.18);
    ring.forEach((position, id) => positions.set(id, position));
  });

  const relevantConcepts = [
    ...new Set(layers.report.flatMap((report) => index.reportConcepts.get(report.id) || [])),
  ]
    .map((id) => index.nodes.get(id))
    .filter(Boolean)
    .sort((left, right) => (right.report_count || 0) - (left.report_count || 0))
    .slice(0, 10);
  positionsOnRing(relevantConcepts, center, 375, -Math.PI / 2 + 0.1).forEach((position, id) => positions.set(id, position));

  const externalCategories = index.categories.filter((item) => item.id !== category.id);
  positionsOnRing(externalCategories, center, 465, -Math.PI / 2).forEach((position, id) => positions.set(id, position));

  const edgeGroup = svgElement("g", { class: "map-edges" });
  svg.append(edgeGroup);
  const visibleIds = new Set(positions.keys());
  graph.edges
    .filter((edge) => edge.kind === "hierarchy" && visibleIds.has(edge.source) && visibleIds.has(edge.target))
    .forEach((edge) => appendLine(edgeGroup, positions.get(edge.source), positions.get(edge.target), "map-edge hierarchy-connection"));
  graph.edges
    .filter((edge) => edge.kind === "concept" && visibleIds.has(edge.source) && visibleIds.has(edge.target))
    .forEach((edge) => appendLine(edgeGroup, positions.get(edge.source), positions.get(edge.target), "map-edge concept-connection", 2));

  relevantConcepts.forEach((concept) => {
    const connectedCategoryIds = new Set(
      reportsForConcept(concept.id)
        .map((report) => index.reportCategory.get(report.id))
        .filter((id) => id && id !== category.id),
    );
    connectedCategoryIds.forEach((categoryId) => {
      appendLine(edgeGroup, positions.get(concept.id), positions.get(categoryId), "map-edge cross-connection", 1.5);
    });
  });

  addInteractiveNode({
    node: category,
    position: center,
    radius: 70,
    className: "category-node hub-node",
    color: categoryColor.get(category.id),
    subtitle: `${layers.report.length}개 리포트`,
    onSelect: selectDetail,
  });
  ["middle", "sub", "detail"].forEach((type) => {
    layers[type].forEach((node) => addInteractiveNode({
      node,
      position: positions.get(node.id),
      radius: type === "middle" ? 22 : 17,
      className: `taxonomy-node ${type}-node`,
      color: "#fffdf8",
      subtitle: TYPE_LABELS[type],
      onSelect: selectDetail,
    }));
  });
  layers.report.forEach((node) => addInteractiveNode({
    node,
    position: positions.get(node.id),
    radius: node.id === focusNodeId ? 31 : 25,
    className: `report-node ${node.id === focusNodeId ? "focused-node" : ""}`,
    color: "#fffdf8",
    subtitle: node.date,
    onSelect: selectDetail,
  }));
  relevantConcepts.forEach((node) => addInteractiveNode({
    node,
    position: positions.get(node.id),
    radius: node.id === focusNodeId ? 29 : 23,
    className: `concept-node ${node.id === focusNodeId ? "focused-node" : ""}`,
    color: "#f4e7bd",
    subtitle: `${node.report_count}개 리포트`,
    onSelect: selectDetail,
  }));
  externalCategories.forEach((node) => addInteractiveNode({
    node,
    position: positions.get(node.id),
    radius: 32,
    className: "category-node external-category-node",
    color: categoryColor.get(node.id),
    subtitle: "다른 대분류",
    onSelect: renderCategory,
  }));

  if (focusNodeId && index.nodes.has(focusNodeId)) {
    selectDetail(index.nodes.get(focusNodeId));
  } else {
    selectDetail(category);
  }
}

function focusReport(reportId) {
  const report = index.nodes.get(reportId);
  if (!report) return;
  const category = index.categoryByLabel.get(report.main_category);
  if (category) renderCategory(category, report.id);
}

function renderSearchResults(query) {
  const needle = query.trim().toLocaleLowerCase("ko");
  if (!needle) {
    searchResultsEl.hidden = true;
    searchResultsEl.replaceChildren();
    return;
  }
  const matches = [...index.nodes.values()]
    .filter((node) => ["report", "concept"].includes(node.type))
    .filter((node) => node.label.toLocaleLowerCase("ko").includes(needle))
    .sort((left, right) => (left.type === right.type ? 0 : left.type === "report" ? -1 : 1))
    .slice(0, 12);
  searchResultsEl.hidden = false;
  searchResultsEl.innerHTML = matches.length
    ? matches.map((node) => `<button type="button" data-search-node="${escapeHtml(node.id)}"><span>${escapeHtml(TYPE_LABELS[node.type])}</span>${escapeHtml(node.label)}</button>`).join("")
    : "<p>일치하는 리포트나 공유 개념이 없습니다.</p>";
  searchResultsEl.querySelectorAll("[data-search-node]").forEach((button) => {
    button.addEventListener("click", () => {
      const node = index.nodes.get(button.dataset.searchNode);
      searchResultsEl.hidden = true;
      if (node.type === "report") {
        focusReport(node.id);
        return;
      }
      const reports = reportsForConcept(node.id);
      const preferred = reports.find((report) => index.reportCategory.get(report.id) === selectedCategoryId) || reports[0];
      if (preferred) {
        const category = index.categoryByLabel.get(preferred.main_category);
        renderCategory(category, node.id);
      }
    });
  });
}

async function loadJson(path) {
  const response = await fetch(path, { cache: "no-store" });
  if (!response.ok) throw new Error(`${path} 데이터를 불러오지 못했습니다.`);
  return response.json();
}

async function init() {
  try {
    const [taxonomy, graphData] = await Promise.all([
      loadJson("public/api/v1/taxonomy.json"),
      loadJson("public/api/v1/knowledge-graph.json"),
    ]);
    graph = graphData;
    index = buildGraphIndex(graph);
    connectionData = calculateCategoryConnections(index);
    categoryColor = new Map(
      index.categories.map((category, idx) => [category.id, CATEGORY_COLORS[idx % CATEGORY_COLORS.length]]),
    );
    if (taxonomy.category_order.length !== index.categories.length) {
      throw new Error("taxonomy와 지식 그래프의 대분류 개수가 다릅니다.");
    }
    document.getElementById("map-category-count").textContent = String(index.categories.length);
    document.getElementById("map-report-count").textContent = String(index.reports.length);
    document.getElementById("map-concept-count").textContent = String(graph.stats?.concepts || 0);
    renderOverview();
  } catch (error) {
    console.error(error);
    errorEl.hidden = false;
    errorEl.textContent = `지식 지도 데이터를 불러오지 못했습니다. ${error.message}`;
    svg.hidden = true;
  }
}

resetEl.addEventListener("click", renderOverview);
searchEl.addEventListener("input", () => renderSearchResults(searchEl.value));
document.addEventListener("click", (event) => {
  if (!event.target.closest(".map-search-wrap")) searchResultsEl.hidden = true;
});

init();
