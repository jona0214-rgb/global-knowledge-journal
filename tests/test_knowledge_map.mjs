import assert from "node:assert/strict";
import fs from "node:fs/promises";
import {
  buildGraphIndex,
  calculateCategoryConnections,
  collectDescendants,
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

assert.match(indexHtml, /href="knowledge-map\.html"/);
assert.match(mapHtml, /id="knowledge-map"/);
assert.match(mapHtml, /type="module" src="knowledge-map\.js"/);
assert.match(mapSource, /public\/api\/v1\/knowledge-graph\.json/);
assert.match(mapSource, /renderCategory/);
assert.match(mapSource, /data-report-id/);

console.log("knowledge_map_test=ok");
