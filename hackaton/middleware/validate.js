function sanitize(str) {
  if (typeof str !== 'string') return '';
  return str.replace(/[<>'"`;]/g, '').trim();
}

function isValidEmail(email) {
  return /^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$/i.test(email);
}

exports.validateRegister = (req, res, next) => {
  let { name, email, password } = req.body;

  name  = sanitize(name  || '');
  email = sanitize(email || '').toLowerCase();

  const errors = [];

  if (!name || name.length < 2 || name.length > 100) {
    errors.push('Full name must be between 2 and 100 characters.');
  }

  if (!isValidEmail(email)) {
    errors.push('A valid email address is required.');
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

  req.body.name  = name;
  req.body.email = email;
  next();
};

exports.validateLogin = (req, res, next) => {
  let { email, password } = req.body;

  email = sanitize(email || '').toLowerCase();

  const errors = [];

  if (!isValidEmail(email)) {
    errors.push('A valid email address is required.');
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
