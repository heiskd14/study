# 🛡️ NexAuth — Full-Stack Authentication System

A modern, production-ready authentication system with a **glassmorphism dark UI**, Express backend, bcrypt password hashing, and JWT sessions. Supports both **MongoDB** and **MySQL**.

---

## 📁 Project Structure

```
auth-app/
├── frontend/
│   ├── index.html       ← Single-page app (Login, Signup, Dashboard)
│   ├── style.css        ← Glassmorphism dark theme
│   └── app.js           ← Frontend logic, API calls, validation
│
├── backend/
│   ├── server.js        ← Express app entry point
│   ├── package.json
│   ├── .env.example     ← Copy to .env and fill in values
│   ├── config/
│   │   └── db.js        ← MongoDB + MySQL adapters
│   ├── routes/
│   │   └── auth.js      ← /api/auth/* routes
│   ├── controllers/
│   │   └── authController.js  ← register, login, getMe
│   └── middleware/
│       ├── auth.js      ← JWT verify middleware
│       └── validate.js  ← Input sanitization & validation
│
└── database/
    └── mysql_setup.sql  ← Run this once for MySQL
```

---

## ⚡ Quick Start

### Prerequisites
- **Node.js** v18+ ([nodejs.org](https://nodejs.org))
- **MongoDB** (local or [MongoDB Atlas](https://www.mongodb.com/cloud/atlas)) OR **MySQL**

---

### 1. Backend Setup

```bash
cd auth-app/backend

# Install dependencies
npm install

# Set up environment variables
cp .env.example .env
# → Open .env and fill in your values (JWT_SECRET, DB connection)
```

**Generate a secure JWT secret:**
```bash
node -e "require('crypto').randomBytes(64).toString('hex').then ? '' : console.log(require('crypto').randomBytes(64).toString('hex'))"
```

### 2. Database Setup

#### Option A — MongoDB (default)
1. Start MongoDB locally: `mongod` (or use MongoDB Atlas)
2. In `.env`, set:
   ```
   DB_TYPE=mongodb
   MONGODB_URI=mongodb://127.0.0.1:27017
   DB_NAME=nexauth
   ```
3. No further setup needed — the backend auto-creates the collection and indexes.

#### Option B — MySQL
1. Start MySQL and run:
   ```bash
   mysql -u root -p < database/mysql_setup.sql
   ```
2. In `.env`, set:
   ```
   DB_TYPE=mysql
   MYSQL_HOST=localhost
   MYSQL_USER=root
   MYSQL_PASSWORD=your_password
   MYSQL_DATABASE=nexauth
   ```

### 3. Start the Backend

```bash
# Development (auto-reload)
npm run dev

# Production
npm start
```

Backend runs at: **http://localhost:5000**

---

### 4. Frontend Setup

The frontend is plain HTML/CSS/JS — no build step needed.

**Option A — VS Code Live Server**
1. Open `frontend/index.html` in VS Code
2. Right-click → *Open with Live Server*
3. It opens at `http://127.0.0.1:5500`

**Option B — Any static server**
```bash
cd auth-app/frontend
npx serve .
# Opens at http://localhost:3000
```

> **Important:** The frontend talks to `http://localhost:5000` by default.
> If your backend port differs, update `API_BASE` at the top of `frontend/app.js`.

---

## 🔑 API Reference

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| `POST` | `/api/auth/register` | ❌ | Create new account |
| `POST` | `/api/auth/login` | ❌ | Login and get JWT |
| `GET`  | `/api/auth/me` | ✅ Bearer | Get current user info |
| `GET`  | `/api/health` | ❌ | Server health check |

### Register — `POST /api/auth/register`
```json
// Request body
{
  "name": "Jane Doe",
  "email": "jane@gmail.com",
  "password": "SecurePass@123"
}

// Success response (201)
{
  "success": true,
  "token": "eyJ...",
  "user": { "id": "...", "name": "Jane Doe", "email": "jane@gmail.com", "created_at": "..." }
}

// Error (409 — duplicate email)
{ "success": false, "message": "That Gmail address is already registered." }

// Error (409 — duplicate password)
{ "success": false, "message": "That password is already in use." }
```

### Login — `POST /api/auth/login`
```json
// Request body
{
  "email": "jane@gmail.com",
  "password": "SecurePass@123",
  "remember": false
}

// Success (200)
{ "success": true, "token": "eyJ...", "user": { ... } }

// Error (401)
{ "success": false, "message": "Invalid email or password." }
```

### Protected Route — `GET /api/auth/me`
```
Authorization: Bearer <your_jwt_token>
```

---

## 🔒 Security Features

| Feature | Implementation |
|---------|---------------|
| Password hashing | bcrypt (12 salt rounds) |
| Sessions | JWT (7-day / 30-day with "remember me") |
| Rate limiting | 20 auth requests / 15 min per IP |
| Input sanitization | Custom middleware (strips `<>'"` etc.) |
| SQL injection prevention | Parameterized queries (MySQL) / MongoDB driver |
| Large payload protection | `express.json({ limit: '10kb' })` |
| Security headers | `helmet` middleware |
| CORS whitelist | Configurable via `ALLOWED_ORIGINS` |
| Duplicate password | bcrypt compare against all existing hashes |

---

## 🎨 UI Features

- **Glassmorphism dark theme** with animated gradient orbs
- **Real-time validation** with animated error/success indicators
- **Password strength meter** (4-level: weak → strong)
- **Password visibility toggle**
- **Toast notifications** (success / error / info / warning)
- **Loading spinner** during API calls
- **Forgot Password modal**
- **Dashboard** with profile, security status, session info, quick actions
- **Session persistence** via `localStorage`
- **Fully responsive** — mobile-first

---

## 🚀 Deployment

### Backend — Railway / Render / Fly.io
1. Push `backend/` to a GitHub repo
2. Connect to Railway/Render and deploy
3. Add environment variables from `.env`
4. Note the deployed URL (e.g. `https://nexauth.railway.app`)

### Frontend — Vercel / Netlify / GitHub Pages
1. Update `API_BASE` in `app.js` to your deployed backend URL
2. Push `frontend/` to GitHub
3. Import into Vercel/Netlify and deploy

### MongoDB Atlas (Cloud DB)
1. Create free cluster at [mongodb.com/cloud/atlas](https://www.mongodb.com/cloud/atlas)
2. Whitelist your server IP
3. Get connection string and set `MONGODB_URI` in production env vars

---

## 🛠️ Troubleshooting

| Problem | Fix |
|---------|-----|
| `Cannot reach server` | Backend not running — run `npm run dev` |
| `Not allowed by CORS` | Add your frontend URL to `ALLOWED_ORIGINS` in `.env` |
| `Database connection failed` | Check `MONGODB_URI` or MySQL credentials |
| JWT errors | Make sure `JWT_SECRET` is set and consistent |
| `Too many requests` | Wait 15 min or restart server in dev |

---

## 📄 License

MIT — free to use and modify.
