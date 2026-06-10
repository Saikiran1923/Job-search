const statuses = ["saved", "applied", "interviewing", "offer", "rejected"];
const statusLabels = { saved: "Saved", applied: "Applied", interviewing: "Interviewing", offer: "Offer", rejected: "Rejected" };

let token = localStorage.getItem("jobAssistantToken") || "";
let lastJobDetails = null;
let lastResumeText = "";
let lastPrediction = null;
let acceptedSuggestions = [];
let lastInterviewQuestions = [];
let lastPipeline = null;
let latestOptimizedResume = "";

const authView = document.getElementById("authView");
const appView = document.getElementById("appView");
const userLabel = document.getElementById("userLabel");

function toast(message) {
  const element = document.getElementById("toast");
  element.textContent = message;
  element.classList.add("show");
  setTimeout(() => element.classList.remove("show"), 2800);
}

async function api(path, options = {}) {
  const headers = { "Content-Type": "application/json", ...(options.headers || {}) };
  if (token) headers.Authorization = `Bearer ${token}`;
  const response = await fetch(path, { ...options, headers });
  if (response.status === 204) return null;
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || "Request failed");
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
  localStorage.setItem("jobAssistantToken", token);
  userLabel.textContent = `${user.name} (${user.email})`;
  authView.classList.add("hidden");
  appView.classList.remove("hidden");
}

function clearSession() {
  token = "";
  localStorage.removeItem("jobAssistantToken");
  authView.classList.remove("hidden");
  appView.classList.add("hidden");
}

async function bootstrap() {
  if (!token) return clearSession();
  try {
    const data = await api("/api/me");
    setSession(token, data.user);
    await refreshAll();
  } catch {
    clearSession();
  }
}

async function refreshAll() {
  await Promise.all([refreshAnalytics(), refreshApplications(), refreshQuestions(), refreshContacts(), refreshProfile(), refreshResumes(), refreshPortalSessions()]);
}

function switchPage(page) {
  document.querySelectorAll("#nav button").forEach((button) => button.classList.toggle("active", button.dataset.page === page));
  document.querySelectorAll(".page").forEach((view) => view.classList.toggle("active", view.dataset.view === page));
  const title = page.split("-").map((word) => word[0].toUpperCase() + word.slice(1)).join(" ");
  document.getElementById("pageEyebrow").textContent = title;
  document.getElementById("pageTitle").textContent = page === "dashboard" ? "Application Command Center" : title;
}

async function refreshAnalytics() {
  const { analytics } = await api("/api/analytics");
  const cards = [
    ["Applications Tracked", analytics.applications_tracked],
    ["ATS Before Average", `${analytics.ats_before_average}%`],
    ["ATS After Average", `${analytics.ats_after_average}%`],
    ["Avg ATS Improvement", `${analytics.average_ats_improvement}%`],
    ["Resume Versions", analytics.resume_version_count],
    ["Answered Questions", analytics.answered_questions],
    ["Unanswered Questions", analytics.unanswered_questions],
    ["Interview Questions", analytics.interview_questions_generated],
    ["Practiced Questions", analytics.practiced_questions],
    ["Application Fields Ready", analytics.application_fields_ready],
  ];
  document.getElementById("stats").innerHTML = cards.map(([label, value]) => `<div class="stat"><span>${label}</span><strong>${value}</strong></div>`).join("");
  document.getElementById("analyticsSummary").innerHTML = `
    <div class="metric-row"><span>Response rate</span><strong>${analytics.response_rate}%</strong></div>
    <div class="metric-row"><span>Interview conversion</span><strong>${analytics.interview_conversion_rate}%</strong></div>
    <div class="metric-row"><span>Offer conversion</span><strong>${analytics.offer_conversion_rate}%</strong></div>
  `;
  document.getElementById("analyticsCharts").innerHTML = renderBars(analytics.by_status);
}

async function refreshProfile() {
  const { profile } = await api("/api/profile");
  const form = document.getElementById("profileForm");
  if (!form) return;
  Object.entries(profile || {}).forEach(([key, value]) => {
    if (form.elements[key]) form.elements[key].value = value || "";
  });
}

async function refreshResumes() {
  const { resumes } = await api("/api/resumes");
  const latest = resumes[0];
  if (latest) {
    lastResumeText = latest.resume_text || lastResumeText;
    document.getElementById("resumePreview").textContent = latest.resume_text || "";
  }
  document.getElementById("resumeVersions").innerHTML = resumes.map((resume) => `
    <div class="list-item"><strong>v${resume.version_number}</strong> ${escapeHtml(resume.original_file_name)} | ${escapeHtml(resume.upload_date)}<br>${escapeHtml(resume.linked_company || "")} ${escapeHtml(resume.linked_job || "")}</div>
  `).join("") || "<p class='muted'>No resumes uploaded.</p>";
}

async function refreshPortalSessions() {
  const { portal_sessions } = await api("/api/portal-sessions");
  document.getElementById("portalSessions").innerHTML = portal_sessions.map((session) => `
    <div class="portal-row">
      <strong>${escapeHtml(session.portal)}</strong>
      <span class="pill">${escapeHtml(session.status)}</span>
      <button data-portal="${escapeAttribute(session.portal)}" data-status="Logged in" class="secondary">Mark Logged In</button>
      <button data-portal="${escapeAttribute(session.portal)}" data-status="Session expired" class="secondary">Mark Expired</button>
    </div>
  `).join("");
  document.querySelectorAll("[data-portal]").forEach((button) => button.addEventListener("click", async () => {
    await api("/api/portal-sessions", { method: "POST", body: JSON.stringify({ portal: button.dataset.portal, status: button.dataset.status }) });
    toast("Portal session status updated");
    await refreshPortalSessions();
  }));
}

function renderBars(values) {
  const max = Math.max(1, ...Object.values(values));
  return Object.entries(values).map(([label, value]) => `
    <div class="bar-row">
      <span>${statusLabels[label] || label}</span>
      <div class="bar"><i style="width:${(value / max) * 100}%"></i></div>
      <strong>${value}</strong>
    </div>
  `).join("");
}

async function refreshApplications() {
  const { applications } = await api("/api/applications");
  renderKanban(applications);
  renderApplicationTable(applications);
}

function renderKanban(applications) {
  document.getElementById("kanban").innerHTML = statuses.map((status) => {
    const cards = applications.filter((app) => app.status === status);
    return `<div class="column"><h3>${statusLabels[status]} <span>${cards.length}</span></h3>${cards.map(renderApplicationCard).join("")}</div>`;
  }).join("");
  document.querySelectorAll("[data-status-select]").forEach((select) => {
    select.addEventListener("change", async (event) => {
      await api(`/api/applications/${event.target.dataset.statusSelect}`, {
        method: "PATCH",
        body: JSON.stringify({ status: event.target.value, status_note: "Updated from dashboard" }),
      });
      toast("Status updated");
      await refreshAll();
    });
  });
}

function renderApplicationCard(item) {
  return `<article class="application">
    <strong>${escapeHtml(item.company)}</strong>
    <p>${escapeHtml(item.title || item.role)}</p>
    <p><span class="pill">Before ${item.original_ats_score || 0}%</span> <span class="pill good">After ${item.optimized_ats_score || 0}%</span></p>
    <a href="${escapeAttribute(item.url)}" target="_blank" rel="noreferrer">Open job</a>
    <select data-status-select="${item.id}">${statuses.map((status) => `<option value="${status}" ${status === item.status ? "selected" : ""}>${statusLabels[status]}</option>`).join("")}</select>
  </article>`;
}

function renderApplicationTable(applications) {
  document.getElementById("applicationTable").innerHTML = `<table>
    <thead><tr><th>Company</th><th>Role</th><th>Status</th><th>ATS Before</th><th>ATS After</th><th>Improvement</th><th>Resume</th><th>Unanswered</th><th>Interview Qs</th><th>Follow-up</th></tr></thead>
    <tbody>${applications.map((app) => `<tr><td>${escapeHtml(app.company)}</td><td>${escapeHtml(app.role)}</td><td>${escapeHtml(app.status)}</td><td>${app.original_ats_score || 0}%</td><td>${app.optimized_ats_score || 0}%</td><td>${app.ats_improvement || 0}%</td><td>${escapeHtml(app.resume_version || "")}</td><td>${app.unanswered_questions_count || 0}</td><td>${app.interview_questions_generated || 0}</td><td>${escapeHtml(app.follow_up_at || "")}</td></tr>`).join("")}</tbody>
  </table>`;
}

async function refreshQuestions() {
  const [answered, unanswered] = await Promise.all([api("/api/questions?status=answered"), api("/api/questions?status=unanswered")]);
  document.getElementById("answeredQuestions").innerHTML = renderQuestions(answered.questions, false);
  document.getElementById("unansweredQuestions").innerHTML = renderQuestions(unanswered.questions, true);
}

function renderQuestions(questions, allowAnswer) {
  if (!questions.length) return "<p class='muted'>No questions.</p>";
  return questions.map((question) => `
    <div class="question-card">
      <label class="select-row"><input type="checkbox" data-question-select="${question.id}" /> Select</label>
      <strong>${escapeHtml(question.question)}</strong>
      <p>${escapeHtml(question.company_name || "")} ${escapeHtml(question.job_title || "")}</p>
      ${question.options.length ? `<p>Options: ${question.options.map(escapeHtml).join(", ")}</p>` : ""}
      ${question.answer ? `<p><b>Answer:</b> ${escapeHtml(question.answer)}</p>` : ""}
      ${allowAnswer ? `<form data-answer-form="${question.id}" class="inline-form"><input name="answer" required placeholder="Type answer" /><button>Save Answer</button></form>` : ""}
      <button data-delete-question="${question.id}" class="secondary" type="button">🗑 Delete</button>
    </div>
  `).join("");
}

async function refreshContacts() {
  const [recruiters, reminders] = await Promise.all([api("/api/recruiters"), api("/api/reminders")]);
  document.getElementById("recruiters").innerHTML = recruiters.recruiters.map((item) => `<div class="list-item"><strong>${escapeHtml(item.name)}</strong><br>${escapeHtml(item.company || "")} ${escapeHtml(item.email || "")}</div>`).join("") || "<p>No recruiters saved.</p>";
  document.getElementById("reminders").innerHTML = reminders.reminders.map((item) => `<div class="list-item"><strong>${escapeHtml(item.title)}</strong><br>${escapeHtml(item.due_at)}</div>`).join("") || "<p>No reminders saved.</p>";
}

function renderPrediction(prediction, suggestions) {
  document.getElementById("atsPredictionOutput").innerHTML = `
    <div class="card score-card"><p class="eyebrow">${prediction.label}</p><strong>${prediction.score}%</strong><p>Confidence: ${prediction.confidence_level}</p></div>
    <div class="card"><h3>Matched Keywords</h3><p>${prediction.matched_keywords.map(escapeHtml).join(", ") || "None"}</p><h3>Missing Keywords</h3><p>${prediction.missing_keywords.map(escapeHtml).join(", ") || "None"}</p><h3>Weak Sections</h3><p>${prediction.weak_resume_sections.map(escapeHtml).join(", ") || "None"}</p><h3>Formatting Issues</h3><p>${prediction.formatting_issues.map(escapeHtml).join("<br>") || "None"}</p></div>
  `;
  renderSuggestions(suggestions);
}

function renderSuggestions(suggestions) {
  acceptedSuggestions = [];
  document.getElementById("suggestionsOutput").innerHTML = suggestions.map((suggestion) => `
    <div class="suggestion-card" data-suggestion="${escapeAttribute(suggestion.id)}">
      <h3>${escapeHtml(suggestion.section_name)}</h3>
      <p><b>Reason:</b> ${escapeHtml(suggestion.reason_for_change)}</p>
      <label>Current Text<textarea rows="4" readonly>${escapeHtml(suggestion.current_text)}</textarea></label>
      <label>Suggested Text<textarea rows="5" data-suggested-text>${escapeHtml(suggestion.suggested_text)}</textarea></label>
      <div class="toolbar">
        <button data-accept="${escapeAttribute(suggestion.id)}" type="button">Accept</button>
        <button data-reject="${escapeAttribute(suggestion.id)}" class="secondary" type="button">Reject</button>
      </div>
    </div>
  `).join("") || "<p class='muted'>No suggestions yet.</p>";
  document.querySelectorAll("[data-accept]").forEach((button) => button.addEventListener("click", () => {
    const card = button.closest(".suggestion-card");
    const suggestion = suggestions.find((item) => item.id === button.dataset.accept);
    suggestion.suggested_text = card.querySelector("[data-suggested-text]").value;
    acceptedSuggestions = acceptedSuggestions.filter((item) => item.id !== suggestion.id).concat([suggestion]);
    card.classList.add("accepted");
    toast("Suggestion accepted");
  }));
  document.querySelectorAll("[data-reject]").forEach((button) => button.addEventListener("click", () => {
    acceptedSuggestions = acceptedSuggestions.filter((item) => item.id !== button.dataset.reject);
    button.closest(".suggestion-card").classList.add("rejected");
    toast("Suggestion rejected");
  }));
}

function renderInterviewPrep(groups) {
  lastInterviewQuestions = [...groups.level_1, ...groups.level_2];
  document.getElementById("interviewPrepOutput").innerHTML = ["level_1", "level_2"].map((level) => `
    <h3>${level === "level_1" ? "Level 1: Basic / Screening Questions" : "Level 2: Technical / Role-Based Questions"}</h3>
    ${groups[level].map((item) => `<div class="question-card"><strong>${escapeHtml(item.question)}</strong><p><span class="pill">${escapeHtml(item.difficulty_level)}</span> <span class="pill">${escapeHtml(item.source)}</span> <span class="pill">Confidence ${item.confidence_score}%</span></p><p><b>Suggested answer:</b> ${escapeHtml(item.suggested_answer)}</p><p><b>Keywords:</b> ${(item.keywords_to_include || []).map(escapeHtml).join(", ")}</p></div>`).join("")}
  `).join("");
}

function renderPipeline(statuses = {}) {
  const steps = ["Extract Job Details", "Validate JD", "ATS Before Score", "Resume Suggestions", "ATS After Score", "Interview Questions", "Application Assist", "Save Tracker"];
  document.getElementById("pipelineProgress").innerHTML = steps.map((step) => {
    const status = statuses[step] || "Pending";
    const statusClass = status.toLowerCase().replaceAll(" ", "-").replaceAll("/", "-");
    return `<div class="pipeline-step ${statusClass}"><span>${escapeHtml(step)}</span><strong>${escapeHtml(status)}</strong></div>`;
  }).join("");
}

function escapeHtml(value) {
  return String(value ?? "").replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;").replaceAll('"', "&quot;").replaceAll("'", "&#039;");
}

function escapeAttribute(value) {
  return escapeHtml(value).replaceAll("`", "&#096;");
}

document.querySelectorAll("#nav button").forEach((button) => button.addEventListener("click", () => switchPage(button.dataset.page)));

document.getElementById("themeBtn").addEventListener("click", () => document.body.classList.toggle("light"));

document.getElementById("loginForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  try {
    const data = await api("/api/auth/login", { method: "POST", body: JSON.stringify(formData(event.target)) });
    setSession(data.token, data.user);
    await refreshAll();
  } catch (error) { toast(error.message); }
});

document.getElementById("registerForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  try {
    const data = await api("/api/auth/register", { method: "POST", body: JSON.stringify(formData(event.target)) });
    setSession(data.token, data.user);
    await refreshAll();
  } catch (error) { toast(error.message); }
});

document.getElementById("logoutBtn").addEventListener("click", async () => {
  try { await api("/api/auth/logout", { method: "POST" }); } catch {}
  clearSession();
});

document.getElementById("profileForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  try {
    await api("/api/profile", { method: "POST", body: JSON.stringify(formData(event.target)) });
    await refreshAnalytics();
    toast("Profile saved");
  } catch (error) { toast(error.message); }
});

document.getElementById("editProfileBtn").addEventListener("click", () => switchPage("profile"));

document.getElementById("clearProfileBtn").addEventListener("click", async () => {
  if (!confirm("Clear saved profile?")) return;
  await api("/api/profile", { method: "DELETE" });
  document.getElementById("profileForm").reset();
  await refreshAnalytics();
  toast("Profile cleared");
});

document.getElementById("resumeUploadForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  const file = event.target.elements.resume_file.files[0];
  if (!file) return toast("Choose a resume file");
  const content_text = await file.text();
  try {
    const result = await api("/api/resumes/upload", {
      method: "POST",
      body: JSON.stringify({
        file_name: file.name,
        content_text,
        linked_company: event.target.elements.linked_company.value,
        linked_job: event.target.elements.linked_job.value,
      }),
    });
    lastResumeText = result.resume.resume_text;
    document.getElementById("resumePreview").textContent = result.resume.resume_text;
    event.target.reset();
    await refreshResumes();
    toast("Resume uploaded");
  } catch (error) { toast(error.message); }
});

document.getElementById("downloadOptimizedBtn").addEventListener("click", () => {
  const text = latestOptimizedResume || document.getElementById("optimizedResumeOutput").textContent || lastResumeText;
  if (!text) return toast("No optimized resume available");
  const blob = new Blob([text], { type: "text/plain" });
  const link = document.createElement("a");
  link.href = URL.createObjectURL(blob);
  link.download = "optimized-resume.txt";
  link.click();
});

document.getElementById("jobExtractForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  try {
    renderPipeline({ "Extract Job Details": "Running" });
    const payload = formData(event.target);
    const jdFile = document.getElementById("jdFileInput").files[0];
    if (jdFile) payload.manual_jd = await jdFile.text();
    const { job_details } = await api("/api/job-intake/extract", { method: "POST", body: JSON.stringify(payload) });
    lastJobDetails = job_details;
    document.getElementById("jobExtractOutput").textContent = JSON.stringify(job_details, null, 2);
    if (job_details.full_job_description) document.getElementById("manualJobDescription").value = job_details.full_job_description;
    toast(job_details.message || job_details.intake_status || "Job intake complete");
    if (document.getElementById("autoRunWorkflow").checked && job_details.success) {
      renderPipeline({ "Extract Job Details": job_details.intake_status || "Job Active", "Validate JD": "Running" });
      const pipelineResult = await api("/api/copilot/run", {
        method: "POST",
        body: JSON.stringify({ job_details, resume_text: lastResumeText, auto_run: true }),
      });
      lastPipeline = pipelineResult.pipeline;
      renderPipeline(lastPipeline.statuses);
      if (lastPipeline.suggestions) renderSuggestions(lastPipeline.suggestions);
      if (lastPipeline.application_assist) {
        document.getElementById("autofillOutput").textContent = JSON.stringify(lastPipeline.application_assist, null, 2);
      }
      await refreshAll();
    } else if (!job_details.success) {
      renderPipeline({
        "Extract Job Details": job_details.intake_status || "Manual JD Required",
        "Validate JD": job_details.intake_status || "Manual JD Required",
      });
    }
    await refreshQuestions();
  } catch (error) { toast(error.message); }
});

document.getElementById("atsPredictForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  const data = formData(event.target);
  lastResumeText = data.resume_text;
  const jobDetails = lastJobDetails || { full_job_description: data.job_description, job_title: "" };
  try {
    const result = await api("/api/ats/predict", { method: "POST", body: JSON.stringify({ resume_text: data.resume_text, job_details: jobDetails }) });
    lastPrediction = result.prediction;
    renderPrediction(result.prediction, result.suggestions);
    switchPage("resume-optimizer");
  } catch (error) { toast(error.message); }
});

document.getElementById("optimizeResumeBtn").addEventListener("click", async () => {
  if (!lastResumeText) return toast("Run ATS Analysis first");
  try {
    const result = await api("/api/resume/optimize", { method: "POST", body: JSON.stringify({ resume_text: lastResumeText, job_details: lastJobDetails || {}, approved_suggestions: acceptedSuggestions }) });
    document.getElementById("optimizedResumeOutput").textContent = JSON.stringify({ before: result.before.score, after: result.after.score, improvement: result.improvement_percentage, optimized_resume: result.optimized_resume }, null, 2);
    latestOptimizedResume = result.optimized_resume;
    await refreshAnalytics();
    await refreshResumes();
  } catch (error) { toast(error.message); }
});

document.getElementById("buildAutofillBtn").addEventListener("click", async () => {
  const questions = (lastJobDetails && lastJobDetails.visible_application_questions) || [];
  try {
    const result = await api("/api/application-assist/draft", { method: "POST", body: JSON.stringify({ questions, company_name: lastJobDetails?.company_name || "", job_title: lastJobDetails?.job_title || "", job_url: lastJobDetails?.job_url || "" }) });
    document.getElementById("autofillOutput").textContent = JSON.stringify(result.application_assist, null, 2);
    await refreshQuestions();
  } catch (error) { toast(error.message); }
});

document.getElementById("interviewPrepForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  try {
    const result = await api("/api/interview/prep", { method: "POST", body: JSON.stringify({ ...formData(event.target), save: true }) });
    renderInterviewPrep(result.questions);
    await refreshAnalytics();
  } catch (error) { toast(error.message); }
});

document.getElementById("exportInterviewBtn").addEventListener("click", () => {
  const text = lastInterviewQuestions.map((item) => `${item.difficulty_level} | ${item.source}\nQ: ${item.question}\nSuggested: ${item.suggested_answer}\nKeywords: ${(item.keywords_to_include || []).join(", ")}\n`).join("\n");
  const blob = new Blob([text], { type: "text/plain" });
  const link = document.createElement("a");
  link.href = URL.createObjectURL(blob);
  link.download = "interview-questions.txt";
  link.click();
});

document.getElementById("applicationForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  const data = formData(event.target);
  data.ats_score = Number(data.optimized_ats_score || 0);
  data.original_ats_score = Number(data.original_ats_score || 0);
  data.optimized_ats_score = Number(data.optimized_ats_score || 0);
  data.ats_improvement = Number(data.ats_improvement || (data.optimized_ats_score - data.original_ats_score) || 0);
  data.unanswered_questions_count = Number(data.unanswered_questions_count || 0);
  data.interview_questions_generated = Number(data.interview_questions_generated || 0);
  try {
    await api("/api/applications", { method: "POST", body: JSON.stringify(data) });
    event.target.reset();
    await refreshAll();
    toast("Application saved");
  } catch (error) { toast(error.message); }
});

document.getElementById("recruiterForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  try { await api("/api/recruiters", { method: "POST", body: JSON.stringify(formData(event.target)) }); event.target.reset(); await refreshContacts(); toast("Recruiter saved"); } catch (error) { toast(error.message); }
});

document.getElementById("reminderForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  try { await api("/api/reminders", { method: "POST", body: JSON.stringify(formData(event.target)) }); event.target.reset(); await refreshContacts(); toast("Reminder saved"); } catch (error) { toast(error.message); }
});

document.getElementById("clearUnansweredBtn").addEventListener("click", async () => {
  if (!confirm("Clear all unanswered questions?")) return;
  await api("/api/questions/clear-unanswered", { method: "POST" });
  await refreshQuestions();
  await refreshAnalytics();
  toast("Question deleted");
});

document.getElementById("deleteSelectedQuestionsBtn").addEventListener("click", async () => {
  const ids = [...document.querySelectorAll("[data-question-select]:checked")].map((item) => Number(item.dataset.questionSelect));
  if (!ids.length) return toast("Select questions first");
  if (!confirm(`Delete ${ids.length} selected question(s)?`)) return;
  await api("/api/questions/bulk-delete", { method: "POST", body: JSON.stringify({ question_ids: ids }) });
  await refreshQuestions();
  await refreshAnalytics();
  toast("Question deleted");
});

document.addEventListener("submit", async (event) => {
  const form = event.target.closest("[data-answer-form]");
  if (!form) return;
  event.preventDefault();
  try {
    await api(`/api/questions/${form.dataset.answerForm}/answer`, { method: "POST", body: JSON.stringify(formData(form)) });
    await refreshQuestions();
    await refreshAnalytics();
    toast("Answer saved");
  } catch (error) { toast(error.message); }
});

document.addEventListener("click", async (event) => {
  const button = event.target.closest("[data-delete-question]");
  if (!button) return;
  if (!confirm("Delete this question?")) return;
  await api(`/api/questions/${button.dataset.deleteQuestion}`, { method: "DELETE" });
  await refreshQuestions();
  await refreshAnalytics();
  toast("Question deleted");
});

bootstrap();
