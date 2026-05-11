/* ==========================================
   NexAuth — Frontend Application Logic
   ========================================== */

const API_BASE = 'http://localhost:5000/api';

// ─────────────────────────────────────────
// UTILITIES
// ─────────────────────────────────────────

function $(id) { return document.getElementById(id); }

function showToast(message, type = 'info', duration = 3500) {
  const icons = { success: 'fa-circle-check', error: 'fa-circle-xmark', info: 'fa-circle-info', warning: 'fa-triangle-exclamation' };
  const container = $('toast-container');
  const toast = document.createElement('div');
  toast.className = `toast ${type}`;
  toast.innerHTML = `
    <i class="fa-solid ${icons[type]} toast-icon"></i>
    <span class="toast-msg">${message}</span>
  `;
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
  const statusEl = input.closest('.input-wrapper')?.querySelector('.input-status');
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

// ─────────────────────────────────────────
// PAGE NAVIGATION
// ─────────────────────────────────────────

function showPage(pageId) {
  document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
  document.querySelectorAll('.nav-link').forEach(l => l.classList.remove('active'));
  const target = $(`page-${pageId}`);
  if (target) {
    target.classList.add('active');
    target.style.animation = 'none';
    requestAnimationFrame(() => {
      target.style.animation = '';
    });
  }
  const navLink = document.querySelector(`.nav-link[data-page="${pageId}"]`);
  if (navLink) navLink.classList.add('active');
}

document.addEventListener('click', e => {
  const link = e.target.closest('[data-page]');
  if (link) {
    e.preventDefault();
    const page = link.dataset.page;
    if (page === 'login' || page === 'signup') {
      showPage(page);
    }
  }
});

// ─────────────────────────────────────────
// PASSWORD VISIBILITY TOGGLE
// ─────────────────────────────────────────

document.querySelectorAll('.toggle-pw').forEach(btn => {
  btn.addEventListener('click', () => {
    const input = $(btn.dataset.target);
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

// ─────────────────────────────────────────
// PASSWORD STRENGTH METER
// ─────────────────────────────────────────

function checkPasswordStrength(pw) {
  const rules = {
    len:     pw.length >= 8,
    upper:   /[A-Z]/.test(pw),
    num:     /[0-9]/.test(pw),
    special: /[^A-Za-z0-9]/.test(pw),
  };
  const score = Object.values(rules).filter(Boolean).length;

  // Update rule indicators
  ['len','upper','num','special'].forEach(key => {
    const el = $(`rule-${key}`);
    if (el) el.classList.toggle('ok', rules[key]);
  });

  // Update bar
  const fill = $('pw-fill');
  const label = $('pw-label');
  if (!fill || !label) return score;

  const map = {
    0: { w: 0,    col: '#333', lbl: 'Enter a password' },
    1: { w: 25,   col: '#ff5068', lbl: 'Too weak' },
    2: { w: 50,   col: '#ffb347', lbl: 'Fair' },
    3: { w: 75,   col: '#60c8ff', lbl: 'Good' },
    4: { w: 100,  col: '#3effa0', lbl: 'Strong 🔥' },
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
  if (e.target.value) setInputStatus('signup-password', '');
});

// ─────────────────────────────────────────
// REAL-TIME VALIDATION
// ─────────────────────────────────────────

function validateEmail(email) {
  return /^[^\s@]+@gmail\.com$/i.test(email);
}

// Signup name
$('signup-name')?.addEventListener('input', e => {
  const val = e.target.value.trim();
  showError('signup-name-err', '');
  if (val.length > 0) setInputStatus('signup-name', val.length >= 2 ? 'valid' : 'invalid');
});

// Signup email
$('signup-email')?.addEventListener('input', e => {
  const val = e.target.value.trim();
  showError('signup-email-err', '');
  if (val.length > 3) setInputStatus('signup-email', validateEmail(val) ? 'valid' : 'invalid');
});

// Login email
$('login-email')?.addEventListener('input', e => {
  showError('login-email-err', '');
});

// ─────────────────────────────────────────
// AUTH API HELPERS
// ─────────────────────────────────────────

async function apiRequest(endpoint, body) {
  const res = await fetch(`${API_BASE}${endpoint}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  const data = await res.json();
  return { ok: res.ok, status: res.status, data };
}

function saveSession(token, user) {
  localStorage.setItem('nexauth_token', token);
  localStorage.setItem('nexauth_user', JSON.stringify(user));
}

function clearSession() {
  localStorage.removeItem('nexauth_token');
  localStorage.removeItem('nexauth_user');
}

function getSession() {
  const token = localStorage.getItem('nexauth_token');
  const user  = JSON.parse(localStorage.getItem('nexauth_user') || 'null');
  return { token, user };
}

// ─────────────────────────────────────────
// SIGN UP
// ─────────────────────────────────────────

$('signup-form')?.addEventListener('submit', async e => {
  e.preventDefault();
  const name     = $('signup-name').value.trim();
  const email    = $('signup-email').value.trim();
  const password = $('signup-password').value;
  const btn      = $('signup-btn');

  // Clear errors
  showError('signup-name-err', '');
  showError('signup-email-err', '');
  showError('signup-pw-err', '');

  let valid = true;

  if (!name || name.length < 2) {
    showError('signup-name-err', 'Please enter your full name.');
    setInputStatus('signup-name', 'invalid');
    valid = false;
  }

  if (!validateEmail(email)) {
    showError('signup-email-err', 'Enter a valid Gmail address (e.g. you@gmail.com).');
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
      saveSession(data.token, data.user);
      showToast(`Account created! Welcome, ${data.user.name} 🎉`, 'success', 4000);
      setTimeout(() => loadDashboard(data.user), 600);
    } else {
      const msg = data.message || 'Signup failed. Try again.';
      if (msg.toLowerCase().includes('email') || msg.toLowerCase().includes('gmail')) {
        showError('signup-email-err', msg);
        setInputStatus('signup-email', 'invalid');
      } else if (msg.toLowerCase().includes('password')) {
        showError('signup-pw-err', msg);
        setInputStatus('signup-password', 'invalid');
      } else {
        showToast(msg, 'error');
      }
    }
  } catch (err) {
    showToast('Cannot reach server. Is the backend running?', 'error');
  } finally {
    setLoading(btn, false);
  }
});

// ─────────────────────────────────────────
// LOGIN
// ─────────────────────────────────────────

$('login-form')?.addEventListener('submit', async e => {
  e.preventDefault();
  const email    = $('login-email').value.trim();
  const password = $('login-password').value;
  const remember = $('remember-me').checked;
  const btn      = $('login-btn');

  showError('login-email-err', '');
  showError('login-pw-err', '');

  let valid = true;

  if (!validateEmail(email)) {
    showError('login-email-err', 'Enter a valid Gmail address.');
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
      saveSession(data.token, data.user);
      showToast(`Welcome back, ${data.user.name}! ✅`, 'success');
      setTimeout(() => loadDashboard(data.user), 400);
    } else {
      const msg = data.message || 'Login failed.';
      showToast(msg, 'error');
      showError('login-pw-err', msg);
    }
  } catch (err) {
    showToast('Cannot reach server. Is the backend running?', 'error');
  } finally {
    setLoading(btn, false);
  }
});

// ─────────────────────────────────────────
// DASHBOARD
// ─────────────────────────────────────────

function loadDashboard(user) {
  $('dash-fullname').textContent = user.name;
  $('dash-name-chip').textContent = user.name.split(' ')[0];
  $('dash-avatar').textContent = user.name.charAt(0).toUpperCase();
  $('dash-name-val').textContent = user.name;
  $('dash-email-val').textContent = user.email;
  $('dash-joined-val').textContent = user.created_at
    ? new Date(user.created_at).toLocaleDateString('en-US', { year: 'numeric', month: 'long', day: 'numeric' })
    : 'Today';
  $('dash-login-time').textContent = new Date().toLocaleTimeString();

  // Hide navbar auth links
  document.querySelector('.nav-links').style.display = 'none';

  showPage('dashboard');
}

function logout() {
  clearSession();
  document.querySelector('.nav-links').style.display = '';
  showToast('You have been logged out.', 'info');
  showPage('login');
  // Reset forms
  $('login-form')?.reset();
  $('signup-form')?.reset();
  checkPasswordStrength('');
}

$('logout-btn')?.addEventListener('click', logout);
$('dash-logout-btn2')?.addEventListener('click', logout);

// ─────────────────────────────────────────
// FORGOT PASSWORD MODAL
// ─────────────────────────────────────────

$('show-forgot')?.addEventListener('click', e => {
  e.preventDefault();
  $('forgot-modal').classList.add('open');
});

$('close-forgot')?.addEventListener('click', () => {
  $('forgot-modal').classList.remove('open');
});

$('forgot-modal')?.addEventListener('click', e => {
  if (e.target === $('forgot-modal')) $('forgot-modal').classList.remove('open');
});

window.handleForgot = function () {
  const email = $('forgot-email').value.trim();
  if (!validateEmail(email)) {
    showToast('Enter a valid Gmail address.', 'error');
    return;
  }
  showToast('Reset link sent! Check your inbox.', 'success', 4000);
  $('forgot-modal').classList.remove('open');
};

// ─────────────────────────────────────────
// SESSION RESTORE ON LOAD
// ─────────────────────────────────────────

(function init() {
  const { token, user } = getSession();
  if (token && user) {
    loadDashboard(user);
  } else {
    showPage('login');
  }
})();
