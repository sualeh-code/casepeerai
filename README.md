# CasePeer API Wrapper & Dashboard

A professional dashboard and API proxy for automating CasePeer interactions, featuring session persistence and Turso Cloud integration.

## 🚀 Deployment Guide

Follow these steps to upload your code to GitHub and host it on Render.

### 1. Upload to GitHub

Since you are using a new Git account (`salehai-web`), you need to configure your local identity first:

```powershell
# Set your identity
git config --global user.name "salehai-web"
git config --global user.email "your-email@example.com"

# Prepare the repository
git init
git add .
git commit -m "🚀 Initial deploy with Turso & Session Persistence"
git branch -M main

# Add remote (Update if needed)
git remote add origin https://github.com/salehai-web/casepeerai.git

# Push to GitHub (This will open a login window)
git push -u origin main
```

---

### 2. Deploy to Render

Once your code is on GitHub, follow these steps to host it on Render:

#### **A. Backend (FastAPI)**
1. Go to [Render Dashboard](https://dashboard.render.com/) and click **New +** > **Web Service**.
2. Connect your `casepeerai` repository.
3. Select **Docker** as the Runtime.
4. **Environment Variables**: Add the following in the Render settings:
   - `DATABASE_URL`: `libsql://casepeerai-salehai.aws-us-east-2.turso.io`
   - `TURSO_AUTH_TOKEN`: `eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9...` (Your full token)
   - `CASEPEER_USERNAME`: Your CasePeer email
   - `CASEPEER_PASSWORD`: Your CasePeer password
   - `GMAIL_EMAIL`: Your Gmail address
   - `GMAIL_APP_PASSWORD`: Your [Gmail App Password](https://myaccount.google.com/apppasswords)
   - `PLAYWRIGHT_HEADLESS`: `True`

#### **B. Frontend (React Dashboard)**
1. Click **New +** > **Static Site**.
2. Connect the same repository.
3. **Build Command**: `cd dashboard && npm install && npm run build`
4. **Publish Directory**: `dashboard/dist`
5. **Environment Variables**:
   - `VITE_API_BASE_URL`: Your Render Backend URL (e.g., `https://casepeerai-backend.onrender.com`)

---

## 🛠️ Local Development

1. Install dependencies: `pip install -r requirements.txt`
2. Run migration if needed: `python migrate_to_turso.py`
3. Start Backend: `uvicorn caseapi:app --reload`
4. Start Frontend: `cd dashboard && npm run dev`

---

## 🔒 Session Persistence
The app automatically saves cookies to Turso. On next launch, it will attempt to:
1. Restore cookies from the database.
2. Skip Playwright login if the session is still valid.
3. Use the "Remember Me" option during standard login flow.
