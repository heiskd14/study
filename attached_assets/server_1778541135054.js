// ==========================================
// NexAuth — Express Backend Server
// ==========================================

const express = require('express');
const cors = require('cors');
const helmet = require('helmet');
const rateLimit = require('express-rate-limit');
require('dotenv').config();

const authRoutes = require('./routes/auth');

const app = express();
const PORT = process.env.PORT || 5000;

// ── SECURITY MIDDLEWARE ──
app.use(helmet());

// Rate limiting — 100 requests per 15 min per IP
const limiter = rateLimit({
  windowMs: 15 * 60 * 1000,
  max: 100,
  message: { success: false, message: 'Too many requests, please try again later.' },
});
app.use('/api/', limiter);

// Stricter limiter for auth endpoints
const authLimiter = rateLimit({
  windowMs: 15 * 60 * 1000,
  max: 20,
  message: { success: false, message: 'Too many auth attempts. Please wait 15 minutes.' },
});

// ── CORS ──
const allowedOrigins = (process.env.ALLOWED_ORIGINS || 'http://localhost:3000,http://127.0.0.1:5500').split(',');
app.use(cors({
  origin: (origin, callback) => {
    if (!origin || allowedOrigins.includes(origin)) callback(null, true);
    else callback(new Error('Not allowed by CORS'));
  },
  methods: ['GET', 'POST', 'PUT', 'DELETE'],
  allowedHeaders: ['Content-Type', 'Authorization'],
  credentials: true,
}));

// ── BODY PARSING ──
app.use(express.json({ limit: '10kb' })); // Prevent large payloads
app.use(express.urlencoded({ extended: true, limit: '10kb' }));

// ── ROUTES ──
app.use('/api/auth', authLimiter, authRoutes);

// ── HEALTH CHECK ──
app.get('/api/health', (req, res) => {
  res.json({ status: 'ok', timestamp: new Date().toISOString() });
});

// ── 404 HANDLER ──
app.use((req, res) => {
  res.status(404).json({ success: false, message: 'Route not found.' });
});

// ── GLOBAL ERROR HANDLER ──
app.use((err, req, res, _next) => {
  console.error('[Server Error]', err.stack);
  res.status(err.status || 500).json({
    success: false,
    message: process.env.NODE_ENV === 'production' ? 'Internal server error.' : err.message,
  });
});

// ── START SERVER ──
app.listen(PORT, () => {
  console.log(`\n🚀 NexAuth server running on http://localhost:${PORT}`);
  console.log(`   Environment: ${process.env.NODE_ENV || 'development'}`);
  console.log(`   DB Type:     ${process.env.DB_TYPE || 'mongodb'}\n`);
});

module.exports = app;
