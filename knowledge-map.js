import {
  buildGraphIndex,
  calculateCategoryConnections,
  collectDescendants,
  createCategoryDetailLayout,
  createOverviewLayout,
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
    const visibleSegments = segments.slice(0, 2);
    visibleSegments.forEach((segment, idx) => {
      const tspan = svgElement("tspan", {
        x: options.x || 0,
        dy: idx === 0 && options.centered
          ? `${-0.55 * (visibleSegments.length - 1)}em`
          : idx === 0
            ? "0"
            : "1.1em",
      });
      tspan.textContent = segment.trim();
      text.append(tspan);
    });
  }
  group.append(text);
  return text;
}

function categoryLabelFontSize(label, className) {
  const longestSegment = Math.max(
    ...String(label).split("·").map((segment) => segment.trim().length),
  );
  if (className.includes("external-category-node")) {
    return longestSegment >= 7 ? 9 : 11;
  }
  if (longestSegment >= 8) return 13;
  if (longestSegment >= 6) return 15;
  return 17;
}

function appendNodeVisual(group, { radius, className, color }) {
  const visual = svgElement("g", { class: "map-node-visual" });
  const fill = color || "#fffdf8";
  let shape;

  if (className.includes("report-node")) {
    shape = svgElement("rect", {
      x: -21,
      y: -15,
      width: 42,
      height: 30,
      rx: 6,
      fill,
      class: "map-node-shape",
    });
    visual.append(shape);
    visual.append(
      svgElement("path", {
        d: "M 10 -15 L 21 -4 L 10 -4 Z",
        class: "report-fold",
      }),
      svgElement("line", {
        x1: -11,
        y1: 0,
        x2: 8,
        y2: 0,
        class: "report-glyph-line",
      }),
      svgElement("line", {
        x1: -11,
        y1: 6,
        x2: 5,
        y2: 6,
        class: "report-glyph-line",
      }),
    );
  } else if (className.includes("sub-node")) {
    shape = svgElement("rect", {
      x: -39,
      y: -20,
      width: 78,
      height: 40,
      rx: 11,
      fill,
      class: "map-node-shape",
    });
    visual.append(shape);
  } else if (className.includes("detail-node")) {
    shape = svgElement("polygon", {
      points: "0,-18 18,0 0,18 -18,0",
      fill,
      class: "map-node-shape",
    });
    visual.append(shape);
  } else {
    shape = svgElement("circle", {
      r: radius,
      fill,
      class: "map-node-shape",
    });
    visual.append(shape);
  }

  group.append(visual);
}

function containedLabelLines(label, maximumPerLine = 7) {
  const compact = String(label || "").replace(/\s+/g, " ").trim();
  const maximumTotal = maximumPerLine * 2;
  const clipped = compact.length > maximumTotal
    ? `${compact.slice(0, maximumTotal - 1)}…`
    : compact;
  if (clipped.length <= maximumPerLine) return [clipped];

  const preferredBreak = clipped.lastIndexOf(" ", maximumPerLine + 1);
  const breakIndex = preferredBreak >= Math.ceil(maximumPerLine * 0.55)
    ? preferredBreak
    : maximumPerLine;
  return [
    clipped.slice(0, breakIndex).trim(),
    clipped.slice(breakIndex).trim(),
  ].filter(Boolean);
}

function addContainedNodeLabel(group, label, className) {
  const lines = containedLabelLines(label, className.includes("sub-node") ? 8 : 6);
  const text = svgElement("text", {
    x: 0,
    y: 0,
    class: "map-contained-label",
    "text-anchor": "middle",
  });
  lines.forEach((line, indexValue) => {
    const tspan = svgElement("tspan", {
      x: 0,
      y: lines.length === 1 ? 3 : -4 + indexValue * 11,
    });
    tspan.textContent = line;
    text.append(tspan);
  });
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
  appendNodeVisual(group, { radius, className, color });
  const isCategory = className.includes("category");
  const containsTaxonomyLabel = className.includes("middle-node") || className.includes("sub-node");
  const labelElement = containsTaxonomyLabel
    ? addContainedNodeLabel(group, node.label, className)
    : addText(group, node.label, {
      y: isCategory ? 0 : className.includes("report-node") ? 35 : radius + 17,
      className: isCategory
        ? "map-category-label"
        : "map-node-label",
      maximum: className.includes("report") ? 14 : 16,
      singleLine: !isCategory,
      centered: isCategory,
    });
  if (isCategory) {
    labelElement.setAttribute(
      "style",
      `font-size:${categoryLabelFontSize(node.label, className)}px`,
    );
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
  resetEl.disabled = true;
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

function renderCategory(category, focusNodeId = null) {
  selectedCategoryId = category.id;
  resetEl.disabled = false;
  clearMap();
  svg.setAttribute("viewBox", "0 0 1280 1080");
  titleEl.textContent = category.label.endsWith("지식")
    ? `${category.label} 궤도`
    : `${category.label} 지식 궤도`;
  descriptionEl.textContent = "중분류는 원, 소분류는 둥근 사각형, 리포트는 작은 문서 카드로 표시합니다. 최소분류는 복잡도를 낮추기 위해 숨기고 리포트를 가까운 상위 분류에 연결합니다.";
  const center = { x: 640, y: 520 };
  const descendants = collectDescendants(category.id, index);
  const relevantConcepts = [
    ...new Set(
      [...descendants]
        .map((id) => index.nodes.get(id))
        .filter((node) => node?.type === "report")
        .flatMap((report) => index.reportConcepts.get(report.id) || []),
    ),
  ]
    .map((id) => index.nodes.get(id))
    .filter(Boolean)
    .sort((left, right) => (right.report_count || 0) - (left.report_count || 0))
    .slice(0, 10);
  const {
    positions,
    layers,
    externalCategories,
  } = createCategoryDetailLayout(category, index, relevantConcepts, {
    center,
    radii: {
      middle: 128,
      sub: 220,
      detail: 270,
      report: 325,
      concept: 420,
      category: 505,
    },
  });

  const edgeGroup = svgElement("g", { class: "map-edges" });
  svg.append(edgeGroup);
  const visibleIds = new Set(positions.keys());
  const visibleHierarchyNodes = [
    ...layers.middle,
    ...layers.sub,
    ...layers.report,
  ];
  const visibleHierarchyIds = new Set([
    category.id,
    ...visibleHierarchyNodes.map((node) => node.id),
  ]);
  visibleHierarchyNodes.forEach((node) => {
    let parentId = index.hierarchyParent.get(node.id);
    while (parentId && !visibleHierarchyIds.has(parentId)) {
      parentId = index.hierarchyParent.get(parentId);
    }
    if (!parentId) return;
    appendLine(
      edgeGroup,
      positions.get(parentId),
      positions.get(node.id),
      `map-edge hierarchy-connection hierarchy-to-${node.type}`,
    );
  });
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
  ["middle", "sub"].forEach((type) => {
    layers[type].forEach((node) => addInteractiveNode({
      node,
      position: positions.get(node.id),
      radius: type === "middle" ? 34 : 22,
      className: `taxonomy-node ${type}-node`,
      color: type === "middle" ? "#e8ded0" : "#e4efed",
      subtitle: TYPE_LABELS[type],
      onSelect: selectDetail,
    }));
  });
  layers.report.forEach((node) => addInteractiveNode({
    node,
    position: positions.get(node.id),
    radius: node.id === focusNodeId ? 24 : 21,
    className: `report-node ${node.id === focusNodeId ? "focused-node" : ""}`,
    color: "#edf3fa",
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

function resetMapState() {
  searchEl.value = "";
  searchResultsEl.hidden = true;
  searchResultsEl.replaceChildren();
  renderOverview();
}

resetEl.addEventListener("click", resetMapState);
searchEl.addEventListener("input", () => renderSearchResults(searchEl.value));
document.addEventListener("click", (event) => {
  if (!event.target.closest(".map-search-wrap")) searchResultsEl.hidden = true;
});

init();
