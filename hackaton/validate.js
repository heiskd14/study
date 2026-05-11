// ==========================================
// NexAuth — Input Validation Middleware
// ==========================================

// Sanitize a string to prevent basic injection
function sanitize(str) {
  if (typeof str !== 'string') return '';
  return str.replace(/[<>'"`;]/g, '').trim();
}

// Validate Gmail format
function isValidGmail(email) {
  return /^[a-zA-Z0-9._%+\-]+@gmail\.com$/i.test(email);
}

// ── Register Validation ──
exports.validateRegister = (req, res, next) => {
  let { name, email, password } = req.body;

  // Sanitize
  name  = sanitize(name  || '');
  email = sanitize(email || '').toLowerCase();
  // Don't sanitize password — just validate length/format

  const errors = [];

  if (!name || name.length < 2 || name.length > 100) {
    errors.push('Full name must be between 2 and 100 characters.');
  }

  if (!isValidGmail(email)) {
    errors.push('A valid Gmail address is required (e.g. you@gmail.com).');
  }

  if (!password || typeof password !== 'string') {
    errors.push('Password is required.');
  } else if (password.length < 8) {
    errors.push('Password must be at least 8 characters.');
  } else if (password.length > 128) {
    errors.push('Password must be less than 128 characters.');
  }

  if (errors.length > 0) {
    return res.status(400).json({ success: false, message: errors[0], errors });
  }

  // Attach sanitized values
  req.body.name  = name;
  req.body.email = email;

  next();
};

// ── Login Validation ──
exports.validateLogin = (req, res, next) => {
  let { email, password } = req.body;

  email = sanitize(email || '').toLowerCase();

  const errors = [];

  if (!isValidGmail(email)) {
    errors.push('A valid Gmail address is required.');
  }

  if (!password) {
    errors.push('Password is required.');
  }

  if (errors.length > 0) {
    return res.status(400).json({ success: false, message: errors[0], errors });
  }

  req.body.email = email;
  next();
};
