import assert from "node:assert/strict";
import fs from "node:fs/promises";
import {
  buildGraphIndex,
  calculateCategoryConnections,
  circularAngleDistance,
  collectDescendants,
  createCategoryDetailLayout,
  createOverviewLayout,
} from "../knowledge-map-core.mjs";

const graph = JSON.parse(
  await fs.readFile(new URL("../public/api/v1/knowledge-graph.json", import.meta.url), "utf8"),
);
const indexHtml = await fs.readFile(
  new URL("../index.html", import.meta.url),
  "utf8",
);
const mapHtml = await fs.readFile(
  new URL("../knowledge-map.html", import.meta.url),
  "utf8",
);
const mapSource = await fs.readFile(
  new URL("../knowledge-map.js", import.meta.url),
  "utf8",
);

const index = buildGraphIndex(graph);
const connections = calculateCategoryConnections(index);
const layout = createOverviewLayout(index.categories, connections.scores);

assert.equal(index.categories.length, 10);
assert.equal(index.reports.length, graph.stats.reports);
assert.equal(index.conceptReports.size, graph.stats.concepts);
assert.equal(layout.positions.size, 10);
assert.ok(layout.hub);
assert.deepEqual(layout.positions.get(layout.hub.id), { x: 600, y: 410 });
assert.ok((connections.scores.get(layout.hub.id)?.crossLinks || 0) > 0);

for (const category of index.categories) {
  const descendants = collectDescendants(category.id, index);
  const reportCount = [...descendants]
    .map((id) => index.nodes.get(id))
    .filter((node) => node?.type === "report").length;
  assert.equal(reportCount, connections.scores.get(category.id).reports);
}

const selectedCategory = index.categoryByLabel.get("역사·문화");
const selectedDescendants = collectDescendants(selectedCategory.id, index);
const selectedReports = [...selectedDescendants]
  .map((id) => index.nodes.get(id))
  .filter((node) => node?.type === "report");
const selectedConcepts = [
  ...new Set(selectedReports.flatMap((report) => index.reportConcepts.get(report.id) || [])),
]
  .map((id) => index.nodes.get(id))
  .filter(Boolean)
  .sort((left, right) => (right.report_count || 0) - (left.report_count || 0))
  .slice(0, 10);
const detailLayout = createCategoryDetailLayout(
  selectedCategory,
  index,
  selectedConcepts,
);
const repeatedDetailLayout = createCategoryDetailLayout(
  selectedCategory,
  index,
  selectedConcepts,
);
assert.deepEqual(
  [...detailLayout.positions.entries()],
  [...repeatedDetailLayout.positions.entries()],
);

for (const type of ["sub", "detail", "report"]) {
  for (const node of detailLayout.layers[type]) {
    const parentId = index.hierarchyParent.get(node.id);
    const nodeAngle = detailLayout.angles.get(node.id);
    const parentAngle = detailLayout.angles.get(parentId);
    if (Number.isFinite(parentAngle)) {
      assert.ok(
        circularAngleDistance(nodeAngle, parentAngle) < Math.PI / 2,
        `${node.label} should remain in its parent branch`,
      );
    }
  }
}

for (const concept of selectedConcepts) {
  assert.ok(detailLayout.positions.has(concept.id));
  assert.ok(detailLayout.conceptTargets.has(concept.id));
  assert.ok(
    circularAngleDistance(
      detailLayout.conceptAngles.get(concept.id),
      detailLayout.conceptTargets.get(concept.id),
    ) < Math.PI / 2,
    `${concept.label} should stay near its evidence-weighted target`,
  );
}

assert.match(indexHtml, /href="knowledge-map\.html"/);
assert.match(mapHtml, /id="knowledge-map"/);
assert.match(mapHtml, /type="module" src="knowledge-map\.js"/);
assert.match(mapHtml, /id="map-reset"/);
assert.match(mapHtml, /기본 대분류 지도로 돌아가기/);
assert.match(mapHtml, /외부 대분류/);
assert.match(mapSource, /public\/api\/v1\/knowledge-graph\.json/);
assert.match(mapSource, /renderCategory/);
assert.match(mapSource, /createCategoryDetailLayout/);
assert.match(mapSource, /data-report-id/);
assert.match(mapSource, /function resetMapState/);
assert.match(mapSource, /searchEl\.value = ""/);
assert.match(mapSource, /resetEl\.disabled = true/);
assert.doesNotMatch(mapSource, /className: "map-node-metric"/);

console.log("knowledge_map_test=ok");
