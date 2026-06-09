const statuses = ["saved", "applied", "interviewing", "offer", "rejected"];
const statusLabels = {
  saved: "Saved",
  applied: "Applied",
  interviewing: "Interviewing",
  offer: "Offer",
  rejected: "Rejected",
};

let token = localStorage.getItem("jobAssistantToken") || "";
let currentUser = null;
let applications = [];

const authView = document.getElementById("authView");
const dashboardView = document.getElementById("dashboardView");
const userLabel = document.getElementById("userLabel");
const logoutBtn = document.getElementById("logoutBtn");

function toast(message) {
  const element = document.getElementById("toast");
  element.textContent = message;
  element.classList.add("show");
  setTimeout(() => element.classList.remove("show"), 2600);
}

async function api(path, options = {}) {
  const headers = { "Content-Type": "application/json", ...(options.headers || {}) };
  if (token) headers.Authorization = `Bearer ${token}`;
  const response = await fetch(path, { ...options, headers });
  if (response.status === 204) return null;
  const data = await response.json();
  if (!response.ok) {
    throw new Error(data.error || "API request failed");
  }
  return data;
}

function formData(form) {
  const data = {};
  new FormData(form).forEach((value, key) => {
    data[key] = value;
  });
  return data;
}

function setSession(nextToken, user) {
  token = nextToken;
  currentUser = user;
  localStorage.setItem("jobAssistantToken", token);
  userLabel.textContent = `${user.name} (${user.email})`;
  logoutBtn.classList.remove("hidden");
  authView.classList.add("hidden");
  dashboardView.classList.remove("hidden");
}

function clearSession() {
  token = "";
  currentUser = null;
  localStorage.removeItem("jobAssistantToken");
  userLabel.textContent = "Not signed in";
  logoutBtn.classList.add("hidden");
  authView.classList.remove("hidden");
  dashboardView.classList.add("hidden");
}

async function bootstrap() {
  if (!token) return clearSession();
  try {
    const data = await api("/api/me");
    setSession(token, data.user);
    await refreshDashboard();
  } catch {
    clearSession();
  }
}

async function refreshDashboard() {
  const [applicationData, analyticsData, recruiterData, reminderData] = await Promise.all([
    api("/api/applications"),
    api("/api/analytics"),
    api("/api/recruiters"),
    api("/api/reminders"),
  ]);
  applications = applicationData.applications;
  renderStats(analyticsData.analytics);
  renderAnalytics(analyticsData.analytics);
  renderKanban(applications);
  renderRecruiters(recruiterData.recruiters);
  renderReminders(reminderData.reminders);
}

function renderStats(analytics) {
  const stats = [
    ["Total", analytics.total_applications],
    ["Avg ATS", `${analytics.average_ats_score}%`],
    ["Response", `${analytics.response_rate}%`],
    ["Interview", `${analytics.interview_conversion_rate}%`],
    ["Offer", `${analytics.offer_conversion_rate}%`],
  ];
  document.getElementById("stats").innerHTML = stats
    .map(([label, value]) => `<div class="stat"><span>${label}</span><strong>${value}</strong></div>`)
    .join("");
}

function renderAnalytics(analytics) {
  const statusRows = Object.entries(analytics.by_status)
    .map(([status, count]) => `<div class="list-item">${statusLabels[status] || status}: ${count}</div>`)
    .join("");
  const versions = Object.entries(analytics.resume_versions)
    .map(([version, data]) => `<div class="list-item">${version}: ${data.count} apps, ${data.interviews} interviews, ${data.offers} offers</div>`)
    .join("");
  document.getElementById("analytics").innerHTML = `
    <h3>Status Breakdown</h3>
    ${statusRows || "<p>No applications yet.</p>"}
    <h3>Resume Versions</h3>
    ${versions || "<p>No resume version data yet.</p>"}
  `;
}

function renderKanban(items) {
  const kanban = document.getElementById("kanban");
  kanban.innerHTML = statuses
    .map((status) => {
      const cards = items.filter((item) => item.status === status);
      return `
        <div class="column">
          <h3>${statusLabels[status]} <span>${cards.length}</span></h3>
          ${cards.map(renderApplicationCard).join("")}
        </div>
      `;
    })
    .join("");
  document.querySelectorAll("[data-status-select]").forEach((select) => {
    select.addEventListener("change", async (event) => {
      const id = event.target.dataset.statusSelect;
      await api(`/api/applications/${id}`, {
        method: "PATCH",
        body: JSON.stringify({ status: event.target.value, status_note: "Updated from dashboard" }),
      });
      toast("Status updated");
      await refreshDashboard();
    });
  });
}

function renderApplicationCard(item) {
  const scoreClass = item.optimized_ats_score >= 85 ? "good" : item.optimized_ats_score >= 70 ? "warn" : "bad";
  return `
    <article class="application">
      <strong>${escapeHtml(item.company)}</strong>
      <p>${escapeHtml(item.title || item.role)} | ${escapeHtml(item.location || "Location not set")}</p>
      <p><span class="pill ${scoreClass}">ATS ${item.optimized_ats_score || item.ats_score || 0}%</span></p>
      <p><a href="${escapeAttribute(item.url)}" target="_blank" rel="noreferrer">Open job</a></p>
      ${item.follow_up_at ? `<p>Follow up: ${escapeHtml(item.follow_up_at)}</p>` : ""}
      ${item.recruiter_name ? `<p>Recruiter: ${escapeHtml(item.recruiter_name)}</p>` : ""}
      <div class="status-row">
        <select data-status-select="${item.id}">
          ${statuses.map((status) => `<option value="${status}" ${status === item.status ? "selected" : ""}>${statusLabels[status]}</option>`).join("")}
        </select>
      </div>
    </article>
  `;
}

function renderRecruiters(items) {
  document.getElementById("recruiters").innerHTML = items
    .map((item) => `<div class="list-item"><strong>${escapeHtml(item.name)}</strong> ${escapeHtml(item.company || "")}<br>${escapeHtml(item.email || "")}</div>`)
    .join("") || "<p>No recruiters saved.</p>";
}

function renderReminders(items) {
  document.getElementById("reminders").innerHTML = items
    .map((item) => `<div class="list-item"><strong>${escapeHtml(item.title)}</strong><br>${escapeHtml(item.due_at)} ${item.company ? `| ${escapeHtml(item.company)}` : ""}</div>`)
    .join("") || "<p>No reminders saved.</p>";
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function escapeAttribute(value) {
  return escapeHtml(value).replaceAll("`", "&#096;");
}

document.getElementById("loginForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  try {
    const data = await api("/api/auth/login", {
      method: "POST",
      body: JSON.stringify(formData(event.target)),
    });
    setSession(data.token, data.user);
    await refreshDashboard();
    toast("Logged in");
  } catch (error) {
    toast(error.message);
  }
});

document.getElementById("registerForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  try {
    const data = await api("/api/auth/register", {
      method: "POST",
      body: JSON.stringify(formData(event.target)),
    });
    setSession(data.token, data.user);
    await refreshDashboard();
    toast("Account created");
  } catch (error) {
    toast(error.message);
  }
});

logoutBtn.addEventListener("click", async () => {
  try {
    await api("/api/auth/logout", { method: "POST" });
  } catch {
    // Session cleanup should still happen locally.
  }
  clearSession();
});

document.getElementById("applicationForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  const data = formData(event.target);
  data.ats_score = Number(data.optimized_ats_score || 0);
  data.original_ats_score = Number(data.original_ats_score || 0);
  data.optimized_ats_score = Number(data.optimized_ats_score || 0);
  try {
    await api("/api/applications", { method: "POST", body: JSON.stringify(data) });
    event.target.reset();
    toast("Application saved");
    await refreshDashboard();
  } catch (error) {
    toast(error.message);
  }
});

document.getElementById("recruiterForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  try {
    await api("/api/recruiters", { method: "POST", body: JSON.stringify(formData(event.target)) });
    event.target.reset();
    toast("Recruiter saved");
    await refreshDashboard();
  } catch (error) {
    toast(error.message);
  }
});

document.getElementById("reminderForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  try {
    await api("/api/reminders", { method: "POST", body: JSON.stringify(formData(event.target)) });
    event.target.reset();
    toast("Reminder saved");
    await refreshDashboard();
  } catch (error) {
    toast(error.message);
  }
});

document.getElementById("atsForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  try {
    const result = await api("/api/ats/analyze", {
      method: "POST",
      body: JSON.stringify(formData(event.target)),
    });
    document.getElementById("atsOutput").textContent = JSON.stringify(result.analysis, null, 2);
  } catch (error) {
    toast(error.message);
  }
});

document.getElementById("interviewForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  try {
    const result = await api("/api/interview/questions", {
      method: "POST",
      body: JSON.stringify(formData(event.target)),
    });
    const sections = Object.entries(result.questions)
      .map(([label, questions]) => `
        <h3>${escapeHtml(label.replaceAll("_", " "))}</h3>
        <ol>${questions.map((question) => `<li>${escapeHtml(question)}</li>`).join("")}</ol>
      `)
      .join("");
    document.getElementById("interviewOutput").innerHTML = sections;
  } catch (error) {
    toast(error.message);
  }
});

document.getElementById("evaluateForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  try {
    const result = await api("/api/interview/evaluate", {
      method: "POST",
      body: JSON.stringify(formData(event.target)),
    });
    document.getElementById("evaluationOutput").textContent = JSON.stringify(result.evaluation, null, 2);
  } catch (error) {
    toast(error.message);
  }
});

bootstrap();
