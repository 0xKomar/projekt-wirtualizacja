// Ask the backend if it's up and can reach the database.
async function checkHealth() {
  const res = await fetch("/api/health");
  const data = await res.json();

  document.getElementById("status").textContent =
    `Backend: ${data.status}, database: ${data.database}`;
  document.getElementById("response").textContent = JSON.stringify(data, null, 2);
}

checkHealth();
setInterval(checkHealth, 10000);
