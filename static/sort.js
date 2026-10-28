(function () {
  var table = document.getElementById("compare");
  if (!table) return;
  var heads = table.querySelectorAll("thead th");
  heads.forEach(function (th, i) {
    th.tabIndex = 0;
    function sort() {
      var desc = th.getAttribute("aria-sort") !== "descending";
      heads.forEach(function (h) { h.removeAttribute("aria-sort"); });
      th.setAttribute("aria-sort", desc ? "descending" : "ascending");
      var body = table.tBodies[0];
      var rows = Array.prototype.slice.call(body.rows);
      rows.sort(function (a, b) {
        var x = a.cells[i], y = b.cells[i];
        if (th.dataset.sort === "num") {
          var d = (+x.dataset.v || 0) - (+y.dataset.v || 0);
          return desc ? -d : d;
        }
        var c = x.textContent.trim().localeCompare(y.textContent.trim(), "ko");
        return desc ? -c : c;
      });
      rows.forEach(function (r) { body.appendChild(r); });
    }
    th.addEventListener("click", sort);
    th.addEventListener("keydown", function (e) { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); sort(); } });
  });
})();
