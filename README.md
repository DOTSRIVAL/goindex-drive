<div align="center">
  <img src="https://upload.wikimedia.org/wikipedia/commons/1/12/Google_Drive_icon_%282020%29.svg" width="80" alt="Google Drive Logo">
  <h1>Drive Base PRO 🚀</h1>
  <p><b>The Ultimate High-Speed Google Drive Proxy & Streaming Platform</b></p>
  <p><i>Bypass Google's Quota Limits. Stream 1080p Flawlessly. Protect Your Links.</i></p>
</div>

<hr>

## 🌟 What is Drive Base PRO?

Drive Base PRO is a completely rewritten, heavily optimized proxy engine for Google Drive. Originally inspired by GoIndex, this platform has been rebuilt from the ground up using **Asynchronous Python (aiohttp & FastAPI)** to act as a robust, high-performance streaming proxy.

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

Drive Base PRO is highly optimized for Free Cloud Hosting platforms like **Hugging Face Spaces**.

### Step 1: Create a PostgreSQL or MongoDB Database
To ensure your connected Google Drives are never lost when Hugging Face restarts the server, you need a free database.
1. Go to [Neon.tech](https://neon.tech/) and create a Free PostgreSQL database.
2. Copy the `DATABASE_URL` connection string.

### Step 2: Deploy to Hugging Face
1. Create a new **Docker Space** on Hugging Face.
2. Upload all the files from this repository.
3. Go to your Space **Settings -> Variables and secrets**.
4. Add a new Secret:
   - **Name:** `DATABASE_URL`
   - **Value:** *(Paste your NeonDB or MongoDB URL here)*

### Step 3: Add Your Google Drive
1. Open your deployed Drive Base PRO website.
2. Click the **Settings (⚙)** gear icon.
3. Go to the **☁ Drives** tab.
4. Add your Google Drive `Client ID`, `Client Secret`, and `Refresh Token`. (Generate these from Google Cloud Console).
5. Done! Your files will load instantly and the configuration is saved to your database permanently!

---

## 🔧 Pro Tips for Webmasters (Anime/Movie Sites)

- **Remote Uploading:** Do you use hosts like Vidmoly, Vidoza, or Streamtape? Just copy the "Direct Download Link" from Drive Base, paste it into the Remote Upload section of those sites, and watch it transfer a 500MB file in under 60 seconds!
- **Download Managers:** If you share the links directly to users, tell them to use **IDM (Internet Download Manager)** or **ADM (Mobile)**. Drive Base natively supports HTTP `Range` headers, allowing IDM to open 16 parallel connections and skyrocket download speeds up to 48MB/s!
- **Link Expiry:** Turn on Link Security in the settings and set it to 2 Hours. When you embed the `<video>` on your site, use the newly generated signed URL. It will automatically expire, preventing scrapers from stealing your server bandwidth.

---

## ⚖️ Disclaimer

This project is a powerful tool designed for personal backups and webmaster file management. Please ensure you comply with Google Drive's Terms of Service and applicable copyright laws when distributing content.

---
**Author:** DotSrival | Tamil | Cheems (Original UI)
