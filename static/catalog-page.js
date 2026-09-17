/* Крым.Гид — порционный показ каталога.
   Чистые функции без DOM: подключаются в браузере через <script>
   (как window.CatalogPage) и тестируются в Node через node:test.

   Зачем: каталог вырос до 60 карточек, каждая — с картинкой. Рисовать
   их одним куском на слабом телефоне заметно дорого, поэтому показываем
   первую порцию, а остальное догружаем по мере прокрутки. Состояние
   порции намеренно НЕ попадает в ссылку на подборку: получатель должен
   увидеть тот же набор фильтров, а не «докрученную» ленту. */
(function (root, factory) {
  const api = factory();
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.CatalogPage = api;
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";

  // Первая порция закрывает примерно два экрана на десктопе и заметно
  // сокращает работу при первом рендере; шаг догрузки — столько же.
  const PAGE = 12;

  function toCount(value) {
    const n = Math.floor(Number(value));
    return Number.isFinite(n) && n > 0 ? n : 0;
  }

  /** Сколько карточек показать при первом рендере подборки. */
  function firstPage(total, page) {
    return Math.min(toCount(total), toCount(page) || PAGE);
  }

  /** Следующий размер видимой части (не больше общего числа). */
  function growShown(shown, total, page) {
    const cap = toCount(total);
    return Math.min(cap, toCount(shown) + (toCount(page) || PAGE));
  }

  /** Видимая часть подборки. Массив не мутируется. */
  function visible(items, shown) {
    const list = Array.isArray(items) ? items : [];
    return list.slice(0, Math.min(list.length, toCount(shown)));
  }

  /** Сколько карточек ещё скрыто. */
  function remaining(shown, total) {
    return Math.max(0, toCount(total) - toCount(shown));
  }

  /** Нужна ли кнопка/наблюдатель догрузки. */
  function hasMore(shown, total) {
    return remaining(shown, total) > 0;
  }

  /** Подпись счётчика: сколько показано из скольких найденных. */
  function statusLabel(shown, total) {
    const cap = toCount(total);
    const seen = Math.min(cap, toCount(shown));
    if (!cap) return "Ничего не найдено";
    if (seen >= cap) return `Найдено: ${cap}`;
    return `Показано ${seen} из ${cap}`;
  }

  return {
    PAGE, firstPage, growShown, visible, remaining, hasMore, statusLabel,
  };
});
