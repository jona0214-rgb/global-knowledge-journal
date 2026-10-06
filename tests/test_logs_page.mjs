import assert from "node:assert/strict";
import fs from "node:fs/promises";
import vm from "node:vm";


class FakeClassList {
  remove() {}
}


class FakeElement {
  constructor() {
    this.innerHTML = "";
    this.classList = new FakeClassList();
  }
}


const historyElement = new FakeElement();
const history = [
  {
    date: "2026-10-04",
    title: "자동화 공개 테스트",
    scheduled_for_kst: "2026-10-04T00:00:00+09:00",
    workflow_started_at: "2026-10-03T15:04:00Z",
    catalog_updated_at: "2026-10-03T15:08:00Z",
    publication_target_kst: "2026-10-04T07:00:00+09:00",
    publication_pushed_at: "2026-10-03T22:00:20Z",
    scheduler_delay_seconds: 240,
    setup_duration_seconds: 60,
    generation_duration_seconds: 180,
    run_url: "https://github.com/example/actions/runs/1",
    publication_run_url: "https://github.com/example/actions/runs/2",
  },
];
const source = await fs.readFile(
  new URL("../logs.js", import.meta.url),
  "utf8",
);

const context = vm.createContext({
  console,
  Intl,
  Date,
  document: {
    getElementById(id) {
      assert.equal(id, "generation-history");
      return historyElement;
    },
  },
  fetch: async () => ({
    ok: true,
    json: async () => history,
  }),
});

vm.runInContext(source, context, { filename: "logs.js" });
await new Promise((resolve) => setTimeout(resolve, 0));

assert.match(historyElement.innerHTML, /생성 예약/);
assert.match(historyElement.innerHTML, /스테이징 저장/);
assert.match(historyElement.innerHTML, /공개 목표/);
assert.match(historyElement.innerHTML, /main 승격/);
assert.match(historyElement.innerHTML, /생성 Actions 로그/);
assert.match(historyElement.innerHTML, /공개 Actions 로그/);
assert.match(historyElement.innerHTML, /공개 승격 완료/);

console.log("logs_page_test=ok");
