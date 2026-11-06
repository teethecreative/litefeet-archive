/* Five visible category rows, with native scrolling and local search. */
(function () {
  'use strict';
  function boot() {
    document.querySelectorAll('[data-category-results]').forEach(function (section) {
      const search = section.querySelector('[data-category-search]');
      const viewport = section.querySelector('.lfv-results-scroll');
      const table = section.querySelector('table');
      const rows = Array.from(section.querySelectorAll('[data-result-row]'));
      const count = section.querySelector('[data-results-count]');
      const empty = section.querySelector('[data-no-results]');
      let scheduled = false;
      function fitRows() {
        scheduled = false;
        const visible = rows.filter(row => !row.hidden).slice(0, 5);
        if (!visible.length) return;
        const height = table.tHead.getBoundingClientRect().height + visible.reduce((sum, row) => sum + row.getBoundingClientRect().height, 0);
        viewport.style.maxHeight = Math.ceil(height + 2) + 'px';
      }
      function scheduleFit() {
        if (!scheduled) { scheduled = true; window.requestAnimationFrame(fitRows); }
      }
      function render() {
        const query = search.value.trim().toLocaleLowerCase();
        let matches = 0;
        rows.forEach(function (row) {
          row.hidden = !row.textContent.toLocaleLowerCase().includes(query);
          if (!row.hidden) matches += 1;
        });
        count.textContent = query ? matches + ' of ' + rows.length + ' categories' : rows.length + ' categories';
        empty.hidden = matches !== 0;
        viewport.hidden = matches === 0;
        viewport.scrollTop = 0;
        scheduleFit();
      }
      search.addEventListener('input', render);
      window.addEventListener('resize', scheduleFit);
      if (window.ResizeObserver) new ResizeObserver(scheduleFit).observe(table);
      if (document.fonts && document.fonts.ready) document.fonts.ready.then(scheduleFit);
      render();
    });
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot);
  else boot();
})();
