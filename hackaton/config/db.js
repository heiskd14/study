require('dotenv').config({ path: __dirname + '/../.env' });
const DB_TYPE = process.env.DB_TYPE || 'mongodb';

let dbInstance = null;

async function connectMongo() {
  const { MongoClient, ObjectId } = require('mongodb');
  const uri = process.env.MONGODB_URI;
  if (!uri) throw new Error('MONGODB_URI is not set.');
  const client = new MongoClient(uri);
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

async function connectSQLite() {
  const Database = require('better-sqlite3');
  const path = require('path');
  const db = new Database(path.join(__dirname, '../..', 'exam_results.db'));
  db.prepare(`CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE,
    password TEXT NOT NULL,
    created_at TEXT DEFAULT (datetime('now'))
  )`).run();
  console.log('Using SQLite fallback database');
  return {
    findUserByEmail: (email) => {
      const row = db.prepare('SELECT * FROM users WHERE email = ? LIMIT 1').get(email);
      if (!row) return null;
      return { ...row, id: String(row.id), password: row.password };
    },
    findUserById: (id) => {
      const row = db.prepare('SELECT * FROM users WHERE id = ? LIMIT 1').get(Number(id));
      if (!row) return null;
      return { ...row, id: String(row.id) };
    },
    createUser: ({ name, email, password }) => {
      const info = db.prepare('INSERT INTO users (name, email, password) VALUES (?, ?, ?)').run(name, email, password);
      return { id: String(info.lastInsertRowid), name, email, password, created_at: new Date().toISOString() };
    },
    getAllUsers: () => {
      return db.prepare('SELECT id, password FROM users').all();
    },
  };
}

async function connectDb() {
  try {
    if (DB_TYPE === 'sqlite') {
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

connectDb();

module.exports = { connectDb, getDb };
