/* Проверяем настоящий renderQuiz из app.js, а не копию переходов.
   Минимальная модель кнопок — без npm/DOM; в tools/browser_smoke.py
   те же переходы дополнительно проверяются в настоящем браузере. */
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const quiz = require("../../app/data/quiz.json");
const app = fs.readFileSync(require.resolve("../../static/app.js"), "utf8");
const source = app.slice(app.indexOf("function renderQuiz()"), app.indexOf("async function submitQuiz()"));

function setup() {
  let buttons = [];
  const sent = [];
  const view = {};
  Object.defineProperty(view, "innerHTML", { set(html) {
    buttons = [...html.matchAll(/<button\b([^>]*)>/g)].map(([, attrs]) => ({
      id: /id="([^"]*)"/.exec(attrs)?.[1],
      dataset: { opt: /data-opt="([^"]*)"/.exec(attrs)?.[1] },
      disabled: /\bdisabled\b/.test(attrs),
      addEventListener(event, fn) { this[event] = fn; },
    }));
  }});
  const state = { quiz, q: { step: 0, answers: {} }, quizResult: null };
  const context = vm.createContext({
    state, view,
    $: selector => buttons.find(b => "#" + b.id === selector),
    $$: () => buttons.filter(b => b.dataset.opt),
    esc: String, t: s => s, localize() {}, toast() {},
    submitQuiz: () => sent.push(JSON.parse(JSON.stringify(state.q.answers))),
  });
  vm.runInContext(source + "\nrenderQuiz();", context);
  function click(id) {
    const button = buttons.find(b => b.id === id || b.dataset.opt === id);
    assert.ok(button, `нет кнопки ${id}`);
    assert.equal(button.disabled, false, `${id} выключена`);
    button.click();
  }
  return { state, sent, click, buttons: () => buttons };
}

test("после первого вопроса — второй, а не результат с дефолтами сервера", () => {
  const ui = setup();
  ui.click("beach"); ui.click("q-next");
  assert.equal(ui.state.q.step, 1);
  assert.equal(ui.sent.length, 0);
});

test("все 7 вопросов проходят до единственной отправки полного набора", () => {
  const ui = setup();
  ui.click("beach"); ui.click("q-next");
  for (const answer of ["winter", "relax", "premium", "family", "6-10", "transit"]) ui.click(answer);
  assert.equal(ui.state.q.step, 6, "не выходим за границу вопросов");
  assert.equal(ui.sent.length, 0, "ждём подтверждения на последнем вопросе");
  ui.click("q-next");
  assert.deepEqual(ui.sent, [{ purpose: ["beach"], season: "winter", tempo: "relax",
    budget: "premium", party: "family", duration: "6-10", transport: "transit" }]);
});

test("Назад сохраняет ответы, повторный выбор заменяет ответ", () => {
  const ui = setup();
  ui.click("beach"); ui.click("q-next"); ui.click("summer");
  ui.click("q-back");
  assert.equal(ui.state.q.step, 1);
  assert.equal(ui.state.q.answers.season, "summer");
  ui.click("winter");
  assert.equal(ui.state.q.answers.season, "winter");
  assert.equal(ui.sent.length, 0);
});

test("пустой первый ответ нельзя отправить; максимум 3 интереса", () => {
  const ui = setup();
  assert.equal(ui.buttons().find(b => b.id === "q-next").disabled, true);
  for (const answer of ["beach", "nature", "history", "wine"]) ui.click(answer);
  assert.deepEqual(Array.from(ui.state.q.answers.purpose), ["beach", "nature", "history"]);
  for (const answer of ["beach", "nature", "history"]) ui.click(answer);
  assert.equal(ui.buttons().find(b => b.id === "q-next").disabled, true);
});
