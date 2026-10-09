# Video Library By Telegram BotFather

This is a Video Library application utilizing a Telegram Bot (via BotFather), a FastAPI backend, and an HTML/JS frontend. It uses PostgreSQL (Neon Cloud) for the database and Google Gemini API for AI-powered chat features.

## Project Structure

The project is divided into two main parts:
- `backend/`: FastAPI application.
- `frontend/`: HTML, CSS, and JS files for the UI.

## Setup Instructions

### 1. Backend Setup

1. **Navigate to the backend directory:**
   ```bash
   cd backend
   ```

2. **Install requirements:**
   Make sure you have Python installed, then run:
   ```bash
   pip install -r requirements.txt
   ```

3. **Environment Variables Configuration:**
   Create a `.env` file in the `backend/` directory with the following variables:

   ```env
   # Neon Cloud PostgreSQL Database URL
   DATABASE_URL=postgresql://<user>:<password>@<host>/<dbname>?sslmode=require

   # Telegram Bot Credentials (Get from BotFather)
   TELEGRAM_BOT_TOKEN=your_bot_token_here
   TELEGRAM_CHANNEL_ID=your_channel_id_here

   # Admin Authentication Settings
   ADMIN_EMAIL=admin@example.com
   ADMIN_PASSWORD=admin123

   # Security Secrets
   SECRET_KEY=your_secret_key_here
   ALGORITHM=HS256
   ACCESS_TOKEN_EXPIRE_MINUTES=1440

   # Server & CORS Configuration
   CORS_ORIGINS=http://localhost:5173,http://localhost:3000,http://127.0.0.1:5173,http://localhost:8080,http://127.0.0.1:8080,null

   # Telegram Reverse Proxy (Optional Cloudflare Worker if needed)
   TELEGRAM_BASE_URL=https://api.telegram.org

   # Google Gemini API Key
   GEMINI_API_KEY=your_gemini_api_key_here
   ```

4. **Run the backend server:**
   ```bash
   uvicorn app.main:app --reload
   ```

### 2. Frontend Setup

1. Simply open the `frontend/index.html` file in your preferred web browser, or serve it using a local HTTP server like Live Server (VS Code extension) or Python's `http.server`.

   ```bash
   cd frontend
   python -m http.server 8080
   ```

2. Access the frontend at `http://localhost:8080`.
