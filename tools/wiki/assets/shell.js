/* Navigation uses the source path itself. The manifest contains only tracked text. */
"use strict";
const $ = (id) => document.getElementById(id);
const categories = ["Home", "Src", "Agents/Skills", "Tools", "Cfg", "Presentations"];
let files = {}, current = "README.md", activeCategory = "Home", activeFrame = null;

function link(path, fragment = "") {
  return `?page=${encodeURIComponent(path)}${fragment ? `#${encodeURIComponent(fragment)}` : ""}`;
}
function navigate(path, fragment = "") {
  history.pushState(null, "", link(path, fragment));
  display();
}
function tree() {
  const filter = $("filter").value.toLowerCase();
  const nodes = {};
  Object.entries(files).forEach(([path, file]) => {
    if (!file.nav || file.category !== activeCategory || !path.toLowerCase().includes(filter)) return;
    let node = nodes;
    const relative = path.replace(/^(?:\.agents\/skills|src|tools|cfg)\//, "");
    const parts = relative.split("/");
    parts.slice(0, -1).forEach((part) => { node = node[part] ||= {}; });
    node[parts.at(-1)] = path;
  });
  const fill = (nodes, parent) => {
    Object.entries(nodes).sort(([a], [b]) => a.localeCompare(b)).forEach(([name, value]) => {
      if (typeof value === "string") {
        const item = document.createElement("a");
        item.textContent = name;
        item.href = link(value);
        if (value === current) item.setAttribute("aria-current", "page");
        parent.append(item);
      } else {
        const folder = document.createElement("details"), title = document.createElement("summary"), children = document.createElement("div");
        title.textContent = name;
        folder.open = true;
        fill(value, children);
        folder.append(title, children);
        parent.append(folder);
      }
    });
  };
  $("tree").replaceChildren();
  fill(nodes, $("tree"));
  if (!Object.keys(nodes).length) $("tree").textContent = "No files yet.";
  [...$("tabs").children].forEach((button) => button.setAttribute("aria-current", button.textContent === activeCategory ? "page" : "false"));
}

function source(path, line = 1) {
  if (!Object.hasOwn(files, path) || !Number.isInteger(line) || line < 1) return;
  const text = files[path].text.split(/\r?\n/);
  if (line > text.length) return;
  $("source-title").textContent = path;
  $("source-lines").replaceChildren(...text.map((value, index) => {
    const row = document.createElement("span"), number = document.createElement("span");
    row.className = "code-line" + (index + 1 === line ? " selected" : "");
    number.className = "line-number";
    number.textContent = index + 1;
    row.append(number, document.createTextNode(value));
    return row;
  }));
  if (!$("source-dialog").open) $("source-dialog").showModal();
  $("source-lines").querySelector(".selected").scrollIntoView({block: "center"});
}

function display() {
  const url = new URL(location.href);
  const emptyCategory = url.searchParams.get("category");
  if (categories.includes(emptyCategory)) { showEmpty(emptyCategory); return; }
  current = url.searchParams.get("page") || "README.md";
  activeFrame = null;
  const entry = files[current];
  $("document").replaceChildren();
  $("document").classList.remove("embedded");
  if (!entry) {
    $("home-toggle").hidden = true;
    $("path").textContent = current;
    $("source-path").textContent = "";
    $("document").textContent = `Document not found: ${current}`;
    $("document").classList.add("error");
    $("source").disabled = true;
    return;
  }
  $("document").classList.remove("error");
  $("source").disabled = false;
  activeCategory = entry.category;
  $("path").textContent = current;
  $("source-path").textContent = current;
  document.title = `${current.split("/").at(-1)} — nand2mario`;
  $("home-toggle").hidden = !["README.md", "AGENTS.md"].includes(current);
  document.querySelectorAll("[data-home]").forEach((button) => button.setAttribute("aria-pressed", String(button.dataset.home === current)));
  if (entry.kind === "md") $("document").innerHTML = entry.html;
  else if (entry.kind === "html") {
    const frame = document.createElement("iframe"), standalone = document.createElement("a");
    frame.src = `files/${current.split("/").map(encodeURIComponent).join("/")}${location.hash}`;
    frame.title = current;
    frame.setAttribute("sandbox", "allow-scripts allow-popups allow-popups-to-escape-sandbox");
    standalone.href = frame.src;
    standalone.target = "_blank";
    standalone.rel = "noopener";
    standalone.textContent = "Open standalone ↗";
    standalone.className = "standalone";
    $("document").classList.add("embedded");
    $("document").append(standalone, frame);
    activeFrame = frame;
  } else {
    const pre = document.createElement("pre"), code = document.createElement("code");
    code.textContent = entry.text;
    pre.append(code);
    $("document").append(pre);
  }
  tree();
  const fragment = decodeURIComponent(location.hash.slice(1));
  if (/^L\d+/.test(fragment)) source(current, Number(fragment.match(/^L(\d+)/)[1]));
  else if (fragment) $("document").querySelector(`#${CSS.escape(fragment)}`)?.scrollIntoView();
}

async function fullscreen() {
  try {
    if (document.fullscreenElement) await document.exitFullscreen();
    else await $("stage").requestFullscreen();
    return true;
  } catch { $("fullscreen").textContent = "Fullscreen unavailable"; return false; }
}

document.addEventListener("click", (event) => {
  const anchor = event.target.closest("a");
  if (!anchor || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
  if (anchor.dataset.source) {
    event.preventDefault();
    source(anchor.dataset.source, Number(anchor.dataset.line || 1));
    return;
  }
  const target = new URL(anchor.href, location.href);
  if (target.origin === location.origin && target.pathname === location.pathname && target.searchParams.has("page")) {
    event.preventDefault();
    const path = target.searchParams.get("page");
    if (path.startsWith("src/") && files[path]?.kind === "source") {
      source(path, Number(target.hash.match(/^#L(\d+)/)?.[1] || 1));
    } else navigate(path, decodeURIComponent(target.hash.slice(1)));
  }
});
window.addEventListener("message", (event) => {
  if (!activeFrame || event.source !== activeFrame.contentWindow || !event.data || typeof event.data !== "object") return;
  if (event.data.type === "n2m:source") source(event.data.path, event.data.line ?? 1);
  if (event.data.type === "n2m:navigate" && Object.hasOwn(files, event.data.path) && typeof event.data.fragment === "string") {
    if (files[event.data.path].kind === "source") source(event.data.path, Number(event.data.fragment.match(/^L(\d+)/)?.[1] || 1));
    else navigate(event.data.path, event.data.fragment);
  }
  if (event.data.type === "n2m:fullscreen") fullscreen().then((ok) => {
    event.source.postMessage({type: "n2m:fullscreen-result", ok}, "*");
  });
});
window.addEventListener("popstate", display);
$("filter").addEventListener("input", tree);
$("source").addEventListener("click", () => source(current));
$("close-source").addEventListener("click", () => $("source-dialog").close());
$("fullscreen").addEventListener("click", fullscreen);
document.addEventListener("fullscreenchange", () => { $("fullscreen").textContent = document.fullscreenElement ? "Exit fullscreen" : "Fullscreen"; });
document.querySelectorAll("[data-home]").forEach((button) => button.addEventListener("click", () => navigate(button.dataset.home)));
function showEmpty(name) {
  activeCategory = name;
  activeFrame = null;
  current = "";
  tree();
  $("home-toggle").hidden = true;
  $("path").textContent = name;
  $("source-path").textContent = "";
  $("source").disabled = true;
  $("document").classList.remove("embedded", "error");
  $("document").textContent = "No documents in this category yet.";
}
categories.forEach((name) => {
  const button = document.createElement("button");
  button.textContent = name;
  button.addEventListener("click", () => {
    $("filter").value = "";
    const entry = Object.entries(files).find(([path, file]) => file.nav && file.category === name && (name !== "Home" || path === "README.md"));
    if (entry) navigate(entry[0]);
    else {
      showEmpty(name);
      history.pushState(null, "", `?category=${encodeURIComponent(name)}`);
    }
  });
  $("tabs").append(button);
});
fetch("manifest.json").then((response) => {
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  return response.json();
}).then((manifest) => { files = manifest; display(); }).catch((error) => {
  $("document").textContent = `Could not load the workspace: ${error.message}. Serve the generated site over HTTP.`;
});
