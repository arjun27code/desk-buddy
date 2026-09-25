const buddy = document.getElementById("buddy");
const speechBubble = document.getElementById("speechBubble");
const moodLabel = document.getElementById("moodLabel");
const serverStatus = document.getElementById("serverStatus");
const weatherTemp = document.getElementById("weatherTemp");
const weatherText = document.getElementById("weatherText");
const weatherIcon = document.getElementById("weatherIcon");
const batteryValue = document.getElementById("batteryValue");
const batteryText = document.getElementById("batteryText");
const clockValue = document.getElementById("clockValue");
const dateValue = document.getElementById("dateValue");
const weatherRefresh = document.getElementById("weatherRefresh");

const moodClasses = ["sleepy", "excited", "love", "surprised", "focused"];
let moodTimer = null;
let lastWeather = null;

const lines = {
  curious: [
    "I am watching the desk. Very serious work.",
    "Tiny screen. Large responsibilities.",
    "I blink professionally.",
    "Desk status: suspiciously calm."
  ],
  excited: [
    "Energy level upgraded.",
    "I have exactly one job and I am overqualified for it.",
    "Boop received. Morale improved."
  ],
  love: [
    "Acceptable human interaction detected.",
    "You may boop again. For testing purposes."
  ],
  sleepy: [
    "Entering low-power cuteness mode.",
    "Wake me if the desk does something interesting."
  ],
  surprised: [
    "That was not in the tiny robot handbook.",
    "Unexpected event detected."
  ],
  focused: [
    "Focus mode. I am pretending to understand your schedule.",
    "Concentration face activated."
  ]
};

const weatherCodes = {
  0: ["Clear", "☀"],
  1: ["Mostly clear", "🌤"],
  2: ["Partly cloudy", "⛅"],
  3: ["Cloudy", "☁"],
  45: ["Foggy", "🌫"],
  48: ["Foggy", "🌫"],
  51: ["Light drizzle", "🌦"],
  53: ["Drizzle", "🌦"],
  55: ["Heavy drizzle", "🌧"],
  61: ["Light rain", "🌦"],
  63: ["Rain", "🌧"],
  65: ["Heavy rain", "🌧"],
  71: ["Light snow", "🌨"],
  73: ["Snow", "🌨"],
  75: ["Heavy snow", "❄"],
  80: ["Rain showers", "🌦"],
  81: ["Rain showers", "🌧"],
  82: ["Heavy showers", "⛈"],
  95: ["Thunderstorm", "⛈"],
  96: ["Storm with hail", "⛈"],
  99: ["Storm with hail", "⛈"]
};

function randomItem(items) {
  return items[Math.floor(Math.random() * items.length)];
}

function setSpeech(text) {
  speechBubble.textContent = text;
}

function setMood(mood, duration = 2800) {
  moodClasses.forEach((name) => buddy.classList.remove(name));

  if (mood !== "curious") {
    buddy.classList.add(mood);
  }

  moodLabel.textContent = "Mood: " + mood;

  if (moodTimer) {
    clearTimeout(moodTimer);
  }

  if (duration > 0 && mood !== "curious") {
    moodTimer = setTimeout(() => {
      moodClasses.forEach((name) => buddy.classList.remove(name));
      moodLabel.textContent = "Mood: curious";
    }, duration);
  }
}

function react(mood, customLine) {
  setMood(mood);
  setSpeech(customLine || randomItem(lines[mood] || lines.curious));
}

function blink() {
  if (buddy.classList.contains("sleepy")) return;

  buddy.classList.add("blink");
  setTimeout(() => buddy.classList.remove("blink"), 145);
}

function scheduleBlink() {
  const delay = 2200 + Math.random() * 4300;

  setTimeout(() => {
    blink();

    if (Math.random() > 0.82) {
      setTimeout(blink, 240);
    }

    scheduleBlink();
  }, delay);
}

function trackEyes(clientX, clientY) {
  if (buddy.classList.contains("sleepy")) return;

  const rect = buddy.getBoundingClientRect();
  const centerX = rect.left + rect.width / 2;
  const centerY = rect.top + rect.height / 2;

  const dx = Math.max(-1, Math.min(1, (clientX - centerX) / (rect.width * 0.55)));
  const dy = Math.max(-1, Math.min(1, (clientY - centerY) / (rect.height * 0.55)));

  document.querySelectorAll(".pupil").forEach((pupil) => {
    pupil.style.transform = "translate(" + dx * 12 + "px, " + dy * 9 + "px)";
  });
}

function updateClock() {
  const now = new Date();

  clockValue.textContent = new Intl.DateTimeFormat(undefined, {
    hour: "2-digit",
    minute: "2-digit"
  }).format(now);

  dateValue.textContent = new Intl.DateTimeFormat(undefined, {
    weekday: "short",
    day: "numeric",
    month: "short"
  }).format(now);
}

async function checkServer() {
  try {
    const response = await fetch("/api/health", { cache: "no-store" });

    if (!response.ok) {
      throw new Error("Server not ready");
    }

    serverStatus.classList.add("online");
    serverStatus.querySelector("span:last-child").textContent = "Online";
  } catch (error) {
    serverStatus.classList.remove("online");
    serverStatus.querySelector("span:last-child").textContent = "Offline";
  }
}

async function loadBattery() {
  try {
    const response = await fetch("/api/battery", { cache: "no-store" });
    const data = await response.json();

    if (!data.available) {
      batteryValue.textContent = "Optional";
      batteryText.textContent = "Install Termux:API for phone battery";
      return;
    }

    batteryValue.textContent = String(data.percentage) + "%";

    const details = [];
    if (data.status) details.push(String(data.status).toLowerCase());
    if (data.temperature !== undefined) details.push(String(data.temperature) + "°C");

    batteryText.textContent = details.join(" · ") || "Battery connected";

    if (Number(data.percentage) <= 15) {
      react("focused", "Battery is low. Even tiny robots understand chargers.");
    }
  } catch (error) {
    batteryValue.textContent = "Unavailable";
    batteryText.textContent = "Battery check failed";
  }
}

function weatherMood(code, temp) {
  if ([95, 96, 99].includes(code)) return "surprised";
  if ([61, 63, 65, 80, 81, 82].includes(code)) return "focused";
  if (temp >= 34) return "sleepy";
  if ([0, 1].includes(code)) return "excited";
  return "curious";
}

async function fetchWeatherForPosition(position) {
  const lat = position.coords.latitude;
  const lon = position.coords.longitude;

  weatherTemp.textContent = "Checking...";
  weatherText.textContent = "Asking the sky";

  try {
    const response = await fetch(
      "/api/weather?lat=" + encodeURIComponent(lat) + "&lon=" + encodeURIComponent(lon),
      { cache: "no-store" }
    );

    const data = await response.json();

    if (!response.ok) {
      throw new Error(data.error || "Weather failed");
    }

    const current = data.current || {};
    const code = Number(current.weather_code);
    const temp = Number(current.temperature_2m);
    const apparent = Number(current.apparent_temperature);
    const description = weatherCodes[code] || ["Weather", "◌"];

    lastWeather = {
      code,
      temp,
      apparent,
      description: description[0]
    };

    weatherIcon.textContent = description[1];
    weatherTemp.textContent = Number.isFinite(temp) ? Math.round(temp) + "°C" : "Weather";
    weatherText.textContent =
      description[0] +
      (Number.isFinite(apparent) ? " · feels " + Math.round(apparent) + "°C" : "");

    const mood = weatherMood(code, temp);
    if (mood !== "curious") {
      setMood(mood, 2200);
    }
  } catch (error) {
    weatherIcon.textContent = "◌";
    weatherTemp.textContent = "Weather unavailable";
    weatherText.textContent = "Internet or weather service failed";
  }
}

function loadWeather() {
  if (!("geolocation" in navigator)) {
    weatherTemp.textContent = "No location support";
    weatherText.textContent = "Your browser cannot provide location";
    return;
  }

  weatherTemp.textContent = "Location...";
  weatherText.textContent = "Allow location for local weather";

  navigator.geolocation.getCurrentPosition(
    fetchWeatherForPosition,
    () => {
      weatherIcon.textContent = "⌖";
      weatherTemp.textContent = "Location needed";
      weatherText.textContent = "Allow location permission and refresh";
      react("focused", "I need location permission before I can interrogate the weather.");
    },
    {
      enableHighAccuracy: false,
      timeout: 10000,
      maximumAge: 10 * 60 * 1000
    }
  );
}

function speak(text) {
  if (!("speechSynthesis" in window)) {
    react("surprised", "This browser refuses to give me a voice. Rude.");
    return;
  }

  window.speechSynthesis.cancel();

  const utterance = new SpeechSynthesisUtterance(text);
  utterance.rate = 1.03;
  utterance.pitch = 1.2;

  window.speechSynthesis.speak(utterance);
}

async function toggleFullscreen() {
  try {
    if (!document.fullscreenElement) {
      await document.documentElement.requestFullscreen();
    } else {
      await document.exitFullscreen();
    }
  } catch (error) {
    react("surprised", "Full screen was blocked by the browser.");
  }
}

document.addEventListener("pointermove", (event) => {
  trackEyes(event.clientX, event.clientY);
});

document.addEventListener(
  "touchmove",
  (event) => {
    const touch = event.touches[0];

    if (touch) {
      trackEyes(touch.clientX, touch.clientY);
    }
  },
  { passive: true }
);

buddy.addEventListener("click", () => {
  const moods = ["excited", "love", "surprised"];

  react(randomItem(moods));

  if (navigator.vibrate) {
    navigator.vibrate(35);
  }
});

weatherRefresh.addEventListener("click", loadWeather);

document.querySelector(".controls").addEventListener("click", (event) => {
  const button = event.target.closest("button[data-action]");

  if (!button) return;

  const action = button.dataset.action;

  if (action === "boop") {
    buddy.click();
  } else if (action === "cheer") {
    react("excited", "You are still here. Productivity has not defeated you yet.");
  } else if (action === "sleep") {
    setMood("sleepy", 6500);
    setSpeech(randomItem(lines.sleepy));
  } else if (action === "talk") {
    const text = lastWeather
      ? "It is " + Math.round(lastWeather.temp) + " degrees. " + lastWeather.description + "."
      : randomItem(lines.curious);

    setMood("love", 2200);
    setSpeech(text);
    speak(text);
  } else if (action === "fullscreen") {
    toggleFullscreen();
  }
});

updateClock();
setInterval(updateClock, 1000);

scheduleBlink();
checkServer();
loadBattery();
loadWeather();

setInterval(checkServer, 30000);
setInterval(loadBattery, 60000);
