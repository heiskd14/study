/* TAU Online Study — Auth Frontend (adapted from NexAuth) */

const API_BASE = '/api';

function $(id) { return document.getElementById(id); }

function showToast(message, type = 'info', duration = 3500) {
  const icons = { success: 'fa-circle-check', error: 'fa-circle-xmark', info: 'fa-circle-info', warning: 'fa-triangle-exclamation' };
  const container = $('toast-container');
  if (!container) return;
  const toast = document.createElement('div');
  toast.className = `tau-toast ${type}`;
  toast.innerHTML = `<i class="fa-solid ${icons[type]} toast-icon"></i><span class="toast-msg">${message}</span>`;
  container.appendChild(toast);
  setTimeout(() => {
    toast.classList.add('removing');
    setTimeout(() => toast.remove(), 300);
  }, duration);
}

function setLoading(btn, state) {
  btn.classList.toggle('loading', state);
  btn.disabled = state;
}

function showError(fieldId, message) {
  const el = $(fieldId);
  if (!el) return;
  el.textContent = message;
  el.classList.toggle('visible', !!message);
}

function setInputStatus(inputId, status) {
  const input = $(inputId);
  if (!input) return;
  const statusEl = input.closest('.tau-input-wrapper')?.querySelector('.input-status');
  if (!statusEl) return;
  statusEl.className = 'input-status';
  if (status === 'valid') {
    statusEl.innerHTML = '<i class="fa-solid fa-circle-check"></i>';
    statusEl.classList.add('valid');
  } else if (status === 'invalid') {
    statusEl.innerHTML = '<i class="fa-solid fa-circle-xmark"></i>';
    statusEl.classList.add('invalid');
  }
}

function showPage(pageId) {
  document.querySelectorAll('.tau-page').forEach(p => p.classList.remove('active'));
  const target = $(`tau-page-${pageId}`);
  if (target) {
    target.classList.add('active');
  }
  document.querySelectorAll('.tau-tab-btn').forEach(b => b.classList.remove('active'));
  const tab = document.querySelector(`.tau-tab-btn[data-page="${pageId}"]`);
  if (tab) tab.classList.add('active');
}

document.addEventListener('DOMContentLoaded', () => {
  document.querySelectorAll('[data-page]').forEach(el => {
    el.addEventListener('click', e => {
      const page = el.dataset.page;
      if (page === 'login' || page === 'signup') {
        e.preventDefault();
        showPage(page);
      }
    });
  });

  document.querySelectorAll('.toggle-pw').forEach(btn => {
    btn.addEventListener('click', () => {
      const input = $(btn.dataset.target);
      if (!input) return;
      const icon = btn.querySelector('i');
      if (input.type === 'password') {
        input.type = 'text';
        icon.className = 'fa-regular fa-eye-slash';
      } else {
        input.type = 'password';
        icon.className = 'fa-regular fa-eye';
      }
    });
  });

  const initialTab = document.body.dataset.tab || 'login';
  showPage(initialTab);
});

function checkPasswordStrength(pw) {
  const rules = {
    len:     pw.length >= 8,
    upper:   /[A-Z]/.test(pw),
    num:     /[0-9]/.test(pw),
    special: /[^A-Za-z0-9]/.test(pw),
  };
  const score = Object.values(rules).filter(Boolean).length;

  ['len','upper','num','special'].forEach(key => {
    const el = $(`rule-${key}`);
    if (el) el.classList.toggle('ok', rules[key]);
  });

  const fill = $('pw-fill');
  const label = $('pw-label');
  if (!fill || !label) return score;

  const map = {
    0: { w: 0,   col: '#333',    lbl: 'Enter a password' },
    1: { w: 25,  col: '#ff5068', lbl: 'Too weak' },
    2: { w: 50,  col: '#ffb347', lbl: 'Fair' },
    3: { w: 75,  col: '#60c8ff', lbl: 'Good' },
    4: { w: 100, col: '#3effa0', lbl: 'Strong' },
  };
  const m = map[score];
  fill.style.width = m.w + '%';
  fill.style.background = m.col;
  label.textContent = m.lbl;
  label.style.color = m.col;
  return score;
}

$('signup-password')?.addEventListener('input', e => {
  checkPasswordStrength(e.target.value);
  showError('signup-pw-err', '');
});

function validateEmail(email) {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email);
}

$('signup-name')?.addEventListener('input', e => {
  const val = e.target.value.trim();
  showError('signup-name-err', '');
  if (val.length > 0) setInputStatus('signup-name', val.length >= 2 ? 'valid' : 'invalid');
});

$('signup-email')?.addEventListener('input', e => {
  const val = e.target.value.trim();
  showError('signup-email-err', '');
  if (val.length > 3) setInputStatus('signup-email', validateEmail(val) ? 'valid' : 'invalid');
});

$('login-email')?.addEventListener('input', () => showError('login-email-err', ''));

async function apiRequest(endpoint, body) {
  const res = await fetch(`${API_BASE}${endpoint}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  const data = await res.json();
  return { ok: res.ok, status: res.status, data };
}

async function syncFlaskSession(token, user) {
  try {
    await fetch('/auth/sync', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ token, user }),
    });
  } catch (e) {
    console.warn('Session sync failed:', e);
  }
}

$('signup-form')?.addEventListener('submit', async e => {
  e.preventDefault();
  const name     = $('signup-name').value.trim();
  const email    = $('signup-email').value.trim();
  const password = $('signup-password').value;
  const btn      = $('signup-btn');

  showError('signup-name-err', '');
  showError('signup-email-err', '');
  showError('signup-pw-err', '');

  let valid = true;

  if (!name || name.length < 2) {
    showError('signup-name-err', 'Please enter your full name (min. 2 characters).');
    setInputStatus('signup-name', 'invalid');
    valid = false;
  }

  if (!validateEmail(email)) {
    showError('signup-email-err', 'Please enter a valid email address.');
    setInputStatus('signup-email', 'invalid');
    valid = false;
  }

  const strength = checkPasswordStrength(password);
  if (password.length < 8) {
    showError('signup-pw-err', 'Password must be at least 8 characters.');
    setInputStatus('signup-password', 'invalid');
    valid = false;
  } else if (strength < 2) {
    showError('signup-pw-err', 'Password is too weak. Add uppercase, numbers, or symbols.');
    setInputStatus('signup-password', 'invalid');
    valid = false;
  }

  if (!valid) return;

  setLoading(btn, true);
  try {
    const { ok, data } = await apiRequest('/auth/register', { name, email, password });
    if (ok) {
      showToast(`Account created! Welcome, ${data.user.name}`, 'success', 4000);
      await syncFlaskSession(data.token, data.user);
      setTimeout(() => { window.location.href = '/'; }, 800);
    } else {
      const msg = data.message || 'Signup failed. Try again.';
      if (msg.toLowerCase().includes('email')) {
        showError('signup-email-err', msg);
        setInputStatus('signup-email', 'invalid');
      } else if (msg.toLowerCase().includes('password')) {
        showError('signup-pw-err', msg);
      } else {
        showToast(msg, 'error');
      }
    }
  } catch (err) {
    showToast('Cannot reach server. Please try again.', 'error');
  } finally {
    setLoading(btn, false);
  }
});

$('login-form')?.addEventListener('submit', async e => {
  e.preventDefault();
  const email    = $('login-email').value.trim();
  const password = $('login-password').value;
  const remember = $('remember-me')?.checked || false;
  const btn      = $('login-btn');

  showError('login-email-err', '');
  showError('login-pw-err', '');

  let valid = true;
  if (!validateEmail(email)) {
    showError('login-email-err', 'Please enter a valid email address.');
    valid = false;
  }
  if (!password) {
    showError('login-pw-err', 'Password is required.');
    valid = false;
  }
  if (!valid) return;

  setLoading(btn, true);
  try {
    const { ok, data } = await apiRequest('/auth/login', { email, password, remember });
    if (ok) {
      showToast(`Welcome back, ${data.user.name}!`, 'success');
      await syncFlaskSession(data.token, data.user);
      setTimeout(() => { window.location.href = '/'; }, 600);
    } else {
      const msg = data.message || 'Login failed.';
      showToast(msg, 'error');
      showError('login-pw-err', msg);
    }
  } catch (err) {
    showToast('Cannot reach server. Please try again.', 'error');
  } finally {
    setLoading(btn, false);
  }
});

$('show-forgot')?.addEventListener('click', e => {
  e.preventDefault();
  const modal = $('forgot-modal');
  if (modal) modal.classList.add('open');
});

$('close-forgot')?.addEventListener('click', () => {
  const modal = $('forgot-modal');
  if (modal) modal.classList.remove('open');
});

$('forgot-modal')?.addEventListener('click', e => {
  if (e.target === $('forgot-modal')) $('forgot-modal').classList.remove('open');
});

window.handleForgot = function () {
  const email = $('forgot-email')?.value.trim();
  if (!validateEmail(email)) {
    showToast('Enter a valid email address.', 'error');
    return;
  }
  showToast('Reset link sent! Check your inbox.', 'success', 4000);
  $('forgot-modal').classList.remove('open');
};
