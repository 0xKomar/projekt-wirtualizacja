// Ask the backend if it's up and can reach the database.
async function checkHealth() {
  const status = document.getElementById("status");
  const response = document.getElementById("response");

  try {
    // Give up after 5 s, so a dead backend shows up quickly.
    const res = await fetch("/api/health", { cache: "no-store", signal: AbortSignal.timeout(5000) });
    const data = await res.json();
    status.textContent = `Backend: ${data.status}, database: ${data.database}`;
    status.className = res.ok ? "ok" : "error";
    response.textContent = JSON.stringify(data, null, 2);
  } catch {
    // Timeout or no JSON at all: nginx couldn't reach the backend.
    status.textContent = "Backend unreachable";
    status.className = "error";
    response.textContent = "";
  }

  document.getElementById("checked").textContent = `Last check: ${new Date().toLocaleTimeString()}`;
}

checkHealth();
setInterval(checkHealth, 10000);
