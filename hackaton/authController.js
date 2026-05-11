// ==========================================
// NexAuth — Authentication Controller
// ==========================================

const bcrypt = require('bcryptjs');
const jwt = require('jsonwebtoken');
const { getDb } = require('../config/db');

const SALT_ROUNDS = 12;

// ── Helper: sign a JWT ──
function signToken(userId, remember = false) {
  return jwt.sign(
    { id: userId },
    process.env.JWT_SECRET,
    { expiresIn: remember ? '30d' : '7d' }
  );
}

// ── Helper: format user for response (never return raw password) ──
function safeUser(user) {
  const { password, ...rest } = user;
  return rest;
}

// ──────────────────────────────────────────
// REGISTER
// POST /api/auth/register
// ──────────────────────────────────────────
exports.register = async (req, res) => {
  try {
    const { name, email, password } = req.body;
    const db = getDb();

    const emailNorm = email.trim().toLowerCase();

    // ── Check for duplicate email ──
    const existingByEmail = await db.findUserByEmail(emailNorm);
    if (existingByEmail) {
      return res.status(409).json({
        success: false,
        message: 'That Gmail address is already registered.',
      });
    }

    // ── Check for duplicate password (compare against all hashed passwords) ──
    const allUsers = await db.getAllUsers();
    for (const user of allUsers) {
      const pwMatch = await bcrypt.compare(password, user.password);
      if (pwMatch) {
        return res.status(409).json({
          success: false,
          message: 'That password is already in use. Please choose a unique password.',
        });
      }
    }

    // ── Hash password ──
    const hashedPassword = await bcrypt.hash(password, SALT_ROUNDS);

    // ── Create user ──
    const newUser = await db.createUser({
      name: name.trim(),
      email: emailNorm,
      password: hashedPassword,
    });

    const token = signToken(newUser.id);

    return res.status(201).json({
      success: true,
      message: 'Account created successfully.',
      token,
      user: safeUser(newUser),
    });

  } catch (err) {
    console.error('[Register Error]', err);
    return res.status(500).json({ success: false, message: 'Registration failed. Please try again.' });
  }
};

// ──────────────────────────────────────────
// LOGIN
// POST /api/auth/login
// ──────────────────────────────────────────
exports.login = async (req, res) => {
  try {
    const { email, password, remember } = req.body;
    const db = getDb();

    const emailNorm = email.trim().toLowerCase();

    // ── Find user ──
    const user = await db.findUserByEmail(emailNorm);
    if (!user) {
      return res.status(401).json({ success: false, message: 'Invalid email or password.' });
    }

    // ── Verify password ──
    const isMatch = await bcrypt.compare(password, user.password);
    if (!isMatch) {
      return res.status(401).json({ success: false, message: 'Invalid email or password.' });
    }

    const token = signToken(user.id, !!remember);

    return res.status(200).json({
      success: true,
      message: 'Login successful.',
      token,
      user: safeUser(user),
    });

  } catch (err) {
    console.error('[Login Error]', err);
    return res.status(500).json({ success: false, message: 'Login failed. Please try again.' });
  }
};

// ──────────────────────────────────────────
// GET ME (protected route)
// GET /api/auth/me
// ──────────────────────────────────────────
exports.getMe = async (req, res) => {
  try {
    const db = getDb();
    const user = await db.findUserById(req.userId);
    if (!user) return res.status(404).json({ success: false, message: 'User not found.' });

    return res.status(200).json({
      success: true,
      user: safeUser(user),
    });
  } catch (err) {
    console.error('[GetMe Error]', err);
    return res.status(500).json({ success: false, message: 'Failed to fetch user.' });
  }
};
