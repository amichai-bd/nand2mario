/* Block selection for the RTL explorer. Paging, source links and fullscreen
   stay in tools/wiki/assets/presentation.js; this only opens the panel for the
   block a reader picked. Without it every panel is already open, so the page
   still reads. */
"use strict";
(() => {
  const deck = document.querySelector('.deck');
  if (!deck) return;
  const blocks = [...deck.querySelectorAll('a[data-module]')];
  const panels = [...deck.querySelectorAll('details.module')];
  if (!blocks.length || !panels.length) return;
  panels.forEach(panel => { panel.open = false; });

  function reveal(name) {
    const panel = name.startsWith('m-') ? document.getElementById(name) : null;
    blocks.forEach(block => block.classList.toggle('is-selected',
      panel !== null && block.dataset.module === name.slice(2)));
    if (!panel) return;
    panels.forEach(other => { other.open = other === panel; });
    const summary = panel.querySelector('summary');
    if (summary) summary.focus({preventScroll: true});
    panel.scrollIntoView({block: 'nearest'});
  }

  // Capture phase: the wiki embed bridge also listens for clicks and would turn
  // an in-page selection into a page navigation. Claiming the event first keeps
  // selection inside this page whether it is embedded or standalone.
  document.addEventListener('click', event => {
    if (event.defaultPrevented || event.button !== 0) return;
    if (event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
    const anchor = event.target.closest('a[href^="#m-"]');
    if (!anchor) return;
    event.preventDefault();
    const name = decodeURIComponent(anchor.getAttribute('href').slice(1));
    if (location.hash.slice(1) === name) reveal(name);
    else location.hash = name;
  }, true);

  // Runs after the shared runtime has selected the slide holding the target.
  window.addEventListener('hashchange', () => {
    let name = '';
    try { name = decodeURIComponent(location.hash.slice(1)); } catch { return; }
    reveal(name);
  });
  window.addEventListener('beforeprint', () => panels.forEach(panel => { panel.open = true; }));
  try { reveal(decodeURIComponent(location.hash.slice(1))); } catch { /* malformed fragment */ }
})();
