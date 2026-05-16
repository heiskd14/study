const bcrypt = require('bcryptjs');
const jwt = require('jsonwebtoken');
const crypto = require('crypto');
const { getDb } = require('../config/db');
const { sendVerificationEmail } = require('../utils/mailer');

const SALT_ROUNDS = 12;

function signToken(userId, remember = false) {
  return jwt.sign(
    { id: userId },
    process.env.JWT_SECRET,
    { expiresIn: remember ? '30d' : '7d' }
  );
}

function safeUser(user) {
  const { password, verification_token, ...rest } = user;
  return rest;
}

exports.register = async (req, res) => {
  try {
    const { name, email, password } = req.body;
    const db = getDb();
    const emailNorm = email.trim().toLowerCase();

    const existingByEmail = await db.findUserByEmail(emailNorm);
    if (existingByEmail) {
      return res.status(409).json({
        success: false,
        message: 'That email address is already registered.',
      });
    }

    const allUsers = await db.getAllUsers();
    for (const user of allUsers) {
      if (user.password) {
        const pwMatch = await bcrypt.compare(password, user.password);
        if (pwMatch) {
          return res.status(409).json({
            success: false,
            message: 'That password is already in use. Please choose a unique password.',
          });
        }
      }
    }

    const hashedPassword = await bcrypt.hash(password, SALT_ROUNDS);
    const verificationToken = crypto.randomBytes(32).toString('hex');

    const newUser = await db.createUser({
      name: name.trim(),
      email: emailNorm,
      password: hashedPassword,
    });

    await db.setVerificationToken(emailNorm, verificationToken);

    const appBase = process.env.APP_BASE_URL || `http://localhost:5000`;
    const verifyUrl = `${appBase}/verify-email/${verificationToken}`;

    sendVerificationEmail(emailNorm, verifyUrl).catch(err =>
      console.error('[Mailer Error]', err.message)
    );

    return res.status(201).json({
      success: true,
      needsVerification: true,
      message: 'Account created! Please check your email to verify your account before logging in.',
    });

  } catch (err) {
    console.error('[Register Error]', err);
    if (err.code === 11000 || (err.message && err.message.includes('UNIQUE'))) {
      return res.status(409).json({ success: false, message: 'That email address is already registered.' });
    }
    return res.status(500).json({ success: false, message: 'Registration failed. Please try again.' });
  }
};

exports.login = async (req, res) => {
  try {
    const { email, password, remember } = req.body;
    const db = getDb();
    const emailNorm = email.trim().toLowerCase();

    const user = await db.findUserByEmail(emailNorm);
    if (!user) {
      return res.status(401).json({ success: false, message: 'Invalid email or password.' });
    }

    const isMatch = await bcrypt.compare(password, user.password);
    if (!isMatch) {
      return res.status(401).json({ success: false, message: 'Invalid email or password.' });
    }

    if (user.email_verified === false) {
      return res.status(403).json({
        success: false,
        needsVerification: true,
        message: 'Please verify your email before logging in. Check your inbox for the verification link.',
      });
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

exports.verifyEmail = async (req, res) => {
  try {
    const { token } = req.params;
    const db = getDb();
    const user = await db.verifyEmail(token);
    if (!user) {
      return res.status(400).json({ success: false, message: 'Invalid or expired verification link.' });
    }
    return res.status(200).json({ success: true, message: 'Email verified! You can now log in.' });
  } catch (err) {
    console.error('[VerifyEmail Error]', err);
    return res.status(500).json({ success: false, message: 'Verification failed. Please try again.' });
  }
};
