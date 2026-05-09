<div align="center">
  <img src="https://upload.wikimedia.org/wikipedia/commons/1/12/Google_Drive_icon_%282020%29.svg" width="80" alt="Google Drive Logo">
  <h1>Drive Base PRO 🚀</h1>
  <p><b>The Ultimate High-Speed Google Drive Proxy & Streaming Platform</b></p>
  <p><i>Bypass Google's Quota Limits. Stream 1080p Flawlessly. Protect Your Links.</i></p>
</div>

<p align="center">
  <b><a href="https://dotsrival-drivebasepro.hf.space">🔥 Click Here for Live Demo Preview 🔥</a></b>
</p>

<hr>

## 🌟 What is Drive Base PRO?

Drive Base PRO is a completely custom-built, heavily optimized proxy engine for Google Drive. Designed and engineered by **DOTSRIVAL**, this platform uses **Asynchronous Python (aiohttp & FastAPI)** to act as a robust, high-performance streaming proxy.

It is specifically designed for **Anime/Movie websites, File Hosts, and heavy downloaders** who need to bypass Google Drive's strict *"Download Quota Exceeded"* and *"Automated Bot"* errors. 

## ✨ Key Features

- 🚀 **Blazing Fast `aiohttp` Engine:** Pumps out speeds up to **72 Mbps (9MB/s)** for Server-to-Server transfers (like Remote Uploads to Vidoza, Filemoon, DoodStream, etc.).
- 🛡️ **Anti-Ban Proxy:** Fully proxies the file stream. Bypasses the strict Google API "Bot/Automated Queries" check. Your users will never see the Google Virus Scan warning again.
- 💾 **Database Persistence:** Add your Google Drives via the UI and they will save permanently to **PostgreSQL (NeonDB) or MongoDB**. Perfect for ephemeral platforms like Hugging Face Spaces.
- 📊 **Real-Time Analytics:** Built-in Live Traffic Monitor. Watch your data transfer (GBs) and Active Unique Users count tick up in real-time right from the Top Bar.
- 🔒 **Secure Expiring Links:** Stop link-stealers in their tracks! Enable HMAC-signed Link Expiration. Generate links that automatically expire after X hours.
- 🛑 **Global Traffic Controller:** Set a hard speed limit (e.g., 1.5 MB/s) per connection to save your server bandwidth and prevent abuse.
- 📱 **Pro UI Interface:** Modern, dark-mode, fully mobile-responsive interface with a tabbed Settings dashboard.
- 🎬 **In-Browser Player:** Stream 1080p media natively inside the browser without downloading!

---

## 📸 Screenshots

<p align="center">
  <i>Modern UI with real-time analytics pinned to the top header</i><br>
  <i>(Include your screenshots here)</i>
</p>

---

## ⚡ Deployment Guide (Hugging Face Spaces)

Drive Base PRO is highly optimized for Free Cloud Hosting platforms like **Hugging Face Spaces** using their Docker environment.

### Step 1: Create a PostgreSQL or MongoDB Database
To ensure your connected Google Drives are never lost when Hugging Face restarts the server, you need a free database.
1. Go to [Neon.tech](https://neon.tech/) and create a Free PostgreSQL database.
2. Copy the `DATABASE_URL` connection string.

### Step 2: Deploy to Hugging Face (Docker Setup)
1. Log in to [Hugging Face](https://huggingface.co/) and click **New Space**.
2. Give your space a name (e.g., `anime-drive-base`).
3. **CRITICAL STEP:** Under **Select the Space SDK**, choose **Docker**, then select **Blank**.
4. Set the Space hardware to `Free` and click **Create Space**.
5. Once created, go to the **Files** tab and click **Add file -> Upload files**. Upload all the files from this repository (most importantly `app.py`, `Dockerfile`, `requirements.txt`, and `preview.html`).
6. Hugging Face will automatically detect the `Dockerfile` and start building your proxy server.

### Step 3: Add Database Secrets
1. In your Hugging Face Space, click the **Settings** tab.
2. Scroll down to **Variables and secrets**.
3. Click **New secret**.
   - **Name:** `DATABASE_URL`
   - **Value:** *(Paste your NeonDB or MongoDB URL here)*
4. Click Save. The Space will restart and connect to your database.

### Step 4: Add Your Google Drive
1. Open your deployed Drive Base PRO website.
2. Click the **Settings (⚙)** gear icon.
3. Go to the **☁ Drives** tab.
4. Add your Google Drive `Client ID`, `Client Secret`, and `Refresh Token`. (Generate these from Google Cloud Console).
5. Done! Your files will load instantly and the configuration is saved to your database permanently!

---

## 🌍 Alternative Hosting Platforms

Hugging Face isn't the only place you can host Drive Base PRO. Since this app is fully Dockerized and uses Python FastAPI, you can host it anywhere that supports Docker or Python:

1. **Koyeb / Render / Railway (PaaS):**
   - Connect your GitHub repository to Koyeb, Render, or Railway.
   - They will automatically detect the `Dockerfile` and build the app.
   - Add your `DATABASE_URL` in their Environment Variables section.
   
2. **Private VPS (Contabo, Hetzner, AWS, DigitalOcean):**
   - Buy a cheap Linux VPS (e.g., Ubuntu).
   - Clone the repo: `git clone https://github.com/DOTSRIVAL/DriveBase-PRO.git`
   - Install Docker.
   - Run the app via Docker:
     ```bash
     docker build -t drivebase .
     docker run -d -p 7860:7860 -e DATABASE_URL="your_db_url_here" drivebase
     ```
   - *Advantage:* A private VPS gives you 100% Dedicated Bandwidth, meaning your speeds will be incredibly consistent without relying on free shared servers!

---

## 🔧 Pro Tips for Webmasters (Anime/Movie Sites)

- **Remote Uploading:** Do you use hosts like Vidmoly, Vidoza, or Streamtape? Just copy the "Direct Download Link" from Drive Base, paste it into the Remote Upload section of those sites, and watch it transfer a 500MB file in under 60 seconds!
- **Download Managers:** If you share the links directly to users, tell them to use **IDM (Internet Download Manager)** or **ADM (Mobile)**. Drive Base natively supports HTTP `Range` headers, allowing IDM to open 16 parallel connections and skyrocket download speeds up to 48MB/s!
- **Link Expiry:** Turn on Link Security in the settings and set it to 2 Hours. When you embed the `<video>` on your site, use the newly generated signed URL. It will automatically expire, preventing scrapers from stealing your server bandwidth.

---

## ⚖️ Disclaimer

This project is a powerful tool designed for personal backups and webmaster file management. Please ensure you comply with Google Drive's Terms of Service and applicable copyright laws when distributing content.

---
**Author:** DOTSRIVAL
