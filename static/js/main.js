/**
 * main.js – Homzho ERP Frontend
 * Handles: sidebar toggle, dark mode, global search, form UX,
 *          flatpickr date pickers, loading overlay, scroll-to-top,
 *          duplicate-submission prevention.
 */

'use strict';

/* ------------------------------------------------------------------ */
/* Sidebar                                                              */
/* ------------------------------------------------------------------ */

const sidebar       = document.getElementById('sidebar');
const mainWrapper   = document.getElementById('mainWrapper');
const sidebarToggle = document.getElementById('sidebarToggle');
const sidebarClose  = document.getElementById('sidebarClose');
const sidebarOverlay= document.getElementById('sidebarOverlay');

function openSidebar() {
  sidebar?.classList.add('open');
  sidebarOverlay?.classList.add('active');
  document.body.style.overflow = 'hidden';
}
function closeSidebar() {
  sidebar?.classList.remove('open');
  sidebarOverlay?.classList.remove('active');
  document.body.style.overflow = '';
}

sidebarToggle?.addEventListener('click', () => {
  if (window.innerWidth < 768) {
    sidebar?.classList.contains('open') ? closeSidebar() : openSidebar();
  }
});
sidebarClose?.addEventListener('click', closeSidebar);
sidebarOverlay?.addEventListener('click', closeSidebar);

/* ------------------------------------------------------------------ */
/* Dark Mode                                                            */
/* ------------------------------------------------------------------ */

const darkToggle = document.getElementById('darkModeToggle');
const darkIcon   = document.getElementById('darkModeIcon');
const htmlEl     = document.documentElement;

function applyDarkMode(dark) {
  htmlEl.setAttribute('data-bs-theme', dark ? 'dark' : 'light');
  if (darkIcon) {
    darkIcon.className = dark ? 'bi bi-sun-fill' : 'bi bi-moon-fill';
  }
  localStorage.setItem('homzho-dark', dark ? '1' : '0');
}

// Restore saved preference
const savedDark = localStorage.getItem('homzho-dark');
if (savedDark === '1') applyDarkMode(true);

darkToggle?.addEventListener('click', () => {
  const isDark = htmlEl.getAttribute('data-bs-theme') === 'dark';
  applyDarkMode(!isDark);
});

/* ------------------------------------------------------------------ */
/* Global Search (AJAX)                                                 */
/* ------------------------------------------------------------------ */

const searchInput   = document.getElementById('globalSearch');
const searchResults = document.getElementById('searchResults');

let searchTimer = null;

searchInput?.addEventListener('input', () => {
  clearTimeout(searchTimer);
  const q = searchInput.value.trim();
  if (q.length < 2) {
    searchResults.style.display = 'none';
    return;
  }
  searchTimer = setTimeout(() => doSearch(q), 300);
});

async function doSearch(q) {
  try {
    const res = await fetch(`/search?q=${encodeURIComponent(q)}`);
    const data = await res.json();
    renderSearchResults(data);
  } catch (e) {
    console.error('Search error:', e);
  }
}

function renderSearchResults(items) {
  if (!items.length) {
    searchResults.innerHTML = '<div class="p-3 text-muted small">No results found.</div>';
    searchResults.style.display = 'block';
    return;
  }
  searchResults.innerHTML = items.map(item => `
    <a class="search-result-item" href="${item.url}">
      <span class="search-type-badge">${item.type}</span>
      <span class="flex-grow-1">
        <span class="fw-600">${item.label}</span>
        <small class="text-muted ms-1">${item.sub}</small>
      </span>
      <i class="bi bi-arrow-right text-muted"></i>
    </a>
  `).join('');
  searchResults.style.display = 'block';
}

// Close search on outside click
document.addEventListener('click', e => {
  if (searchResults && !e.target.closest('#globalSearchWrap')) {
    searchResults.style.display = 'none';
  }
});

/* ------------------------------------------------------------------ */
/* Flatpickr Date Pickers                                               */
/* ------------------------------------------------------------------ */

document.addEventListener('DOMContentLoaded', () => {
  // Initialise all date inputs
  document.querySelectorAll('input[type="date"], .datepicker').forEach(el => {
    if (el._flatpickr) return; // Already initialised
    flatpickr(el, {
      dateFormat: 'Y-m-d',
      allowInput: true,
      disableMobile: false,
    });
  });
});

/* ------------------------------------------------------------------ */
/* Loading Overlay (show on form submit)                                */
/* ------------------------------------------------------------------ */

const loadingOverlay = document.getElementById('loadingOverlay');

function showLoading() {
  loadingOverlay?.classList.remove('d-none');
}
function hideLoading() {
  loadingOverlay?.classList.add('d-none');
}

// Prevent duplicate form submissions
document.addEventListener('submit', function (e) {
  const form = e.target;
  if (form.dataset.submitted === 'true') {
    e.preventDefault();
    return;
  }
  form.dataset.submitted = 'true';
  // Show loading for non-file forms only (file upload takes longer)
  if (!form.enctype || form.enctype !== 'multipart/form-data') {
    showLoading();
  }
  // Re-enable after 10s as safety net
  setTimeout(() => {
    form.dataset.submitted = 'false';
    hideLoading();
  }, 10000);
});

/* ------------------------------------------------------------------ */
/* Auto-dismiss Flash Alerts                                            */
/* ------------------------------------------------------------------ */

document.addEventListener('DOMContentLoaded', () => {
  document.querySelectorAll('.flash-alert').forEach(alert => {
    setTimeout(() => {
      const bsAlert = bootstrap.Alert.getOrCreateInstance(alert);
      bsAlert?.close();
    }, 5000);
  });
});

/* ------------------------------------------------------------------ */
/* Scroll-to-Top Button                                                 */
/* ------------------------------------------------------------------ */

const scrollBtn = document.createElement('button');
scrollBtn.className = 'scroll-top-btn';
scrollBtn.innerHTML = '<i class="bi bi-arrow-up"></i>';
scrollBtn.setAttribute('title', 'Back to top');
document.body.appendChild(scrollBtn);

scrollBtn.addEventListener('click', () => window.scrollTo({ top: 0, behavior: 'smooth' }));

window.addEventListener('scroll', () => {
  scrollBtn.classList.toggle('visible', window.scrollY > 300);
});

/* ------------------------------------------------------------------ */
/* File Upload Preview                                                  */
/* ------------------------------------------------------------------ */

function initFilePreview(inputId, previewContainerId) {
  const input = document.getElementById(inputId);
  const container = document.getElementById(previewContainerId);
  if (!input || !container) return;

  input.addEventListener('change', () => {
    container.innerHTML = '';
    Array.from(input.files).forEach(file => {
      if (!file.type.startsWith('image/')) return;
      const reader = new FileReader();
      reader.onload = e => {
        const div = document.createElement('div');
        div.className = 'upload-thumb';
        div.innerHTML = `<img src="${e.target.result}" alt="${file.name}" />`;
        container.appendChild(div);
      };
      reader.readAsDataURL(file);
    });
  });
}

// Auto-init for standard upload inputs
document.addEventListener('DOMContentLoaded', () => {
  initFilePreview('files', 'filePreviewContainer');
  initFilePreview('service_image', 'imagePreviewContainer');
  initFilePreview('bill_image', 'billImagePreview');
});

/* ------------------------------------------------------------------ */
/* AJAX Customer Due Amount pre-fill (payment form)                     */
/* ------------------------------------------------------------------ */

const custSelect = document.getElementById('customer_id');
custSelect?.addEventListener('change', async () => {
  const id = custSelect.value;
  if (!id) return;
  try {
    const res = await fetch(`/payments/api/customer/${id}/due`);
    const data = await res.json();
    const amountDue = document.getElementById('amount_due');
    const nextBill  = document.getElementById('next_billing_date_hint');
    if (amountDue) amountDue.value = data.monthly_rent;
    if (nextBill)  nextBill.textContent = `Next billing: ${data.next_billing_date || 'N/A'}`;
  } catch(e) {
    console.error('Failed to fetch customer due:', e);
  }
});

/* ------------------------------------------------------------------ */
/* Confirm Delete dialogs                                               */
/* ------------------------------------------------------------------ */

document.addEventListener('click', e => {
  const btn = e.target.closest('[data-confirm]');
  if (!btn) return;
  const msg = btn.dataset.confirm || 'Are you sure?';
  if (!confirm(msg)) e.preventDefault();
});

/* ------------------------------------------------------------------ */
/* Tooltip init                                                         */
/* ------------------------------------------------------------------ */

document.addEventListener('DOMContentLoaded', () => {
  document.querySelectorAll('[data-bs-toggle="tooltip"]').forEach(el => {
    new bootstrap.Tooltip(el, { trigger: 'hover' });
  });
});
