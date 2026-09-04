/* Shared deck controls. Content and source links remain useful without JS. */
(() => {
  const deck = document.querySelector('.deck');
  if (!deck) return;
  const slides = [...deck.querySelectorAll('[data-slide]')];
  if (!slides.length) return;
  const controls = document.createElement('nav');
  controls.className = 'deck-controls';
  controls.setAttribute('aria-label', 'Presentation controls');
  controls.innerHTML = '<button data-prev>Previous</button><button data-next>Next</button>' +
    '<span data-progress aria-live="polite"></span><button data-fullscreen>Fullscreen</button>';
  const status = document.createElement('p');
  status.dataset.status = '';
  status.setAttribute('role', 'status');
  deck.append(controls, status);
  const prev = controls.querySelector('[data-prev]');
  const next = controls.querySelector('[data-next]');
  let index = 0;
  function show(value, focus = false) {
    index = Math.max(0, Math.min(slides.length - 1, value));
    slides.forEach((slide, i) => { slide.hidden = i !== index; });
    prev.disabled = index === 0;
    next.disabled = index === slides.length - 1;
    controls.querySelector('[data-progress]').textContent = `${index + 1} / ${slides.length}`;
    if (focus) {
      const heading = slides[index].querySelector('h1, h2, h3');
      if (heading) { heading.tabIndex = -1; heading.focus(); }
    }
  }
  prev.addEventListener('click', () => show(index - 1));
  next.addEventListener('click', () => show(index + 1));
  document.addEventListener('keydown', event => {
    if (event.altKey || event.ctrlKey || event.metaKey || event.target.closest('input, textarea, select, [contenteditable]')) return;
    const target = {ArrowLeft: index - 1, ArrowRight: index + 1, Home: 0, End: slides.length - 1}[event.key];
    if (target !== undefined) { event.preventDefault(); show(target, true); }
  });
  const embedded = window.parent !== window;
  deck.addEventListener('click', event => {
    const link = event.target.closest('a[data-source]');
    if (!link || !embedded || event.defaultPrevented || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey || event.button !== 0) return;
    event.preventDefault();
    window.parent.postMessage({type: 'n2m:source', path: link.dataset.source,
      line: Number(link.dataset.line) || 1}, '*');
  });
  window.addEventListener('message', event => {
    if (event.source === window.parent && event.data?.type === 'n2m:fullscreen-result' && !event.data.ok) {
      status.textContent = 'Use the wiki Fullscreen button to expand this presentation.';
    }
  });
  controls.querySelector('[data-fullscreen]').addEventListener('click', async () => {
    if (embedded) {
      window.parent.postMessage({type: 'n2m:fullscreen'}, '*');
      return;
    }
    try {
      if (document.fullscreenElement) await document.exitFullscreen();
      else if (document.documentElement.requestFullscreen) await document.documentElement.requestFullscreen();
      else status.textContent = 'Fullscreen is unavailable. Open this deck in a browser tab.';
    } catch { status.textContent = 'Fullscreen was declined by the browser.'; }
  });
  deck.classList.add('is-ready');
  show(0);
})();
