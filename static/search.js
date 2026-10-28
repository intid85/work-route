(function () {
  var box = document.querySelector("[data-search]");
  if (!box) return;
  var mode = box.dataset.mode, q = box.querySelector("input"), body = box.querySelector("tbody"),
      status = box.querySelector("[data-status]"), names = {}, states = {}, rows = [], LIMIT = 50;

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
      "<tr><td colspan=\"" + cols + "\">No matching company. Try a shorter part of the name, without LLC, INC or LTD.</td></tr>";
    status.textContent = term
      ? n(hits.length) + (hits.length === 1 ? " company matches" : " companies match") + (hits.length > LIMIT ? ". Showing the first " + LIMIT + "." : ".")
      : (mode === "uk" ? "Showing the first " + LIMIT + " of " + n(rows.length) + " licensed sponsors, A to Z."
                       : "Showing the largest employers first, out of " + n(rows.length) + ".");
  }

  fetch(box.dataset.src).then(function (r) { return r.json(); }).then(function (j) {
    names = j.names || {}; states = j.states || {}; rows = j.rows || []; render();
  }).catch(function () {
    status.textContent = "The employer list didn't load. Reload the page to try again.";
  });
  q.addEventListener("input", render);
})();
