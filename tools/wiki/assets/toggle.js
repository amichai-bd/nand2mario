document.addEventListener("DOMContentLoaded", () => {
  const buttons = document.querySelectorAll("[data-view]");
  if (!buttons.length) return;
  const select = (name) => {
    buttons.forEach((button) => {
      const active = button.dataset.view === name;
      button.setAttribute("aria-pressed", String(active));
      document.getElementById(button.getAttribute("aria-controls")).hidden = !active;
    });
    const edit = document.querySelector(".navbar a[href*='/edit/main/']");
    const sourceEdit = document.querySelector(`#${name}-view a[href*='/edit/main/']`);
    if (edit && sourceEdit) edit.href = sourceEdit.href;
  };
  buttons.forEach((button) => button.addEventListener("click", () => select(button.dataset.view)));
  // Show the matching document when following a heading or search result.
  const showAnchor = () => {
    const target = document.getElementById(decodeURIComponent(location.hash.slice(1)));
    if (target?.closest("#agents-view")) select("agents");
    else if (target?.closest("#readme-view")) select("readme");
  };
  select("readme");
  showAnchor();
  window.addEventListener("hashchange", showAnchor);
});
