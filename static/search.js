(function () {
  var box = document.querySelector("[data-search]");
  if (!box) return;
  var mode = box.dataset.mode, q = box.querySelector("input"), body = box.querySelector("tbody"),
      status = box.querySelector("[data-status]"), names = {}, states = {}, rows = [], LIMIT = 50,
      ko = document.documentElement.lang === "ko";

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"]/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", "\"": "&quot;" }[c];
    });
  }
  function n(v) { return (v || 0).toLocaleString("en-US"); }
  function list(codes) { return (codes || []).map(function (c) { return esc(names[c] || c); }).join(", "); }

  var renderRow = {
    us: function (r) {
      var rate = r.d ? Math.round(r.c / r.d * 100) : 0;
      return "<th scope=\"row\">" + esc(r.n) + "</th><td>" + n(r.d) + "</td><td>" + n(r.c) +
        " <span class=\"rate\">(" + rate + "%)</span></td><td class=\"wrap\">" + list(r.s) + "</td><td>" + esc(states[r.st] || r.st) + "</td>";
    },
    ca: function (r) {
      return "<th scope=\"row\">" + esc(r.n) + "</th><td>" + n(r.p) + "</td><td class=\"wrap\">" + list(r.o) + "</td><td>" + esc(r.pv) + "</td>";
    },
    uk: function (r) {
      return "<th scope=\"row\">" + esc(r.n) + "</th><td>" + esc(r.t) + "</td><td class=\"wrap\">" + esc((r.r || []).join(", ")) + "</td>";
    }
  }[mode];

  function render() {
    var term = q.value.trim().toUpperCase();
    var hits = term ? rows.filter(function (r) { return r.n.indexOf(term) !== -1; }) : rows;
    var cols = box.querySelectorAll("thead th").length;
    body.innerHTML = hits.slice(0, LIMIT).map(function (r) { return "<tr>" + renderRow(r) + "</tr>"; }).join("") ||
      "<tr><td colspan=\"" + cols + "\">" + (ko ? "일치하는 회사가 없습니다. LLC, INC, LTD를 빼고 더 짧게 검색해 보세요."
        : "No matching company. Try a shorter part of the name, without LLC, INC or LTD.") + "</td></tr>";
    if (ko) {
      status.textContent = term
        ? n(hits.length) + "곳이 일치합니다" + (hits.length > LIMIT ? ". 상위 " + LIMIT + "곳만 보여드립니다." : ".")
        : (mode === "uk" ? "전체 " + n(rows.length) + "곳 중 알파벳순으로 " + LIMIT + "곳을 보여드립니다."
                         : "규모가 큰 회사부터 보여드립니다. 전체 " + n(rows.length) + "곳.");
      return;
    }
    status.textContent = term
      ? n(hits.length) + (hits.length === 1 ? " company matches" : " companies match") + (hits.length > LIMIT ? ". Showing the first " + LIMIT + "." : ".")
      : (mode === "uk" ? "Showing the first " + LIMIT + " of " + n(rows.length) + " licensed sponsors, A to Z."
                       : "Showing the largest employers first, out of " + n(rows.length) + ".");
  }

  fetch(box.dataset.src).then(function (r) { return r.json(); }).then(function (j) {
    names = j.names || {}; states = j.states || {}; rows = j.rows || []; render();
  }).catch(function () {
    status.textContent = ko ? "회사 목록을 불러오지 못했습니다. 페이지를 새로고침해 주세요."
                            : "The employer list didn't load. Reload the page to try again.";
  });
  q.addEventListener("input", render);
})();
