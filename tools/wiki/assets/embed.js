/* Generated HTML copies load this bridge; standalone links keep their original href. */
"use strict";
document.addEventListener("click", (event) => {
  if (window.parent === window || event.defaultPrevented || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
  const anchor = event.target.closest("a");
  if (!anchor) return;
  if (anchor.dataset.source) {
    event.preventDefault();
    window.parent.postMessage({type: "n2m:source", path: anchor.dataset.source, line: Number(anchor.dataset.line || 1)}, "*");
  } else if (anchor.dataset.wikiPage) {
    event.preventDefault();
    window.parent.postMessage({type: "n2m:navigate", path: anchor.dataset.wikiPage, fragment: anchor.dataset.wikiFragment || ""}, "*");
  }
});
