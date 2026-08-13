document.addEventListener('DOMContentLoaded', () => {
  const sidebar = document.getElementById('sidebar');
  const toggle = document.getElementById('sidebarToggle');

  if (toggle && sidebar) {
    toggle.addEventListener('click', () => sidebar.classList.toggle('open'));
  }

  document.querySelectorAll('[data-confirm]').forEach(el => {
    el.addEventListener('click', (e) => {
      const msg = el.getAttribute('data-confirm') || 'Are you sure?';
      if (!window.confirm(msg)) e.preventDefault();
    });
  });

  // Live fill for threshold/range-style number inputs paired with a
  // sibling .range-trace-fill via data-trace-max on the input.
  document.querySelectorAll('input[data-trace-max]').forEach((input) => {
    const fill = input.closest('.form-group, label')?.querySelector('.range-trace-fill');
    if (!fill) return;
    const max = parseFloat(input.getAttribute('data-trace-max')) || 100;
    const update = () => {
      const val = parseFloat(input.value) || 0;
      const pct = Math.max(0, Math.min(100, (val / max) * 100));
      fill.style.width = pct + '%';
    };
    input.addEventListener('input', update);
    update();
  });
});
