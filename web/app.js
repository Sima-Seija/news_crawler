const api = {
  articles: "/api/articles",
  status: "/api/status",
  control: "/api/control",
  edit: "/api/article",
};

const crawlerStatus = document.getElementById("crawlerStatus");
const articleCount = document.getElementById("articleCount");
const lastUpdated = document.getElementById("lastUpdated");
const sourceCounts = document.getElementById("sourceCounts");
const articleTableBody = document.getElementById("articleTableBody");
const startBtn = document.getElementById("startBtn");
const stopBtn = document.getElementById("stopBtn");
const refreshBtn = document.getElementById("refreshBtn");
const reloadArticles = document.getElementById("reloadArticles");
const editorForm = document.getElementById("editorForm");
const clearEditor = document.getElementById("clearEditor");

const editIndex = document.getElementById("editIndex");
const editSource = document.getElementById("editSource");
const editTitle = document.getElementById("editTitle");
const editPublishedAt = document.getElementById("editPublishedAt");
const editUrl = document.getElementById("editUrl");
const editContent = document.getElementById("editContent");

let currentArticles = [];

async function fetchJson(url, opts = {}) {
  const res = await fetch(url, opts);
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`${res.status} ${res.statusText}: ${text}`);
  }
  return res.json();
}

function renderStatus(data) {
  crawlerStatus.textContent = data.running ? "執行中" : "已停止";
  crawlerStatus.style.color = data.running ? "#059669" : "#dc2626";
  articleCount.textContent = data.article_count;
  lastUpdated.textContent = data.last_updated || "尚未產生";

  const items = Object.entries(data.source_counts)
    .map(([key, value]) => `<div>${key}: ${value} 筆</div>`)
    .join("");
  sourceCounts.innerHTML = items || "尚無來源資料";
}

function renderArticles(articles) {
  currentArticles = articles;
  articleTableBody.innerHTML = "";
  articles.forEach((article, index) => {
    const row = document.createElement("tr");
    row.innerHTML = `
      <td>${index + 1}</td>
      <td>${article.source || "-"}</td>
      <td>${article.title || "-"}</td>
      <td>${article.published_at || "-"}</td>
      <td><a href="${article.url || "#"}" target="_blank">連結</a></td>
      <td>
        <button class="small-btn" data-action="edit" data-index="${index}">編輯</button>
        <button class="small-btn delete" data-action="delete" data-index="${index}">刪除</button>
      </td>
    `;
    articleTableBody.appendChild(row);
  });
}

async function loadStatus() {
  try {
    const data = await fetchJson(api.status);
    renderStatus(data);
  } catch (error) {
    crawlerStatus.textContent = "讀取失敗";
    console.error(error);
  }
}

async function loadArticles() {
  try {
    const data = await fetchJson(api.articles);
    renderArticles(data.articles || []);
  } catch (error) {
    articleTableBody.innerHTML = `<tr><td colspan="6">讀取新聞失敗：${error.message}</td></tr>`;
    console.error(error);
  }
}

async function sendControl(action) {
  try {
    const data = await fetchJson(api.control, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action }),
    });
    renderStatus(data.status);
  } catch (error) {
    alert(`控制失敗：${error.message}`);
    console.error(error);
  }
}

async function deleteArticle(index) {
  if (!confirm("確認要刪除這筆新聞嗎？")) {
    return;
  }
  try {
    await fetchJson(api.edit, {
      method: "DELETE",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ index }),
    });
    await loadArticles();
    await loadStatus();
  } catch (error) {
    alert(`刪除失敗：${error.message}`);
  }
}

async function saveArticle() {
  const index = Number(editIndex.value);
  const payload = {
    index,
    source: editSource.value.trim(),
    title: editTitle.value.trim(),
    published_at: editPublishedAt.value.trim(),
    url: editUrl.value.trim(),
    content: editContent.value.trim(),
  };
  try {
    await fetchJson(api.edit, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    await loadArticles();
    await loadStatus();
    alert("新聞已儲存。" );
  } catch (error) {
    alert(`儲存失敗：${error.message}`);
  }
}

function fillEditor(article, index) {
  editIndex.value = index;
  editSource.value = article.source || "";
  editTitle.value = article.title || "";
  editPublishedAt.value = article.published_at || "";
  editUrl.value = article.url || "";
  editContent.value = article.content || "";
  window.scrollTo({ top: document.body.scrollHeight, behavior: "smooth" });
}

function clearForm() {
  editIndex.value = "";
  editSource.value = "";
  editTitle.value = "";
  editPublishedAt.value = "";
  editUrl.value = "";
  editContent.value = "";
}

articleTableBody.addEventListener("click", (event) => {
  const button = event.target.closest("button");
  if (!button) return;
  const index = Number(button.dataset.index);
  if (button.dataset.action === "edit") {
    fillEditor(currentArticles[index], index);
  }
  if (button.dataset.action === "delete") {
    deleteArticle(index);
  }
});

editorForm.addEventListener("submit", (event) => {
  event.preventDefault();
  saveArticle();
});

clearEditor.addEventListener("click", () => {
  clearForm();
});

startBtn.addEventListener("click", () => sendControl("start"));
stopBtn.addEventListener("click", () => sendControl("stop"));
refreshBtn.addEventListener("click", () => {
  loadStatus();
  loadArticles();
});
reloadArticles.addEventListener("click", loadArticles);

window.addEventListener("load", () => {
  loadStatus();
  loadArticles();
});
