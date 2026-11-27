// 纯函数工具：node/浏览器双用（UMD 风格导出），零依赖。
// 单测可 require，前端 <script> 引入后挂 window。
(function (root, factory) {
  if (typeof module === "object" && module.exports) {
    module.exports = factory();
  } else {
    root.AP_UTIL = factory();
  }
})(typeof self !== "undefined" ? self : this, function () {
  // XSS 转义：innerHTML 拼接用户数据（path/item/kind/note）前必须过这个
  function escHtml(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }
  // 四维均分（标注 total 自动计算）
  function annTotal(c, l, cr, st) {
    var n = (Number(c) || 0) + (Number(l) || 0) + (Number(cr) || 0) + (Number(st) || 0);
    return Math.round((n / 4) * 100) / 100;
  }
  // 按 total 降序排序（比对结果）；无分排 -1
  function sortByTotalDesc(items) {
    return items.slice().sort(function (a, b) {
      return (b && b.total != null ? b.total : -1) - (a && a.total != null ? a.total : -1);
    });
  }
  // 百分比（标注进度）
  function pct(part, total) {
    if (!total || total <= 0) return 0;
    return Math.min(100, Math.round(part / total * 100));
  }
  return { escHtml: escHtml, annTotal: annTotal, sortByTotalDesc: sortByTotalDesc, pct: pct };
});
