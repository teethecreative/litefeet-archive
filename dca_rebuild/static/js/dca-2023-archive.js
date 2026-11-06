/* Filter historical category labels locally; native details work without JS. */
(function () {
  'use strict';
  function boot() {
    const root = document.getElementById('dca-2023-archive');
    if (!root) return;
    const search = root.querySelector('#dca23-search');
    const all = root.querySelector('#dca23-all');
    const list = root.querySelector('#dca23-categories');
    const count = root.querySelector('#dca23-count');
    const empty = root.querySelector('#dca23-empty');
    const categories = Array.from(root.querySelectorAll('[data-category-name]'));
    function render() {
      const query = search.value.trim().toLocaleLowerCase();
      let matches = 0;
      categories.forEach(function (category) {
        category.hidden = !category.dataset.categoryName.toLocaleLowerCase().includes(query);
        if (!category.hidden) matches += 1;
      });
      list.hidden = matches === 0;
      empty.hidden = matches !== 0;
      count.textContent = query ? matches + ' of ' + categories.length + ' categories' : categories.length + ' categories';
      list.scrollTop = 0;
    }
    search.addEventListener('input', render);
    all.addEventListener('click', function () {
      search.value = ''; render(); search.focus();
    });
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot);
  else boot();
})();
