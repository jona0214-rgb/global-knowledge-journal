import assert from "node:assert/strict";
import fs from "node:fs/promises";
import vm from "node:vm";


class FakeClassList {
  constructor() {
    this.values = new Set();
  }

  remove(...names) {
    names.forEach((name) => this.values.delete(name));
  }
}


class FakeElement {
  constructor(id) {
    this.id = id;
    this.value = "";
    this.disabled = false;
    this.innerHTML = "";
    this.textContent = "";
    this.listeners = new Map();
    this.classList = new FakeClassList();
  }

  addEventListener(type, listener) {
    this.listeners.set(type, listener);
  }

  trigger(type) {
    const listener = this.listeners.get(type);
    if (listener) {
      listener({ target: this });
    }
  }
}


const elementIds = [
  "latest-report",
  "report-list",
  "report-count",
  "latest-date",
  "site-status",
  "archive-category",
  "archive-month",
  "archive-sort",
  "archive-reset",
  "archive-result-count",
];
const elements = new Map(elementIds.map((id) => [id, new FakeElement(id)]));
elements.get("archive-sort").value = "newest";

const reports = JSON.parse(
  await fs.readFile(new URL("../public/reports.json", import.meta.url), "utf8"),
);
const appSource = await fs.readFile(
  new URL("../app.js", import.meta.url),
  "utf8",
);

const location = {
  pathname: "/global-knowledge-journal/",
  search: "",
  hash: "",
};
const context = vm.createContext({
  console,
  URLSearchParams,
  setTimeout,
  clearTimeout,
  document: {
    getElementById(id) {
      return elements.get(id);
    },
  },
  window: {
    location,
    history: {
      replaceState(_state, _title, url) {
        const parsed = new URL(url, "https://example.test");
        location.pathname = parsed.pathname;
        location.search = parsed.search;
        location.hash = parsed.hash;
      },
    },
  },
  fetch: async () => ({
    ok: true,
    json: async () => reports,
  }),
});

vm.runInContext(appSource, context, { filename: "app.js" });
await new Promise((resolve) => setTimeout(resolve, 0));

const categorySelect = elements.get("archive-category");
const monthSelect = elements.get("archive-month");
const sortSelect = elements.get("archive-sort");
const resetButton = elements.get("archive-reset");
const resultCount = elements.get("archive-result-count");
const reportList = elements.get("report-list");
const latestReport = elements.get("latest-report");

assert.match(categorySelect.innerHTML, /역사·문화 \(1\)/);
assert.match(categorySelect.innerHTML, /기술·공학 \(1\)/);
assert.doesNotMatch(categorySelect.innerHTML, /생활기술·일상문화/);
assert.match(monthSelect.innerHTML, /2026년 8월 \(3\)/);
assert.match(latestReport.innerHTML, /<dt>대분류<\/dt>/);
assert.match(latestReport.innerHTML, /<dt>분야<\/dt>/);

categorySelect.value = "역사·문화";
categorySelect.trigger("change");
assert.match(resultCount.textContent, /역사·문화 · 1건/);
assert.match(reportList.innerHTML, /시간표의 탄생/);
assert.doesNotMatch(reportList.innerHTML, /무지의 베일/);
assert.match(location.search, /category=/);

categorySelect.value = "";
sortSelect.value = "oldest";
sortSelect.trigger("change");
assert.ok(
  reportList.innerHTML.indexOf("도시의 하수도") <
    reportList.innerHTML.indexOf("시간표의 탄생"),
);
assert.match(location.search, /sort=oldest/);

resetButton.trigger("click");
assert.equal(categorySelect.value, "");
assert.equal(monthSelect.value, "");
assert.equal(sortSelect.value, "newest");
assert.equal(resultCount.textContent, "전체 공개 리포트 3건");
assert.equal(location.search, "");

console.log("homepage_filter_test=ok");
