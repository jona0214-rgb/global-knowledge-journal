export function buildGraphIndex(graph) {
  const nodes = new Map((graph.nodes || []).map((node) => [node.id, node]));
  const hierarchyChildren = new Map();
  const hierarchyParent = new Map();
  const conceptReports = new Map();
  const reportConcepts = new Map();
  const conceptReportWeights = new Map();

  for (const edge of graph.edges || []) {
    if (edge.kind === "hierarchy") {
      const children = hierarchyChildren.get(edge.source) || [];
      children.push(edge.target);
      hierarchyChildren.set(edge.source, children);
      hierarchyParent.set(edge.target, edge.source);
      continue;
    }

    if (edge.kind === "concept") {
      const reports = conceptReports.get(edge.target) || [];
      reports.push(edge.source);
      conceptReports.set(edge.target, reports);

      const concepts = reportConcepts.get(edge.source) || [];
      concepts.push(edge.target);
      reportConcepts.set(edge.source, concepts);

      const weights = conceptReportWeights.get(edge.target) || new Map();
      weights.set(edge.source, Number(edge.score) || 1);
      conceptReportWeights.set(edge.target, weights);
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
    hierarchyParent,
    conceptReports,
    reportConcepts,
    conceptReportWeights,
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

const TWO_PI = Math.PI * 2;

export function normalizeAngle(angle) {
  return ((angle % TWO_PI) + TWO_PI) % TWO_PI;
}

export function circularAngleDistance(left, right) {
  const distance = Math.abs(normalizeAngle(left) - normalizeAngle(right));
  return Math.min(distance, TWO_PI - distance);
}

export function weightedCircularMean(samples, fallbackAngle = -Math.PI / 2) {
  const validSamples = samples.filter(
    (sample) => Number.isFinite(sample.angle) && Number(sample.weight) > 0,
  );
  if (!validSamples.length) return normalizeAngle(fallbackAngle);

  const vector = validSamples.reduce(
    (total, sample) => ({
      x: total.x + Math.cos(sample.angle) * Number(sample.weight),
      y: total.y + Math.sin(sample.angle) * Number(sample.weight),
    }),
    { x: 0, y: 0 },
  );
  if (Math.hypot(vector.x, vector.y) < 1e-8) {
    return normalizeAngle(fallbackAngle);
  }
  return normalizeAngle(Math.atan2(vector.y, vector.x));
}

function angleFromPosition(position, center) {
  return normalizeAngle(Math.atan2(position.y - center.y, position.x - center.x));
}

function spreadCircularAngles(items, minimumSeparation) {
  if (items.length < 2) {
    return new Map(items.map((item) => [item.id, normalizeAngle(item.angle)]));
  }

  const ordered = [...items].sort(
    (left, right) => normalizeAngle(left.angle) - normalizeAngle(right.angle) ||
      String(left.id).localeCompare(String(right.id)),
  );
  let largestGapIndex = 0;
  let largestGap = -1;
  ordered.forEach((item, index) => {
    const next = index === ordered.length - 1
      ? normalizeAngle(ordered[0].angle) + TWO_PI
      : normalizeAngle(ordered[index + 1].angle);
    const gap = next - normalizeAngle(item.angle);
    if (gap > largestGap) {
      largestGap = gap;
      largestGapIndex = index;
    }
  });

  const startIndex = (largestGapIndex + 1) % ordered.length;
  const unwrapped = [];
  for (let offset = 0; offset < ordered.length; offset += 1) {
    const item = ordered[(startIndex + offset) % ordered.length];
    let angle = normalizeAngle(item.angle);
    if (unwrapped.length && angle < unwrapped.at(-1).target) angle += TWO_PI;
    unwrapped.push({ ...item, target: angle });
  }

  const availableSpan = TWO_PI - minimumSeparation;
  const separation = Math.min(
    minimumSeparation,
    availableSpan / Math.max(unwrapped.length - 1, 1),
  );
  const placed = [];
  for (const item of unwrapped) {
    const previous = placed.at(-1);
    placed.push({
      ...item,
      placed: previous
        ? Math.max(item.target, previous.placed + separation)
        : item.target,
    });
  }
  const correction = placed.reduce(
    (sum, item) => sum + item.target - item.placed,
    0,
  ) / placed.length;

  return new Map(
    placed.map((item) => [item.id, normalizeAngle(item.placed + correction)]),
  );
}

function nodesOfType(descendants, type, index) {
  return [...descendants]
    .map((id) => index.nodes.get(id))
    .filter((node) => node?.type === type)
    .sort((left, right) => String(left.label).localeCompare(String(right.label), "ko"));
}

export function createCategoryDetailLayout(category, index, relevantConcepts, options = {}) {
  const center = options.center || { x: 600, y: 500 };
  const radii = {
    middle: 105,
    sub: 165,
    detail: 225,
    report: 290,
    concept: 375,
    category: 465,
    ...(options.radii || {}),
  };
  const startAngle = options.startAngle ?? -Math.PI / 2;
  const descendants = collectDescendants(category.id, index);
  const layers = {
    middle: nodesOfType(descendants, "middle", index),
    sub: nodesOfType(descendants, "sub", index),
    detail: nodesOfType(descendants, "detail", index),
    report: nodesOfType(descendants, "report", index),
  };
  const visibleHierarchyIds = new Set([category.id, ...descendants]);
  const positions = new Map([[category.id, center]]);
  const angles = new Map();
  const reportCountCache = new Map();

  function subtreeReportCount(nodeId) {
    if (reportCountCache.has(nodeId)) return reportCountCache.get(nodeId);
    const node = index.nodes.get(nodeId);
    const count = node?.type === "report"
      ? 1
      : (index.hierarchyChildren.get(nodeId) || [])
        .filter((id) => visibleHierarchyIds.has(id))
        .reduce((sum, id) => sum + subtreeReportCount(id), 0);
    reportCountCache.set(nodeId, Math.max(count, 1));
    return Math.max(count, 1);
  }

  function placeChildren(parentId, sectorStart, sectorEnd) {
    const children = (index.hierarchyChildren.get(parentId) || [])
      .filter((id) => visibleHierarchyIds.has(id))
      .map((id) => index.nodes.get(id))
      .filter(Boolean)
      .sort((left, right) => String(left.label).localeCompare(String(right.label), "ko"));
    if (!children.length) return;

    const weights = children.map((child) => Math.sqrt(subtreeReportCount(child.id)));
    const totalWeight = weights.reduce((sum, weight) => sum + weight, 0);
    let cursor = sectorStart;
    children.forEach((child, indexValue) => {
      const span = (sectorEnd - sectorStart) * (weights[indexValue] / totalWeight);
      const childStart = cursor;
      const childEnd = cursor + span;
      const angle = (childStart + childEnd) / 2;
      angles.set(child.id, normalizeAngle(angle));
      const radius = radii[child.type];
      if (radius) {
        positions.set(child.id, {
          x: center.x + Math.cos(angle) * radius,
          y: center.y + Math.sin(angle) * radius,
        });
      }
      const inset = Math.min(span * 0.08, 0.045);
      placeChildren(child.id, childStart + inset, childEnd - inset);
      cursor = childEnd;
    });
  }

  placeChildren(category.id, startAngle - Math.PI, startAngle + Math.PI);

  const externalCategories = index.categories.filter((item) => item.id !== category.id);
  positionsOnRing(externalCategories, center, radii.category, startAngle)
    .forEach((position, id) => positions.set(id, position));

  const conceptTargets = relevantConcepts.map((concept, conceptIndex) => {
    const samples = [];
    const reportWeights = index.conceptReportWeights.get(concept.id) || new Map();
    for (const reportId of index.conceptReports.get(concept.id) || []) {
      const reportPosition = positions.get(reportId);
      const categoryId = index.reportCategory.get(reportId);
      const weight = reportWeights.get(reportId) || 1;
      if (categoryId === category.id && reportPosition) {
        samples.push({ angle: angleFromPosition(reportPosition, center), weight: weight * 1.25 });
      } else if (categoryId && positions.has(categoryId)) {
        samples.push({ angle: angleFromPosition(positions.get(categoryId), center), weight });
      }
    }
    const fallback = startAngle + (TWO_PI * conceptIndex) / Math.max(relevantConcepts.length, 1);
    return {
      id: concept.id,
      angle: weightedCircularMean(samples, fallback),
    };
  });
  const conceptAngles = spreadCircularAngles(
    conceptTargets,
    options.minimumConceptSeparation ?? 0.24,
  );
  relevantConcepts.forEach((concept) => {
    const angle = conceptAngles.get(concept.id);
    positions.set(concept.id, {
      x: center.x + Math.cos(angle) * radii.concept,
      y: center.y + Math.sin(angle) * radii.concept,
    });
  });

  return {
    positions,
    angles,
    layers,
    externalCategories,
    conceptTargets: new Map(conceptTargets.map((item) => [item.id, item.angle])),
    conceptAngles,
  };
}

export function truncateLabel(value, maximum = 18) {
  const text = String(value || "");
  return text.length > maximum ? `${text.slice(0, maximum - 1)}…` : text;
}
