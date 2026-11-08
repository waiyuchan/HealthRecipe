"use strict";
const $ = (q, root = document) => root.querySelector(q);
const content = $("#content");
const modal = $("#modal");
const state = {
  page: "home",
  epoch: 0,
  query: "",
  category: "",
  favorite: false,
  offset: 0,
  rec: { ingredients: "", season: "", temperature: "", mode: "smart" },
  detail: null,
  history: [],
  recipes: [],
};
const esc = (value) =>
  String(value ?? "").replace(
    /[&<>"']/g,
    (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        c
      ],
  );
const localDate = (value = new Date()) =>
  `${value.getFullYear()}-${String(value.getMonth() + 1).padStart(2, "0")}-${String(value.getDate()).padStart(2, "0")}`;
const today = () => localDate();
const addDays = (n, from = new Date()) => {
  const d = new Date(from);
  d.setDate(d.getDate() + n);
  return localDate(d);
};
const splitNames = (value) =>
  value
    .split(/[,，、\n]/)
    .map((v) => v.trim())
    .filter(Boolean);
const selected = (a, b) => (a === b ? " selected" : "");
let toastTimer;
function toast(message) {
  clearTimeout(toastTimer);
  $("#toast").textContent = message;
  $("#toast").classList.add("visible");
  toastTimer = setTimeout(() => $("#toast").classList.remove("visible"), 4000);
}
async function api(path, options = {}) {
  const response = await fetch("/api" + path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!response.ok) {
    let data;
    try {
      data = await response.json();
    } catch {
      data = {};
    }
    const detail = Array.isArray(data.detail)
      ? data.detail
          .map((e) => `${e.loc.slice(1).join(".")}: ${e.msg}`)
          .join("；")
      : data.detail;
    throw new Error(detail || `请求失败（${response.status}），请重试`);
  }
  return response.status === 204 ? null : response.json();
}
const post = (path, body, method = "POST") =>
  api(path, { method, body: JSON.stringify(body) });
const actionButton = (label, action, id, classes = "button small") =>
  `<button class="${classes}" data-action="${action}" data-id="${id}">${label}</button>`;
function empty(title, description, button = "") {
  return `<div class="empty"><h3>${title}</h3><p>${description}</p>${button}</div>`;
}
function heading(title, description, action = "") {
  return `<div class="page-title"><div><h1>${title}</h1><p>${description}</p></div>${action}</div>`;
}
function card(recipe) {
  return `<article class="recipe-card"><button class="card-visual" data-action="detail" data-id="${recipe.id}" aria-label="查看${esc(recipe.name)}">${foodPhoto(recipe)}</button><button class="favorite ${recipe.favorite ? "selected" : ""}" data-action="favorite" data-id="${recipe.id}" data-value="${!recipe.favorite}" aria-label="${recipe.favorite ? "取消收藏" : "收藏"}${esc(recipe.name)}" aria-pressed="${recipe.favorite}">${recipe.favorite ? "♥" : "♡"}</button><div class="card-body"><div class="card-meta"><span>${esc(recipe.category)}</span><span>${recipe.minutes} 分钟 · ${recipe.servings} 人份</span></div><button class="recipe-name" data-action="detail" data-id="${recipe.id}">${esc(recipe.name)}</button><p class="ingredients-line">${esc(
    recipe.materials
      .slice(0, 4)
      .map((m) => m.name)
      .join(" / "),
  )}</p><div class="calorie-pill ${recipe.nutrition?.complete ? "" : "partial"}">${caloriesLabel(recipe.nutrition)}</div>${
    recipe.reasons
      ? `<div class="reasons">${recipe.reasons
          .slice(0, 2)
          .map((r) => `<span>${esc(r)}</span>`)
          .join("")}</div>`
      : `<div class="tags">${recipe.tags
          .slice(0, 3)
          .map((t) => `<span class="tag">${esc(t)}</span>`)
          .join("")}</div>`
  }<div class="card-actions">${actionButton("看看怎么做", "detail", recipe.id, "button primary small")}${actionButton("＋ 加入餐单", "add-plan", recipe.id, "button small ghost")}</div></div></article>`;
}
async function home() {
  const params = new URLSearchParams(
    Object.entries(state.rec).filter(([, v]) => v !== ""),
  );
  const [recommendations, summary, weather, memories] = await Promise.all([
    api("/recommendations?" + params),
    api("/nutrition/summary"),
    api("/weather"),
    api("/memories"),
  ]);
  const active = memories.filter(
    (m) => !m.expires_on || m.expires_on >= today(),
  );
  return `<div class="home-heading"><div><p class="eyebrow">今天的胃口，值得认真对待</p><h1>想吃点什么？</h1></div><button class="location-chip" data-action="location">⌖ ${esc(weatherLabel(weather))}<span>⌄</span></button></div>${entryBar()}<div class="home-grid"><section class="hero"><div class="hero-copy"><span class="hero-label">把日子，吃得有滋有味。</span><h2>热锅一响，<br>好好开饭。</h2><p>来点鲜的、香的、热乎的。<br>这一餐，和你的胃口商量着来。</p><button class="button hero-cta" data-action="ask" data-prompt="结合最近吃过的菜和我的偏好，今天吃什么？">让饭搭子帮我挑 ↗</button></div><span class="photo-credit">AI 生成食物示意图</span></section><aside class="home-side">${dailyCalories(summary)}<section class="companion-invite"><div class="companion-label"><span class="assistant-avatar">饭</span><div><strong>你的饭搭子</strong><small>聊聊再决定吃什么</small></div><span>✳</span></div><p>最近状态怎么样？<br>口味、天气、吃过的，我一起看。</p><form id="home-chat-form"><input name="message" aria-label="和饭搭子聊聊" required maxlength="3000" placeholder="今天想吃点热乎的…"><button aria-label="开始和饭搭子聊聊">↗</button></form><small>带上 ${active.length} 条有效记忆 · 近 14 天 ${summary.entries.length} 条记录</small></section></aside></div>
  <div class="section-head recommendations-head"><div><h2>这一餐，有点想吃。</h2><p>${recommendations.season}季 · ${recommendations.eligible} 道符合条件，已应用忌口与近 ${recommendations.avoid_days} 天去重</p></div><button class="text-button" data-action="shuffle">↻ 换一桌灵感</button></div><form id="recommend-form" class="filter-panel"><label>厨房里有什么<input name="ingredients" value="${esc(state.rec.ingredients)}" placeholder="番茄、鸡蛋、豆腐…"></label><label>季节<select name="season"><option value="">跟随所在地</option>${["春", "夏", "秋", "冬"].map((v) => `<option${selected(state.rec.season, v)}>${v}</option>`).join("")}</select></label><label>气温（可手动覆盖）<input type="number" name="temperature" min="-50" max="60" step="0.1" value="${esc(state.rec.temperature)}" placeholder="${weather.status === "ok" ? weather.temperature + " °C" : "可选，例如 18"}"></label><button class="button primary">用这些食材选菜</button></form><div class="cards">${recommendations.items.map(card).join("") || empty("这次还没挑到合适的", "试试其他食材，或者调整厨房偏好。", '<a class="button" href="#settings">调整偏好</a>')}</div><div class="taste-bottom"><a href="#history"><strong>上一顿，也给下一顿一点灵感。</strong><span>近 14 天 ${summary.unique_recipes} 道不同的菜，去看看吃饭记录 ↗</span></a><a href="#plan"><strong>给接下来的几天，留点好吃的。</strong><span>看看餐单和自动整理的购物清单 ↗</span></a></div><p class="filter-note">热量按食材和份量参考估算，缺失用量会标注；照片为 AI 生成的菜品示意图。</p>`;
}
async function recipePage() {
  const params = new URLSearchParams({
    q: state.query,
    category: state.category,
    favorite: state.favorite,
    offset: state.offset,
    limit: 12,
  });
  const [data, categories, draftsHTML] = await Promise.all([
    api("/recipes?" + params),
    api("/categories"),
    draftSection(),
  ]);
  return (
    heading(
      "你的菜谱盒子",
      "把喜欢的味道收好，需要时随时翻开。",
      '<button class="button" data-action="import">按菜名找 / 快收菜谱</button>',
    ) +
    `<form id="search-form" class="searchbar"><input name="q" aria-label="搜索菜谱" placeholder="搜菜名、食材或做法，比如：番茄 鸡蛋" value="${esc(state.query)}"><button class="button primary">搜索菜谱</button><button type="button" class="button ${state.favorite ? "light" : ""}" data-action="filter-favorite">${state.favorite ? "♥ 已收藏" : "♡ 只看收藏"}</button></form>
    <div class="chips"><button class="chip ${!state.category ? "active" : ""}" data-action="category" data-value="">全部</button>${categories.map((c) => `<button class="chip ${state.category === c.name ? "active" : ""}" data-action="category" data-value="${esc(c.name)}">${esc(c.name)} ${c.count}</button>`).join("")}</div>
    <div class="cards">${data.items.map(card).join("") || empty("这里还没有菜谱", "换个关键词试试，也可以记下自己的拿手菜。", '<button class="button primary" data-action="new">新建菜谱</button>')}</div>
    ${data.total > 12 ? `<div class="pagination"><button class="button small" data-action="prev" ${state.offset === 0 ? "disabled" : ""}>上一页</button><span>${state.offset / 12 + 1} / ${Math.ceil(data.total / 12)}</span><button class="button small" data-action="next" ${state.offset + 12 >= data.total ? "disabled" : ""}>下一页</button></div>` : ""}` +
    draftsHTML
  );
}
async function planPage() {
  const [plans, shopping, library] = await Promise.all([
    api("/plans"),
    api("/shopping"),
    allRecipes(),
  ]);
  const days = Array.from({ length: 7 }, (_, i) => addDays(i));
  let checks;
  try {
    checks = JSON.parse(localStorage.getItem("hr-shopping") || "{}");
  } catch {
    checks = {};
  }
  return (
    heading(
      "这一周，吃得有安排",
      "从今天起的七天，给每一餐留一点期待。",
      '<button class="button primary" data-action="add-plan">＋ 安排一道菜</button>',
    ) +
    `<div class="plan-grid">${days
      .map(
        (day, index) =>
          `<section class="day ${index === 0 ? "today" : ""}"><h3>${index === 0 ? "今天" : new Date(day + "T12:00:00").toLocaleDateString("zh-CN", { weekday: "short" })}<strong>${Number(day.slice(5, 7))}/${Number(day.slice(8))}</strong></h3>${plans
            .filter((p) => p.planned_on === day)
            .map(
              (p) =>
                `<div class="meal-item"><small>${esc(p.meal)}</small><button data-action="detail" data-id="${p.recipe_id}">${esc(p.recipe_name)}</button><button class="remove" data-action="delete-plan" data-id="${p.id}">移除安排</button></div>`,
            )
            .join(
              "",
            )}<button class="day-add" data-action="add-plan" data-date="${day}">＋ 加一道</button></section>`,
      )
      .join("")}</div>
    <div class="section-head"><div><h2>顺手列好购物清单</h2><p>根据七天餐单整理；按原菜谱份量列出用量，现有食材仅提示、不判断余量。</p></div><button class="text-button" data-action="copy-shopping">复制清单</button></div>
    <div class="shopping">${plans.some((p) => !library.find((r) => r.id === p.recipe_id)?.materials.length) ? '<p class="hint">餐单中有菜谱尚未填写食材表，这些食材没有计入购物清单；请先补全用料。</p>' : ""}${shopping.length ? `<div class="shopping-list">${shopping.map((item) => `<label class="shopping-item"><input type="checkbox" data-shopping="${esc(item.name)}" ${checks[today() + "|" + item.name] ? "checked" : ""}><span>${esc(item.name)} ${item.in_pantry ? "<small>厨房已有，请确认余量</small>" : ""}<small>${item.uses.map((u) => `${esc(u.recipe)} ${esc(u.amount)}（${esc(u.planned_on.slice(5))} ${esc(u.meal)}）`).join("<br>")}</small></span></label>`).join("")}</div>` : empty("还没有可汇总的食材", plans.length ? "已安排菜谱的食材表还需补充，填写后会自动汇总。" : "先在餐单里加一道菜，食材会自动出现在这里。")}</div>`
  );
}
async function historyPage() {
  state.history = await api("/history?days=3650");
  const recent = state.history.filter(
    (h) => h.cooked_on >= addDays(-13),
  ).length;
  return (
    heading(
      "吃饭记录",
      "记下吃过什么、吃了多少，也留一点下次更好吃的小心得。",
      '<button class="button primary" data-action="cook">＋ 记下这一餐</button>',
    ) +
    `<p class="section-sub">最近 14 天做过 ${recent} 次 · 下方展示近十年记录，记录会参与推荐去重和口味评分。</p><div class="history-list">${state.history.map((h) => `<article class="history-item"><time datetime="${h.cooked_on}">${h.cooked_on}<small>${esc(h.meal || "其他")}</small></time><div><h3><button class="recipe-name" data-action="detail" data-id="${h.recipe_id}">${esc(h.recipe_name)}</button></h3><span class="history-intake">${h.nutrition_snapshot ? (h.nutrition_snapshot.complete ? "约 " : "已知部分 ") + Math.round(h.nutrition_snapshot.consumed.kcal) + " kcal · " + h.servings_eaten + " 份" : "个人食用份量未填写，未计入摄入"}</span><span class="rating">${h.rating ? "★".repeat(h.rating) + "☆".repeat(5 - h.rating) : "尚未评分"}</span>${h.note ? `<p>${esc(h.note)}</p>` : ""}</div><div class="history-actions">${actionButton("修改评价", "edit-history", h.id, "text-button")}${actionButton("删除", "delete-history", h.id, "text-button")}</div></article>`).join("") || empty("第一顿，从今天记起", "选一道做过的菜，写下你的口味和小心得。", '<button class="button primary" data-action="cook">记录做菜</button>')}</div>`
  );
}
async function settingsPage() {
  const settings = await api("/settings");
  return (
    heading("照顾你的厨房习惯", "常备什么、不吃什么，告诉厨房就好。") +
    `<div class="settings-layout"><form id="settings-form" class="panel"><h2>食材与选菜偏好</h2>
    <label class="field">不想出现在推荐里的食材<textarea name="excluded" rows="2" placeholder="例如：花生，虾，香菜">${esc(settings.excluded_ingredients.join("，"))}</textarea><span class="hint">用逗号分隔。按名称、常见别名及食材组匹配，不替代过敏原核查；烹饪前仍需确认全部原料。</span></label>
    <label class="field">厨房现有食材<textarea name="pantry" rows="2" placeholder="例如：番茄，鸡蛋">${esc(settings.pantry.join("，"))}</textarea><span class="hint">推荐优先使用，购物清单会提醒这些食材已经在厨房。</span></label>
    <div class="form-grid"><label class="field">做一道菜最多花几分钟<input name="max_minutes" type="number" min="1" max="1440" value="${settings.max_minutes}" required></label><label class="field">不重复推荐最近几天做过的菜<input name="avoid_days" type="number" min="0" max="90" value="${settings.avoid_days}" required><span class="hint">默认 14 天，填 0 关闭去重。</span></label></div>
    <label class="field">自己设置的每日热量参考目标（可选）<input name="daily_kcal_target" type="number" min="1200" max="5000" value="${settings.daily_kcal_target ?? ""}" placeholder="留空不设置"><span class="hint">不是系统计算或建议的摄入目标；不适用于儿童、孕哺期或需要医疗营养指导的人群。</span></label><label class="inline-check"><input name="memory_enabled" type="checkbox" ${settings.memory_enabled ? "checked" : ""}>使用饮食记忆辅助聊天与选菜</label><p class="hint">当前为家庭共用数据。关闭后不读取或新增记忆，已有内容可在饭搭子页面管理。</p><div class="settings-location"><span>所在城市：${esc(settings.location?.name || "尚未选择")}</span><button type="button" class="text-button" data-action="location">选择城市</button>${settings.location ? '<button type="button" class="text-button" data-action="clear-location">清除</button>' : ""}</div><button class="button primary">保存厨房偏好</button><div class="form-error" role="alert"></div></form>
    <div><section class="panel"><h2>把厨房好好保存</h2><p>菜谱、收藏、做菜手记、餐单和偏好都可以一并备份。建议定期保存一份到自己的设备。</p><div class="backup-actions"><a class="button primary" href="/api/backup" download>导出完整备份</a><button class="button" data-action="restore">恢复备份</button></div><input id="restore-file" class="file-input" type="file" accept=".json,application/json"><p class="hint">恢复将替换当前全部数据。导入前会展示备份内容并请你确认，失败时保留原数据。</p></section>
    <section class="panel spaced-panel"><h2>关于这间厨房</h2><ul class="quiet-list"><li>个人或家庭共用的一份菜谱和记录。</li><li>数据保存在运行服务的设备上，刷新不会丢失。</li><li>聊天连接服务端配置的模型；当前对话、有效记忆和饮食摘要会发送给该服务。</li><li>可自选城市查询真实天气；记忆可以修改、过期与删除。</li></ul><div class="mini-note">好好吃饭是一份日常烹饪工具。推荐基于食材、口味和时节；不提供疾病诊疗或未经核实的食材功效。</div></section></div></div>`
  );
}
async function render() {
  const epoch = ++state.epoch;
  const page = location.hash.slice(1) || "home";
  state.page = [
    "home",
    "recipes",
    "plan",
    "history",
    "settings",
    "chat",
    "nutrition",
  ].includes(page)
    ? page
    : "home";
  document.querySelectorAll("nav a").forEach((a) => {
    a.classList.toggle("active", a.dataset.page === state.page);
    if (a.dataset.page === state.page) a.setAttribute("aria-current", "page");
    else a.removeAttribute("aria-current");
  });
  content.setAttribute("aria-busy", "true");
  try {
    const html = await {
      home,
      recipes: recipePage,
      plan: planPage,
      history: newHistoryPage,
      settings: settingsPage,
      chat: chatPage,
      nutrition: nutritionPage,
    }[state.page]();
    if (epoch !== state.epoch) return;
    content.innerHTML = html;
    $("#connection-state").textContent = "厨房已连接";
    if (state.page === "chat") positionChatReply();
  } catch (error) {
    if (epoch === state.epoch) {
      content.innerHTML = `<div class="error">${esc(error.message)}<br><button class="button small" data-action="retry">重新连接</button></div>`;
      $("#connection-state").textContent = "连接失败";
    }
  } finally {
    if (epoch === state.epoch) content.removeAttribute("aria-busy");
  }
}
function showModal(html) {
  modal.classList.remove("wide");
  $("#modal-content").innerHTML = html;
  if (!modal.open) modal.showModal();
  modal.scrollTop = 0;
}
function closeModal() {
  stopDictation();
  modal.close();
}
async function detail(id) {
  const recipe = await api("/recipes/" + id);
  state.detail = recipe;
  showModal(
    `<div class="detail-photo">${foodPhoto(recipe)}</div><h2 id="modal-title">${esc(recipe.name)}</h2><p class="detail-desc">${esc(recipe.description)}</p><div class="detail-meta"><span>${esc(recipe.category)}</span><span>${recipe.minutes} 分钟</span><span>${recipe.servings} 人份</span></div><div class="tags">${recipe.tags.map((t) => `<span class="tag">${esc(t)}</span>`).join("")}${recipe.seasons.map((s) => `<span class="tag">${s}季</span>`).join("")}</div>${recipe.author ? `<p class="hint">原作者：${esc(recipe.author)}</p>` : ""}${recipe.nutrition ? nutritionBlock(recipe.nutrition) : ""}<h3>准备这些食材</h3>${!recipe.materials.length ? '<p class="hint">食材表待补充，暂不核算热量；可按已有原文做法查看。</p>' : ""}<table class="ingredient-table"><tbody>${recipe.materials.map((m) => `<tr><td>${esc(m.name)}</td><td>${esc(m.unit)}</td></tr>`).join("")}</tbody></table><h3>一起动手做</h3><ol class="steps">${recipe.methods.map((step) => `<li>${esc(step)}</li>`).join("")}</ol>${recipe.original_text ? `<details class="optional-fields"><summary>查看原始口述 / 正文</summary><p class="original-copy">${esc(recipe.original_text)}</p></details>` : ""}${recipe.source_url ? `<a class="source-link" href="${esc(recipe.source_url)}" target="_blank" rel="noopener noreferrer">查看原始菜谱</a>` : ""}<div class="modal-actions">${actionButton("今天做了，记一下", "cook", recipe.id, "button primary")}${actionButton("＋ 加入餐单", "add-plan", recipe.id, "button")}${actionButton("编辑菜谱", "edit", recipe.id, "button ghost")}${actionButton("删除菜谱", "delete-recipe", recipe.id, "button danger")}</div>${recipe.related.length ? `<section class="related"><h3>同样的食材，还可以这样做</h3>${recipe.related.map((r) => `<button data-action="detail" data-id="${r.id}">${esc(r.name)} · ${esc(r.shared.join("、"))}</button>`).join("")}</section>` : ""}`,
  );
}
function editor(recipe = null, capture = false) {
  state.capture = capture;
  state.editing = recipe;
  const r = recipe || {
    name: "",
    description: "",
    category: "家常菜",
    minutes: 20,
    servings: 2,
    materials: [],
    methods: [],
    tags: [],
    seasons: [],
    source_url: "",
  };
  showModal(`<h2 id="modal-title">${recipe?.id ? "编辑这道菜" : recipe ? "预览并保存菜谱" : "记下你的拿手菜"}</h2><p class="detail-desc">一份用料，一段做法，留住熟悉的味道。</p><form id="recipe-form"><div class="form-grid">
    <label class="field full">菜名<input name="name" maxlength="100" value="${esc(r.name)}" required placeholder="例如：妈妈的番茄炒鸡蛋"></label>
    <label class="field full">一句话介绍<textarea name="description" rows="2" maxlength="1000" placeholder="这道菜有什么特别之处？">${esc(r.description)}</textarea></label>
    <label class="field">分类<input name="category" value="${esc(r.category)}" maxlength="30" list="category-list" required><datalist id="category-list">${["家常菜", "荤菜", "素菜", "汤羹", "主食", "凉菜", "炖菜"].map((c) => `<option value="${c}">`).join("")}</datalist></label>
    <label class="field">预计用时（分钟）<input name="minutes" type="number" min="1" max="1440" value="${r.minutes}" required></label>
    <label class="field">几人份<input name="servings" type="number" min="1" max="30" value="${r.servings}" required></label>
    <label class="field">适合的季节<select name="seasons"><option value="">四季皆宜</option>${["春", "夏", "秋", "冬"].map((s) => `<option value="${s}"${r.seasons.length === 1 ? selected(r.seasons[0], s) : ""}>${s}季</option>`).join("")}${r.seasons.length > 1 && r.seasons.length < 4 ? '<option value="keep" selected>保留原季节组合</option>' : ""}</select></label>
    <label class="field full">食材 | 用量 | 可食克重（可选） | 标签kcal/100g（可选）<textarea name="materials" rows="5" required placeholder="番茄 | 2个&#10;鸡蛋 | 3个&#10;盐 | 少许">${esc(r.materials.map((m) => m.name + " | " + m.unit + (m.grams != null || m.kcal_per100g != null ? " | " + (m.grams ?? "") + " | " + (m.kcal_per100g ?? "") : "")).join("\n"))}</textarea></label>
    <label class="field full">做法（一行一个步骤）<textarea name="methods" rows="5" required placeholder="番茄洗净切块，鸡蛋打散。&#10;热锅下油，先炒鸡蛋后盛出。">${esc(r.methods.join("\n"))}</textarea></label>
    <label class="field full">标签（逗号分隔）<input name="tags" value="${esc(r.tags.join("，"))}" placeholder="快手，清爽，家常"></label>
    <label class="field full">原作者（可选）<input name="author" maxlength="200" value="${esc(r.author || "")}" placeholder="保留原作者署名"></label><label class="field full">来源链接（可选）<input name="source_url" type="url" value="${esc(r.source_url)}" placeholder="https://…" maxlength="500"></label></div><button class="button primary">保存菜谱</button><div class="form-error" role="alert"></div></form>`);
}
async function allRecipes() {
  const items = [];
  let total = 1;
  while (items.length < total) {
    const page = await api(`/recipes?limit=200&offset=${items.length}`);
    items.push(...page.items);
    total = page.total;
    if (!page.items.length) break;
  }
  return items;
}
function recipeOptions(recipes, id) {
  return recipes
    .map(
      (r) =>
        `<option value="${r.id}"${selected(r.id, Number(id))}>${esc(r.name)}</option>`,
    )
    .join("");
}
async function cookForm(id, historyId) {
  const recipes = await allRecipes();
  const record = historyId
    ? state.history.find(
        (h) => h.id === Number(historyId) && h.kind !== "quick",
      )
    : null;
  state.editingHistory = record;
  showModal(
    `<h2 id="modal-title">${record ? "修改这顿饭的记录" : "这一顿，做了什么？"}</h2>${recipes.length ? `<form id="history-form"><div class="form-grid"><label class="field full">做过的菜<select name="recipe_id">${recipeOptions(recipes, record?.recipe_id || id)}</select></label><label class="field">做菜日期<input name="cooked_on" type="date" max="${today()}" value="${record?.cooked_on || today()}" required></label><label class="field">实际吃了几份（留空仅记做菜）<input name="servings_eaten" type="number" min="0.1" max="30" step="0.1" value="${record ? (record.servings_eaten ?? "") : 1}" placeholder="例如 0.5 或 1"></label><label class="field">哪一餐<select name="meal">${["早餐", "午餐", "晚餐", "加餐", "其他"].map((m) => `<option${selected(record?.meal || "晚餐", m)}>${m}</option>`).join("")}</select></label><label class="field">这次味道如何<select name="rating"><option value="">先不评分</option>${[5, 4, 3, 2, 1].map((n) => `<option value="${n}"${selected(record?.rating, n)}>${"★".repeat(n)} ${["", "不太喜欢", "有待调整", "还不错", "很喜欢", "下次还做"][n]}</option>`).join("")}</select></label><label class="field full">给下次做菜的小提醒<textarea name="note" rows="3" maxlength="1000" placeholder="例如：这次稍咸，下次少放半勺生抽。">${esc(record?.note || "")}</textarea></label></div><button class="button primary">保存做菜记录</button><div class="form-error" role="alert"></div></form>` : empty("先收好一道菜谱", "有了菜谱，就能记录做过的菜。", '<button class="button primary" data-action="new">新建菜谱</button>')}`,
  );
}
async function planForm(id, day) {
  const recipes = await allRecipes();
  showModal(
    `<h2 id="modal-title">给餐单加一道菜</h2>${recipes.length ? `<form id="plan-form"><div class="form-grid"><label class="field full">选一道菜<select name="recipe_id">${recipeOptions(recipes, id)}</select></label><label class="field">哪天吃<input name="planned_on" type="date" value="${day || today()}" required></label><label class="field">哪一餐<select name="meal"><option>晚餐</option><option>午餐</option><option>早餐</option></select></label></div><p class="hint">购物用量按菜谱原份量列出。同一天同一餐重复添加同一道菜，只保留一份。</p><button class="button primary">加入餐单</button><div class="form-error" role="alert"></div></form>` : empty("先收好一道菜谱", "有了菜谱，就能安排这一周。", '<button class="button primary" data-action="new">新建菜谱</button>')}`,
  );
}
function importForm() {
  showModal(
    '<h2 id="modal-title">收一道下厨房菜谱</h2><p class="detail-desc">粘贴你想收藏的菜谱链接，先预览，再保存到盒子里。</p><form id="import-form"><label class="field">菜谱链接或数字 ID<input name="source" required maxlength="500" placeholder="https://www.xiachufang.com/recipe/100561839/"></label><p class="hint">只读取这一份公开菜谱。若网站限制访问，可手动录入；请保留来源与作者信息，尊重原作者使用条件。</p><button class="button primary">提取并预览</button><div class="form-error" role="alert"></div></form>',
  );
}
async function handleAction(button) {
  if (await quickAction(button)) return;
  if (await companionAction(button)) return;
  const { action, id, value } = button.dataset;
  switch (action) {
    case "new":
      captureForm();
      break;
    case "detail":
      await detail(id);
      break;
    case "edit": {
      const r = await api("/recipes/" + id);
      editor(r);
      break;
    }
    case "favorite":
      await post(
        `/recipes/${id}/favorite`,
        { favorite: value === "true" },
        "PATCH",
      );
      toast(value === "true" ? "已收进收藏" : "已取消收藏");
      await render();
      break;
    case "add-plan":
      await planForm(id, button.dataset.date);
      break;
    case "cook":
      await cookForm(id);
      break;
    case "edit-history":
      await cookForm(null, id);
      break;
    case "import":
      quick.results = null;
      quick.preview = null;
      captureForm();
      break;
    case "shuffle":
      state.rec.mode = "random";
      await render();
      break;
    case "category":
      state.category = value;
      state.offset = 0;
      await render();
      break;
    case "filter-favorite":
      state.favorite = !state.favorite;
      state.offset = 0;
      await render();
      break;
    case "prev":
      state.offset = Math.max(0, state.offset - 12);
      await render();
      window.scrollTo({ top: 0 });
      break;
    case "next":
      state.offset += 12;
      await render();
      window.scrollTo({ top: 0 });
      break;
    case "retry":
      await render();
      break;
    case "delete-recipe":
      if (confirm("删除这道菜也会删除相关做菜手记与餐单安排，确定删除吗？")) {
        await api("/recipes/" + id, { method: "DELETE" });
        closeModal();
        toast("菜谱已删除");
        await render();
      }
      break;
    case "delete-plan":
      await api("/plans/" + id, { method: "DELETE" });
      toast("已移除这道安排");
      await render();
      break;
    case "delete-history":
      if (confirm("确定删除这条做菜记录吗？")) {
        await api("/history/" + id, { method: "DELETE" });
        toast("记录已删除");
        await render();
      }
      break;
    case "restore":
      $("#restore-file").click();
      break;
    case "copy-shopping": {
      const items = await api("/shopping");
      const text = items
        .map(
          (i) =>
            `${i.in_pantry ? "[厨房已有] " : ""}${i.name}：${i.uses.map((u) => `${u.amount}（${u.recipe} ${u.planned_on} ${u.meal}）`).join("；")}`,
        )
        .join("\n");
      if (!text) {
        toast("先安排几道菜，再复制清单");
        break;
      }
      try {
        await navigator.clipboard.writeText(text);
        toast("购物清单已复制");
      } catch {
        showModal(
          `<h2 id="modal-title">复制购物清单</h2><textarea rows="12" readonly aria-label="购物清单">${esc(text)}</textarea><p class="hint">长按或全选上方文字后复制。</p>`,
        );
      }
      break;
    }
  }
}
document.addEventListener("click", async (event) => {
  const button = event.target.closest("[data-action]");
  if (!button || button.disabled) return;
  button.disabled = true;
  try {
    await handleAction(button);
  } catch (error) {
    toast(error.message);
  } finally {
    button.disabled = false;
  }
});
document.addEventListener("submit", async (event) => {
  const form = event.target;
  if (!form.id) return;
  event.preventDefault();
  const data = Object.fromEntries(new FormData(form));
  const button = $('button[type="submit"], button:not([type])', form);
  if (button) button.disabled = true;
  const originalLabel = button?.textContent;
  const errorBox = $(".form-error", form);
  if (errorBox) errorBox.textContent = "";
  try {
    if (await submitQuickForm(form, data)) return;
    if (await submitCompanionForm(form, data)) return;
    switch (form.id) {
      case "recommend-form":
        state.rec = { ...data, mode: "smart" };
        await render();
        break;
      case "search-form":
        state.query = data.q;
        state.offset = 0;
        await render();
        break;
      case "recipe-form": {
        const old = state.editing;
        const materials = data.materials
          .split("\n")
          .filter((l) => l.trim())
          .map((line) => {
            const [name, unit = "", grams = "", energy = ""] =
              line.split(/[|｜]/);
            if (
              [grams, energy].some(
                (v) => v.trim() && !Number.isFinite(Number(v)),
              )
            )
              throw Error("克重和标签热量需要填写数字");
            return {
              name: name.trim(),
              unit: unit.trim() || "适量",
              grams: grams.trim() ? Number(grams) : null,
              kcal_per100g: energy.trim() ? Number(energy) : null,
            };
          });
        const recipe = {
          name: data.name,
          description: data.description,
          category: data.category,
          minutes: Number(data.minutes),
          servings: Number(data.servings),
          materials,
          methods: data.methods
            .split("\n")
            .map((s) => s.trim())
            .filter(Boolean),
          tags: splitNames(data.tags),
          seasons:
            data.seasons === "keep"
              ? old.seasons
              : data.seasons
                ? [data.seasons]
                : ["春", "夏", "秋", "冬"],
          source_url: data.source_url,
          author: data.author,
          favorite: old?.favorite || false,
          original_text: old?.original_text || "",
          xcf_id: old?.xcf_id || null,
        };
        if (state.capture && !old?.id) {
          await post("/capture/save", { recipe, draft_id: quick.draftId });
          quick.draftId = null;
        } else {
          await post(
            old?.id ? "/recipes/" + old.id : "/recipes",
            recipe,
            old?.id ? "PUT" : "POST",
          );
        }
        closeModal();
        toast("菜谱已保存");
        await render();
        break;
      }
      case "history-form":
        await post(
          state.editingHistory
            ? "/history/" + state.editingHistory.id
            : "/history",
          {
            ...data,
            recipe_id: Number(data.recipe_id),
            rating: data.rating ? Number(data.rating) : null,
            servings_eaten: data.servings_eaten
              ? Number(data.servings_eaten)
              : null,
          },
          state.editingHistory ? "PUT" : "POST",
        );
        closeModal();
        toast("这顿饭，记下了");
        await render();
        break;
      case "plan-form":
        await post("/plans", { ...data, recipe_id: Number(data.recipe_id) });
        closeModal();
        toast("已加入餐单，购物清单也准备好了");
        await render();
        break;
      case "settings-form":
        await post(
          "/settings",
          {
            ...(await api("/settings")),
            excluded_ingredients: splitNames(data.excluded),
            pantry: splitNames(data.pantry),
            max_minutes: Number(data.max_minutes),
            avoid_days: Number(data.avoid_days),
            daily_kcal_target: data.daily_kcal_target
              ? Number(data.daily_kcal_target)
              : null,
            memory_enabled: !!data.memory_enabled,
          },
          "PUT",
        );
        toast("厨房偏好已保存");
        break;
      case "import-form": {
        const result = await post("/import/xiachufang/preview", data);
        editor(result.recipe);
        if (result.exists) toast("这道菜已经在盒子里，可以直接编辑");
        break;
      }
    }
  } catch (error) {
    if (errorBox && errorBox.isConnected) errorBox.textContent = error.message;
    else toast(error.message);
  } finally {
    if (button) {
      button.disabled = false;
      if (button.isConnected && originalLabel)
        button.textContent = originalLabel;
    }
  }
});
document.addEventListener("change", async (event) => {
  const input = event.target;
  if (input.dataset.shopping) {
    try {
      const checks = JSON.parse(localStorage.getItem("hr-shopping") || "{}");
      checks[today() + "|" + input.dataset.shopping] = input.checked;
      const prefix = today() + "|";
      localStorage.setItem(
        "hr-shopping",
        JSON.stringify(
          Object.fromEntries(
            Object.entries(checks).filter(([k]) => k.startsWith(prefix)),
          ),
        ),
      );
    } catch {
      toast("浏览器未允许保存勾选状态");
    }
  }
  if (input.id === "restore-file" && input.files[0]) {
    try {
      if (input.files[0].size > 10_000_000)
        throw new Error("备份不能超过 10 MB");
      const backup = JSON.parse(await input.files[0].text());
      if (![1, 2, 3].includes(backup.version) || !Array.isArray(backup.recipes))
        throw new Error("不是有效的 HealthRecipe 备份");
      if (
        confirm(
          `备份有 ${backup.recipes.length} 道菜谱、${(backup.history?.length || 0) + (backup.meal_logs?.length || 0)} 条吃饭记录和 ${backup.plans?.length || 0} 道餐单安排。\n恢复将替换当前全部数据，建议先导出当前备份。确定继续？`,
        )
      ) {
        await post("/restore", backup);
        toast("厨房数据已恢复");
        await render();
      }
    } catch (error) {
      toast(error.message);
    } finally {
      input.value = "";
    }
  }
});
$("#new-recipe").addEventListener("click", () => {
  quick.results = null;
  quick.preview = null;
  captureForm();
});
$(".close", modal).addEventListener("click", closeModal);
modal.addEventListener("click", (event) => {
  if (event.target === modal) {
    const r = modal.getBoundingClientRect();
    if (
      event.clientX < r.left ||
      event.clientX > r.right ||
      event.clientY < r.top ||
      event.clientY > r.bottom
    )
      closeModal();
  }
});
window.addEventListener("hashchange", () => {
  closeModal();
  render();
  window.scrollTo({ top: 0 });
});
$("#date-label").textContent = new Date().toLocaleDateString("zh-CN", {
  month: "long",
  day: "numeric",
  weekday: "long",
});
render();
