require('dotenv').config({ path: __dirname + '/../.env' });
const DB_TYPE = process.env.DB_TYPE || 'mongodb';

let dbInstance = null;

async function connectMongo() {
  const { MongoClient, ObjectId } = require('mongodb');
  const uri = process.env.MONGODB_URI;
  if (!uri) throw new Error('MONGODB_URI is not set.');
  const client = new MongoClient(uri, {
    serverSelectionTimeoutMS: 5000,
    connectTimeoutMS: 5000,
    socketTimeoutMS: 5000,
  });
  await client.connect();
  const db = client.db(process.env.DB_NAME || 'tau_study');
  const users = db.collection('users');
  await users.createIndex({ email: 1 }, { unique: true });
  console.log('Connected to MongoDB');
  return {
    findUserByEmail: async (email) => {
      const u = await users.findOne({ email });
      if (!u) return null;
      return { ...u, id: u._id.toString() };
    },
    findUserById: async (id) => {
      const u = await users.findOne({ _id: new ObjectId(id) });
      if (!u) return null;
      return { ...u, id: u._id.toString() };
    },
    createUser: async ({ name, email, password }) => {
      const doc = { name, email, password, created_at: new Date() };
      const result = await users.insertOne(doc);
      return { ...doc, id: result.insertedId.toString() };
    },
    getAllUsers: async () => {
      return await users.find({}, { projection: { password: 1 } }).toArray();
    },
  };
}

async function connectPostgres() {
  const { Pool } = require('pg');
  const pool = new Pool({
    connectionString: process.env.DATABASE_URL,
    ssl: process.env.NODE_ENV === 'production' ? { rejectUnauthorized: false } : false,
  });
  await pool.query('SELECT 1');
  await pool.query(`CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    full_name TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    email_verified BOOLEAN DEFAULT FALSE,
    verification_token TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
  )`);
  await pool.query(`ALTER TABLE users ADD COLUMN IF NOT EXISTS email_verified BOOLEAN DEFAULT FALSE`);
  await pool.query(`ALTER TABLE users ADD COLUMN IF NOT EXISTS verification_token TEXT`);
  console.log('Using PostgreSQL database');
  return {
    findUserByEmail: async (email) => {
      const res = await pool.query('SELECT * FROM users WHERE email = $1 LIMIT 1', [email]);
      if (!res.rows[0]) return null;
      const row = res.rows[0];
      return { id: String(row.id), name: row.full_name, email: row.email, password: row.password_hash, created_at: row.created_at };
    },
    findUserById: async (id) => {
      const res = await pool.query('SELECT * FROM users WHERE id = $1 LIMIT 1', [Number(id)]);
      if (!res.rows[0]) return null;
      const row = res.rows[0];
      return { id: String(row.id), name: row.full_name, email: row.email, password: row.password_hash, created_at: row.created_at };
    },
    createUser: async ({ name, email, password }) => {
      const res = await pool.query(
        'INSERT INTO users (full_name, email, password_hash) VALUES ($1, $2, $3) RETURNING *',
        [name, email, password]
      );
      const row = res.rows[0];
      return { id: String(row.id), name: row.full_name, email: row.email, password: row.password_hash, created_at: row.created_at };
    },
    getAllUsers: async () => {
      const res = await pool.query('SELECT id, password_hash AS password FROM users');
      return res.rows;
    },
    setVerificationToken: async (email, token) => {
      await pool.query('UPDATE users SET verification_token = $1 WHERE email = $2', [token, email]);
    },
    verifyEmail: async (token) => {
      const res = await pool.query(
        'UPDATE users SET email_verified = TRUE, verification_token = NULL WHERE verification_token = $1 RETURNING id, full_name, email',
        [token]
      );
      return res.rows[0] || null;
    },
  };
}

async function connectSQLite() {
  const Database = require('better-sqlite3');
  const path = require('path');
  const db = new Database(path.join(__dirname, '../..', 'exam_results.db'));
  db.prepare(`CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    full_name TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
  )`).run();
  console.log('Using SQLite fallback database');
  return {
    findUserByEmail: (email) => {
      const row = db.prepare('SELECT * FROM users WHERE email = ? LIMIT 1').get(email);
      if (!row) return null;
      return { id: String(row.id), name: row.full_name, email: row.email, password: row.password_hash, created_at: row.created_at };
    },
    findUserById: (id) => {
      const row = db.prepare('SELECT * FROM users WHERE id = ? LIMIT 1').get(Number(id));
      if (!row) return null;
      return { id: String(row.id), name: row.full_name, email: row.email, password: row.password_hash, created_at: row.created_at };
    },
    createUser: ({ name, email, password }) => {
      const info = db.prepare('INSERT INTO users (full_name, email, password_hash) VALUES (?, ?, ?)').run(name, email, password);
      return { id: String(info.lastInsertRowid), name, email, password, created_at: new Date().toISOString() };
    },
    getAllUsers: () => {
      return db.prepare('SELECT id, password_hash AS password FROM users').all();
    },
  };
}

async function connectDb() {
  try {
    if (process.env.DATABASE_URL) {
      try {
        dbInstance = await connectPostgres();
      } catch (pgErr) {
        console.warn('PostgreSQL unavailable, falling back to SQLite:', pgErr.message);
        dbInstance = await connectSQLite();
      }
    } else if (DB_TYPE === 'sqlite') {
      dbInstance = await connectSQLite();
    } else {
      try {
        dbInstance = await connectMongo();
      } catch (mongoErr) {
        console.warn('MongoDB unavailable, falling back to SQLite:', mongoErr.message);
        dbInstance = await connectSQLite();
      }
    }
  } catch (err) {
    console.error('Database connection failed:', err.message);
    process.exit(1);
  }
}

function getDb() {
  if (!dbInstance) throw new Error('Database not initialized.');
  return dbInstance;
}

const dbReadyPromise = connectDb();

function waitForDb() {
  return dbReadyPromise;
}

module.exports = { connectDb, getDb, waitForDb };
