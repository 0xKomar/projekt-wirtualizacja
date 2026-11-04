// Ask the backend if it's up and can reach the database.
async function checkHealth() {
  const status = document.getElementById("status");
  const response = document.getElementById("response");

  try {
    const res = await fetch("/api/health");
    const data = await res.json();
    status.textContent = `Backend: ${data.status}, database: ${data.database}`;
    status.className = res.ok ? "ok" : "error";
    response.textContent = JSON.stringify(data, null, 2);
  } catch {
    // No JSON at all: nginx couldn't reach the backend.
    status.textContent = "Backend unreachable";
    status.className = "error";
    response.textContent = "";
  }
}

checkHealth();
setInterval(checkHealth, 10000);
