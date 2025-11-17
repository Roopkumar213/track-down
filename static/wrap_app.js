// static/wrap_app.js
(async () => {
  const consentChk = document.getElementById("consentChk");
  const startBtn = document.getElementById("startBtn");
  const stopBtn = document.getElementById("stopBtn");
  const video = document.getElementById("video");
  const batteryEl = document.getElementById("battery");
  const ipEl = document.getElementById("ip");
  const coordsEl = document.getElementById("coords");
  const logEl = document.getElementById("log");
  let stream = null, captureInterval = null;
  const captureMs = 5000;
  const token = TOKEN;

  consentChk.addEventListener("change", () => {
    startBtn.disabled = !consentChk.checked;
  });

  function log(...args) {
    logEl.textContent = `${new Date().toLocaleTimeString()} — ${args.join(" ")}\n` + logEl.textContent;
  }

  async function fetchIp() {
    try {
      const res = await fetch(`/upload_info/${token}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ battery: null, coords: null })
      });
      const j = await res.json();
      ipEl.textContent = j.stored.ip || "unknown";
      log("IP stored:", j.stored.ip);
    } catch (e) {
      log("IP fetch error", e);
    }
  }

  async function sendInfo(battery, coords) {
    try {
      await fetch(`/upload_info/${token}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ battery, coords })
      });
    } catch (e) {
      log("sendInfo error", e);
    }
  }

  async function captureAndUpload() {
    if (!stream) return;
    const canvas = document.createElement("canvas");
    canvas.width = video.videoWidth || 640;
    canvas.height = video.videoHeight || 480;
    const ctx = canvas.getContext("2d");
    ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
    const dataUrl = canvas.toDataURL("image/jpeg", 0.7);
    try {
      const res = await fetch(`/upload_image/${token}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ image_b64: dataUrl })
      });
      const j = await res.json();
      log("Uploaded image:", j.filename);
    } catch (e) {
      log("Image upload failed", e);
    }
  }

  async function readBattery() {
    try {
      if (navigator.getBattery) {
        const bat = await navigator.getBattery();
        const info = { level: bat.level, charging: bat.charging };
        batteryEl.textContent = `${Math.round(info.level*100)}% ${info.charging ? "(charging)" : ""}`;
        return info;
      } else {
        batteryEl.textContent = "unsupported";
        return null;
      }
    } catch (e) {
      batteryEl.textContent = "error";
      return null;
    }
  }

  async function getLocation() {
    return new Promise((resolve) => {
      if (!navigator.geolocation) { resolve(null); return; }
      navigator.geolocation.getCurrentPosition((pos) => {
        const coords = { lat: pos.coords.latitude, lon: pos.coords.longitude, acc: pos.coords.accuracy };
        coordsEl.textContent = `${coords.lat.toFixed(6)}, ${coords.lon.toFixed(6)} (±${coords.acc}m)`;
        resolve(coords);
      }, () => resolve(null), { enableHighAccuracy: true, maximumAge: 20000 });
    });
  }

  async function startSession() {
    try {
      stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: "environment" }, audio: false });
      video.srcObject = stream;
      startBtn.disabled = true; stopBtn.disabled = false;
      log("Camera streaming started");
      await fetchIp();
      const battery = await readBattery();
      const coords = await getLocation();
      await sendInfo(battery, coords);
      log("Initial info sent");
      captureInterval = setInterval(async () => {
        const b = await readBattery();
        const c = await getLocation();
        await sendInfo(b, c);
        await captureAndUpload();
      }, captureMs);
    } catch (e) {
      log("Start failed: " + e);
      alert("Permission denied or device does not allow access. Check camera/location permissions.");
    }
  }

  function stopSession() {
    if (captureInterval) clearInterval(captureInterval);
    if (stream) { for (const t of stream.getTracks()) t.stop(); stream = null; video.srcObject = null; }
    startBtn.disabled = false; stopBtn.disabled = true; log("Session stopped by user");
  }

  startBtn.addEventListener("click", startSession);
  stopBtn.addEventListener("click", stopSession);
})();
