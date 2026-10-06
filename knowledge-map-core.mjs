export function buildGraphIndex(graph) {
  const nodes = new Map((graph.nodes || []).map((node) => [node.id, node]));
  const hierarchyChildren = new Map();
  const conceptReports = new Map();
  const reportConcepts = new Map();

  for (const edge of graph.edges || []) {
    if (edge.kind === "hierarchy") {
      const children = hierarchyChildren.get(edge.source) || [];
      children.push(edge.target);
      hierarchyChildren.set(edge.source, children);
      continue;
    }

    if (edge.kind === "concept") {
      const reports = conceptReports.get(edge.target) || [];
      reports.push(edge.source);
      conceptReports.set(edge.target, reports);

      const concepts = reportConcepts.get(edge.source) || [];
      concepts.push(edge.target);
      reportConcepts.set(edge.source, concepts);
    }
  }

  const reports = [...nodes.values()].filter((node) => node.type === "report");
  const categories = [...nodes.values()]
    .filter((node) => node.type === "category")
    .sort((left, right) => (left.order || 0) - (right.order || 0));
  const categoryByLabel = new Map(categories.map((node) => [node.label, node]));
  const reportCategory = new Map();

  for (const report of reports) {
    const category = categoryByLabel.get(report.main_category);
    if (category) {
      reportCategory.set(report.id, category.id);
    }
  }

  return {
    nodes,
    hierarchyChildren,
    conceptReports,
    reportConcepts,
    reports,
    categories,
    categoryByLabel,
    reportCategory,
  };
}

export function collectDescendants(rootId, index) {
  const descendants = new Set();
  const queue = [...(index.hierarchyChildren.get(rootId) || [])];

  while (queue.length) {
    const nodeId = queue.shift();
    if (descendants.has(nodeId)) {
      continue;
    }
    descendants.add(nodeId);
    queue.push(...(index.hierarchyChildren.get(nodeId) || []));
  }

  return descendants;
}

export function calculateCategoryConnections(index) {
  const scores = new Map(
    index.categories.map((category) => [
      category.id,
      { reports: 0, concepts: 0, crossLinks: 0 },
    ]),
  );
  const pairs = new Map();

  for (const report of index.reports) {
    const categoryId = index.reportCategory.get(report.id);
    if (categoryId && scores.has(categoryId)) {
      scores.get(categoryId).reports += 1;
    }
  }

  for (const reportIds of index.conceptReports.values()) {
    const categoryIds = [
      ...new Set(reportIds.map((id) => index.reportCategory.get(id)).filter(Boolean)),
    ].sort();

    for (const categoryId of categoryIds) {
      scores.get(categoryId).concepts += 1;
    }

    for (let left = 0; left < categoryIds.length; left += 1) {
      for (let right = left + 1; right < categoryIds.length; right += 1) {
        const pairId = `${categoryIds[left]}|${categoryIds[right]}`;
        pairs.set(pairId, (pairs.get(pairId) || 0) + 1);
        scores.get(categoryIds[left]).crossLinks += 1;
        scores.get(categoryIds[right]).crossLinks += 1;
      }
    }
  }

  return { scores, pairs };
}

export function createOverviewLayout(categories, scores, options = {}) {
  const width = options.width || 1200;
  const height = options.height || 820;
  const radius = options.radius || Math.min(width, height) * 0.34;
  const center = { x: width / 2, y: height / 2 };
  const ranked = [...categories].sort((left, right) => {
    const leftScore = scores.get(left.id) || {};
    const rightScore = scores.get(right.id) || {};
    return (
      (rightScore.crossLinks || 0) - (leftScore.crossLinks || 0) ||
      (rightScore.concepts || 0) - (leftScore.concepts || 0) ||
      (left.order || 0) - (right.order || 0)
    );
  });
  const hub = ranked[0];
  const orbit = categories.filter((category) => category.id !== hub.id);
  const positions = new Map([[hub.id, center]]);

  orbit.forEach((category, index) => {
    const angle = -Math.PI / 2 + (Math.PI * 2 * index) / orbit.length;
    positions.set(category.id, {
      x: center.x + Math.cos(angle) * radius,
      y: center.y + Math.sin(angle) * radius,
    });
  });

  return { hub, positions, width, height };
}

export function positionsOnRing(nodes, center, radius, startAngle = -Math.PI / 2) {
  const positions = new Map();
  const count = Math.max(nodes.length, 1);
  nodes.forEach((node, index) => {
    const angle = startAngle + (Math.PI * 2 * index) / count;
    positions.set(node.id, {
      x: center.x + Math.cos(angle) * radius,
      y: center.y + Math.sin(angle) * radius,
    });
  });
  return positions;
}

export function truncateLabel(value, maximum = 18) {
  const text = String(value || "");
  return text.length > maximum ? `${text.slice(0, maximum - 1)}…` : text;
}
