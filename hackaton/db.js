// ==========================================
// NexAuth — Database Configuration
// Supports: MongoDB (default) or MySQL
// ==========================================

require('dotenv').config();
const DB_TYPE = process.env.DB_TYPE || 'mongodb';

let dbInstance = null;

// ──────────────────────────────────────────
// MONGODB ADAPTER
// ──────────────────────────────────────────
async function connectMongo() {
  const { MongoClient, ObjectId } = require('mongodb');
  const client = new MongoClient(process.env.MONGODB_URI);
  await client.connect();
  const db = client.db(process.env.DB_NAME || 'nexauth');
  const users = db.collection('users');

  // Create unique index on email
  await users.createIndex({ email: 1 }, { unique: true });

  console.log('✅ Connected to MongoDB');

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
      const all = await users.find({}, { projection: { password: 1 } }).toArray();
      return all;
    },
  };
}

// ──────────────────────────────────────────
// MYSQL ADAPTER
// ──────────────────────────────────────────
async function connectMySQL() {
  const mysql = require('mysql2/promise');
  const pool = mysql.createPool({
    host:     process.env.MYSQL_HOST     || 'localhost',
    user:     process.env.MYSQL_USER     || 'root',
    password: process.env.MYSQL_PASSWORD || '',
    database: process.env.MYSQL_DATABASE || 'nexauth',
    waitForConnections: true,
    connectionLimit: 10,
  });

  // Create table if it doesn't exist
  await pool.execute(`
    CREATE TABLE IF NOT EXISTS users (
      id         INT AUTO_INCREMENT PRIMARY KEY,
      name       VARCHAR(100) NOT NULL,
      email      VARCHAR(255) NOT NULL UNIQUE,
      password   VARCHAR(255) NOT NULL,
      created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
  `);

  console.log('✅ Connected to MySQL');

  return {
    findUserByEmail: async (email) => {
      const [rows] = await pool.execute('SELECT * FROM users WHERE email = ? LIMIT 1', [email]);
      return rows[0] || null;
    },
    findUserById: async (id) => {
      const [rows] = await pool.execute('SELECT * FROM users WHERE id = ? LIMIT 1', [id]);
      return rows[0] || null;
    },
    createUser: async ({ name, email, password }) => {
      const [result] = await pool.execute(
        'INSERT INTO users (name, email, password) VALUES (?, ?, ?)',
        [name, email, password]
      );
      return { id: result.insertId, name, email, password, created_at: new Date() };
    },
    getAllUsers: async () => {
      const [rows] = await pool.execute('SELECT id, password FROM users');
      return rows;
    },
  };
}

// ──────────────────────────────────────────
// CONNECT
// ──────────────────────────────────────────
async function connectDb() {
  try {
    if (DB_TYPE === 'mysql') {
      dbInstance = await connectMySQL();
    } else {
      dbInstance = await connectMongo();
    }
  } catch (err) {
    console.error('❌ Database connection failed:', err.message);
    process.exit(1);
  }
}

function getDb() {
  if (!dbInstance) throw new Error('Database not initialized. Call connectDb() first.');
  return dbInstance;
}

// Auto-connect when this module is first required by server.js
connectDb();

module.exports = { connectDb, getDb };
