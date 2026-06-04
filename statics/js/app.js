document.addEventListener('DOMContentLoaded', () => {
  const sidebar = document.getElementById('sidebar');
  const toggle = document.getElementById('sidebarToggle');
  const themeToggle = document.getElementById('themeToggle');

  if (toggle && sidebar) {
    toggle.addEventListener('click', () => sidebar.classList.toggle('open'));
  }

  if (themeToggle) {
    themeToggle.addEventListener('click', () => {
      const body = document.body;
      const isDark = body.classList.toggle('theme-dark');
      body.classList.toggle('theme-light', !isDark);
      themeToggle.textContent = isDark ? '☀' : '☾';
    });
  }

  document.querySelectorAll('[data-confirm]').forEach(el => {
    el.addEventListener('click', (e) => {
      const msg = el.getAttribute('data-confirm') || 'Are you sure?';
      if (!window.confirm(msg)) e.preventDefault();
    });
  });
});
