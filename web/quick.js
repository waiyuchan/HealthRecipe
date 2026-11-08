"use strict";
const quick = {
  random: [],
  drawCount: 3,
  results: null,
  preview: null,
  draftId: null,
  drafts: [],
  editingLog: null,
  recipes: [],
  pending: null,
  busy: false,
  voice: null,
};
const SOURCE_LABELS = {
  xiachufang: "下厨房",
  douguo: "豆果美食",
  meishichina: "美食天下",
  xiaohongshu: "小红书",
  woks: "中餐双语食谱（原文英文）",
};
function entryBar() {
  return `<section class="entry-bar" aria-label="快速操作"><button data-action="random-open"><span>⚄</span><div><b>随机吃点什么</b><small>挑一道，或一次来几道</small></div><i>↗</i></button><button data-action="quick-log"><span>✓</span><div><b>记下今天吃的</b><small>只写菜名也可以，一次记多道</small></div><i>↗</i></button><button data-action="capture"><span>＋</span><div><b>想吃的菜，收进来</b><small>报菜名找做法，知道就口述</small></div><i>↗</i></button></section>`;
}
function voiceButton(target, label = "点这里口述") {
  return `<button type="button" class="button small ghost" data-action="dictate" data-target="${target}">◉ ${label}</button>`;
}
function stopDictation() {
  const current = quick.voice;
  quick.voice = null;
  if (current) {
    current.recognition.stop();
    current.button.textContent = current.label;
  }
}
function dictate(button) {
  if (quick.voice) {
    stopDictation();
    return;
  }
  const Recognition =
    window.SpeechRecognition || window.webkitSpeechRecognition;
  const status = $("#voice-status");
  if (!Recognition) {
    if (status)
      status.textContent =
        "这个浏览器没有提供语音识别，可以使用手机键盘的听写，或直接打字。";
    toast("浏览器未提供语音识别，可使用系统听写或打字");
    return;
  }
  const target = $("#" + button.dataset.target);
  if (!target) return;
  const recognition = new Recognition();
  recognition.lang = "zh-CN";
  recognition.continuous = true;
  recognition.interimResults = true;
  const label = button.textContent;
  quick.voice = { recognition, button, label };
  button.textContent = "■ 结束口述";
  recognition.onresult = (event) => {
    let interim = "";
    for (let i = event.resultIndex; i < event.results.length; i++) {
      const text = event.results[i][0].transcript;
      if (event.results[i].isFinal) {
        target.value +=
          (target.value && !/[\n，,、。]$/.test(target.value) ? "，" : "") +
          text;
        target.dispatchEvent(new Event("input", { bubbles: true }));
      } else interim += text;
    }
    if (status)
      status.textContent =
        interim || "正在听，可以继续说；完成后点「结束口述」。";
  };
  recognition.onerror = () => {
    if (status)
      status.textContent =
        "没有完成语音识别，已识别的内容仍保留。可用系统听写或直接编辑。";
  };
  recognition.onend = () => {
    if (quick.voice?.recognition === recognition) quick.voice = null;
    button.textContent = label;
    if (status && !status.textContent.includes("没有完成"))
      status.textContent = "口述已结束，确认文字后再保存。";
  };
  try {
    recognition.start();
    if (status) status.textContent = "正在请求浏览器麦克风与语音识别权限…";
  } catch {
    quick.voice = null;
    button.textContent = label;
    if (status)
      status.textContent = "语音识别暂不可用，可以直接打字或使用系统听写。";
  }
}
async function randomForm() {
  quick.random = [];
  quick.drawCount = 3;
  showModal(
    '<h2 id="modal-title">今天，让运气下厨。</h2><p class="detail-desc">随机挑菜，同样遵守忌口、做菜时长和近期去重。</p><p class="loading">正在翻菜谱盒子…</p>',
  );
  modal.classList.add("wide");
  await drawRandom();
}
async function drawRandom(count = quick.drawCount) {
  const previous = quick.random.map((r) => r.id);
  quick.drawCount = Number(count);
  const result = await api(
    "/recommendations?mode=random&limit=" +
      Math.min(30, quick.drawCount + previous.length),
  );
  quick.random = [
    ...result.items.filter((r) => !previous.includes(r.id)),
    ...result.items.filter((r) => previous.includes(r.id)),
  ].slice(0, quick.drawCount);
  showModal(
    `<h2 id="modal-title">今天，让运气下厨。</h2><p class="detail-desc">${result.eligible} 道符合条件，随机挑了 ${quick.random.length} 道。已应用忌口和近 ${result.avoid_days} 天去重${result.eligible > quick.drawCount ? "，尽量避开上一组" : ""}。</p><form id="random-form" class="random-controls"><label class="field">一次推荐<select name="count">${[1, 3, 6].map((n) => `<option value="${n}"${selected(n, quick.drawCount)}>${n} 道菜</option>`).join("")}</select></label><button class="button primary">⚄ 再抽一组</button></form><div class="cards random-cards">${quick.random.map(card).join("") || empty("暂时没有合适的", "可以新增菜谱，或主动调整偏好；不会自动放宽忌口。", '<button class="button" data-action="capture">找一道新菜</button>')}</div>${quick.random.length ? '<div class="modal-actions"><button class="button primary" data-action="random-plan">加入今天晚餐</button><button class="button" data-action="random-ate">这几道今天吃了</button></div><p class="hint">这是菜品灵感，单道菜不等同完整配餐。</p>' : ""}`,
  );
  modal.classList.add("wide");
}
function mealNames(text) {
  if (quick.prefilledNames?.join("、") === text.trim())
    return quick.prefilledNames;
  const existing = quick.recipes.find((r) => r.name === text.trim());
  if (existing) return [existing.name];
  return [
    ...new Set(
      splitNames(
        text
          .replace(
            /^(?:我)?(?:今天)?(?:早上|中午|晚上|早餐|午餐|晚餐)?(?:吃了|吃的是|吃过了?)[:：]?\s*/,
            "",
          )
          .replace(/[。；;]+/g, "，"),
      )
        .map((s) => s.trim())
        .filter(Boolean),
    ),
  ];
}
async function quickMealForm(options = {}) {
  quick.recipes = await allRecipes();
  quick.editingLog = options.entry || null;
  const entry = options.entry;
  const hour = new Date().getHours();
  const meal =
    entry?.meal ||
    (hour < 10 ? "早餐" : hour < 15 ? "午餐" : hour < 22 ? "晚餐" : "加餐");
  const names = entry?.name || options.names?.join("、") || "";
  quick.prefilledNames = options.names || null;
  showModal(
    `<h2 id="modal-title">${entry ? "修改这顿饭" : "今天，吃了些什么？"}</h2><p class="detail-desc">不用先有菜谱。外卖、食堂、零食，都可以只记个名字。</p><form id="quick-meal-form"><label class="field">${entry ? "菜名" : "吃过的菜名（用顿号、逗号或换行分隔）"}<textarea id="meal-names" name="names" rows="3" maxlength="3000" required placeholder="比如：番茄炒蛋、米饭、酸奶">${esc(names)}</textarea></label><div class="voice-row">${voiceButton("meal-names", "说说今天吃了啥")}<span class="hint">也可以用键盘听写。</span></div><p id="voice-status" class="hint" role="status">浏览器可能使用其语音识别服务；保存前可以编辑文字。</p><div class="quick-food-chips">${["米饭", "面条", "水果", "酸奶"].map((n) => `<button type="button" data-action="meal-add-name" data-name="${n}">＋ ${n}</button>`).join("")}</div><div class="form-grid"><label class="field">哪天吃的<input name="cooked_on" type="date" value="${entry?.cooked_on || today()}" max="${today()}" required></label><label class="field">哪一餐<select name="meal">${["早餐", "午餐", "晚餐", "加餐", "其他"].map((m) => `<option${selected(m, meal)}>${m}</option>`).join("")}</select></label></div><details class="optional-fields"><summary>可选：份量与小记</summary><div class="form-grid"><label class="field">各吃了几份<input name="servings_eaten" type="number" min="0.1" max="30" step="0.1" value="${entry?.servings_eaten ?? 1}" placeholder="不确定可留空"></label><label class="field">这一顿的小记<input name="note" maxlength="1000" value="${esc(entry?.note || "")}" placeholder="想记下的口味或感受"></label></div></details><p class="hint">只有与菜谱盒子准确匹配的菜，才会按其用量估算热量；只报菜名不会编造营养数字。</p><button class="button primary">${entry ? "保存修改" : "记下这一餐"}</button><div class="form-error" role="alert"></div></form>`,
  );
}
function captureForm(options = {}) {
  if (!options.keepDraft) quick.draftId = options.draftId || null;
  quick.captureInput = options;
  showModal(
    `<h2 id="modal-title">想吃的菜，先收进来。</h2><p class="detail-desc">知道做法就说两句；不知道就留空，只报菜名，我帮你找几个版本。</p><form id="capture-form"><label class="field">菜名<input name="name" maxlength="100" value="${esc(options.name || "")}" placeholder="比如：红烧肉、番茄炒蛋"></label><label class="field capture-link">或粘贴菜谱 / 小红书分享链接<input name="url" value="${esc(options.url || options.source_url || "")}" maxlength="1500" placeholder="也可以整段粘贴分享文字，自动识别链接"></label><label class="field">做法（知道就说，不知道就留空）<textarea id="capture-narration" name="narration" rows="4" maxlength="15000" placeholder="比如：番茄切块，鸡蛋炒好先盛出来。再炒番茄，出汁后把鸡蛋倒回去。">${esc(options.narration || "")}</textarea></label><div class="voice-row">${voiceButton("capture-narration", "口述我知道的做法")}<span class="hint">按你的原话整理。</span></div><p class="hint" id="voice-status" role="status">语音由浏览器提供，不可用时可打字或用系统听写。</p><details class="optional-fields"><summary>可选：食材、作者与搜索来源</summary><label class="field">食材与用量（一行一种，食材 | 用量；不清楚可空）<textarea name="materials" rows="3" placeholder="番茄 | 2个&#10;鸡蛋 | 3个">${esc((options.materials || []).map((m) => m.name + " | " + m.unit).join("\n"))}</textarea></label><label class="field">作者 / 署名（可选）<input name="author" value="${esc(options.author || "")}" maxlength="200"></label><div class="source-checkboxes">${Object.entries(
      SOURCE_LABELS,
    )
      .map(
        ([key, label]) =>
          `<label class="inline-check"><input type="checkbox" name="sources" value="${key}" checked>${label}</label>`,
      )
      .join(
        "",
      )}</div></details><div class="modal-actions"><button class="button primary">继续：整理或找做法</button><button type="button" class="button ghost" data-action="advanced-editor">完整手动录入</button></div><div class="form-error" role="alert"></div></form>`,
  );
}
function searchResults(result) {
  quick.results = result;
  quick.preview = null;
  showModal(
    `<h2 id="modal-title">「${esc(result.query)}」可以这样做</h2><p class="detail-desc">找到了 ${result.items.length} 个公开结果。挑一个提取、预览，再收进菜谱盒子。</p><div class="source-options">${result.sources.map((s) => `<a href="${esc(s.search_url)}" target="_blank" rel="noopener noreferrer"><b>${esc(s.name)}</b><span>${s.count ? "找到 " + s.count + " 项" : "打开站内搜索 ↗"}</span><small>${esc(s.note)}</small></a>`).join("")}</div>${result.warnings.map((w) => `<p class="hint">${esc(w)}；仍可打开各站搜索，或粘贴已有链接。</p>`).join("")}<div class="capture-results">${result.items.map((r, i) => `<article><div><span class="tag">${esc(r.source_name)}</span>${r.language === "en" ? '<span class="tag">保留英文原文</span>' : ""}<h3>${esc(r.title)}</h3><p>${esc(r.summary)}</p><a class="source-link" href="${esc(r.url)}" target="_blank" rel="noopener noreferrer">打开原文 ↗</a></div><button class="button primary small" data-action="capture-result" data-index="${i}">提取这份做法</button></article>`).join("") || empty("这次没有读到匹配的公开结果", "来源可能暂时不可用；可以打开上面的站内搜索，粘贴你找到的分享链接。")}</div><div class="modal-actions"><button class="button" data-action="capture-again">改个菜名 / 粘贴链接</button><button class="button ghost" data-action="capture-draft">先存为待找菜谱</button></div><p class="hint">小红书等平台可能需要登录或限制读取；只提取可访问文字，不会补写缺少的做法。</p>`,
  );
  modal.classList.add("wide");
}
function capturePreview(result) {
  quick.preview = result;
  if (result.status !== "ready") {
    showModal(
      `<h2 id="modal-title">这份做法，还没读完整。</h2><p class="detail-desc">${esc(result.message || "公开页面暂时没有可辨认的做法。")}</p>${result.name ? `<h3>${esc(result.name)}</h3>` : ""}${result.source_url ? `<a class="button" href="${esc(result.source_url)}" target="_blank" rel="noopener noreferrer">打开原文 ↗</a>` : ""}${result.narration ? `<details class="optional-fields"><summary>已经读到的公开文字</summary><p class="original-copy">${esc(result.narration)}</p></details>` : ""}<div class="modal-actions">${quick.results ? '<button class="button primary" data-action="capture-back">换一个来源</button>' : ""}<button class="button" data-action="capture-fill">粘贴 / 口述做法</button><button class="button ghost" data-action="capture-draft">存为待找菜谱</button></div>`,
    );
    return;
  }
  const r = result.recipe;
  showModal(
    `<h2 id="modal-title">先看看，是不是这个味道。</h2><h3 class="capture-name">${esc(r.name)}</h3><p class="detail-desc">来源：${esc(result.source || "你的记录")}${r.author ? " · " + esc(r.author) : ""}</p>${r.source_url ? `<a class="source-link" href="${esc(r.source_url)}" target="_blank" rel="noopener noreferrer">查看原文 ↗</a>` : ""}<h3>用料</h3>${r.materials.length ? `<table class="ingredient-table"><tbody>${r.materials.map((m) => `<tr><td>${esc(m.name)}</td><td>${esc(m.unit)}</td></tr>`).join("")}</tbody></table>` : '<p class="hint">原文没有独立用料表，先保留做法；食材可稍后补充，暂不核算热量。</p>'}<h3>做法</h3><ol class="steps">${r.methods.map((m) => `<li>${esc(m)}</li>`).join("")}</ol>${(result.warnings || []).map((w) => `<p class="hint">${esc(w)}</p>`).join("")}<div class="modal-actions"><button class="button primary" data-action="capture-save">收进菜谱盒子</button><button class="button" data-action="capture-edit">编辑用料与人份</button>${quick.results ? '<button class="button ghost" data-action="capture-back">再看其他版本</button>' : ""}</div>`,
  );
}
async function draftSection() {
  const drafts = await api("/capture/drafts");
  quick.drafts = drafts;
  if (!drafts.length) return "";
  return `<section class="draft-shelf"><div class="section-head"><div><h2>还想做的菜</h2><p>先记住名字，做法可以以后再找。</p></div></div><div class="draft-list">${drafts.map((d) => `<article><div><b>${esc(d.name)}</b><small>${d.source_url ? "已保留来源链接" : "做法待补充"}</small></div><button class="text-button" data-action="continue-draft" data-id="${d.id}">继续找 / 补做法</button><button class="text-button" data-action="delete-draft" data-id="${d.id}">移除</button></article>`).join("")}</div></section>`;
}
async function newHistoryPage() {
  const summary = await api("/food-log?days=3650");
  state.history = summary.entries;
  const recent = summary.entries.filter((h) => h.cooked_on >= addDays(-13));
  return (
    heading(
      "今天吃了啥，顺手记一下。",
      "菜谱盒子里没有的菜，也可以直接记。",
      '<button class="button primary" data-action="quick-log">＋ 记下今天吃的</button>',
    ) +
    `<div class="history-toolbar"><p>近 14 天 ${recent.length} 条记录 · 已计入选菜去重与饭搭子回顾</p><button class="text-button" data-action="capture">想吃的菜，找个做法 ↗</button></div><div class="history-list">${summary.entries.map((h) => `<article class="history-item"><time datetime="${h.cooked_on}">${h.cooked_on}<small>${esc(h.meal || "其他")}</small></time><div><h3>${h.recipe_id ? `<button class="recipe-name" data-action="detail" data-id="${h.recipe_id}">${esc(h.recipe_name)}</button>` : `<span class="recipe-name">${esc(h.recipe_name)}</span>`}</h3><span class="history-intake">${h.nutrition_snapshot ? (h.nutrition_snapshot.complete ? "约 " : "已知部分 ") + Math.round(h.nutrition_snapshot.consumed.kcal) + " kcal · " + h.servings_eaten + " 份" : "已记下菜名，热量尚未核算"}</span>${h.rating ? `<span class="rating">${"★".repeat(h.rating)}</span>` : ""}${h.note ? `<p>${esc(h.note)}</p>` : ""}</div><div class="history-actions">${h.kind === "quick" ? `<button class="text-button" data-action="edit-quick-log" data-id="${h.id}">修改记录</button><button class="text-button" data-action="delete-quick-log" data-id="${h.id}">删除</button>` : actionButton("修改评价", "edit-history", h.id, "text-button") + actionButton("删除", "delete-history", h.id, "text-button")}</div></article>`).join("") || empty("从今天这顿开始", "报几个菜名就好，份量和做法都可以以后再补。", '<button class="button primary" data-action="quick-log">记下今天吃的</button>')}</div>`
  );
}
async function quickAction(button) {
  const { action, id } = button.dataset;
  switch (action) {
    case "dictate":
      dictate(button);
      return true;
    case "random-open":
      await randomForm();
      return true;
    case "random-plan":
      await post("/plans/batch", {
        items: quick.random.map((r) => ({
          recipe_id: r.id,
          planned_on: today(),
          meal: "晚餐",
        })),
      });
      button.textContent = "已加入今天晚餐 ✓";
      toast("今天晚餐已安排，重复菜品不会重复添加");
      return true;
    case "random-ate":
      await quickMealForm({ names: quick.random.map((r) => r.name) });
      return true;
    case "quick-log":
      await quickMealForm({
        names: button.dataset.name ? [button.dataset.name] : undefined,
      });
      return true;
    case "meal-add-name": {
      const input = $("#meal-names");
      const names = mealNames(input.value);
      if (!names.includes(button.dataset.name)) names.push(button.dataset.name);
      input.value = names.join("、");
      return true;
    }
    case "edit-quick-log": {
      const entry = state.history.find(
        (h) => h.kind === "quick" && h.id === Number(id),
      );
      await quickMealForm({ entry });
      return true;
    }
    case "delete-quick-log":
      if (confirm("删除这条吃饭记录？")) {
        await api("/food-log/" + id, { method: "DELETE" });
        toast("这条记录已删除");
        await render();
      }
      return true;
    case "capture":
      quick.results = null;
      quick.preview = null;
      captureForm();
      return true;
    case "advanced-editor":
      editor(
        quick.preview?.status === "ready" ? quick.preview.recipe : null,
        true,
      );
      return true;
    case "capture-result": {
      const result = quick.results?.items[Number(button.dataset.index)];
      if (!result) throw Error("搜索结果已失效，请重新找一次");
      button.textContent = "正在提取原文…";
      capturePreview(
        await post("/capture/preview", {
          name: quick.results.query,
          url: result.url,
        }),
      );
      return true;
    }
    case "capture-back":
      searchResults(quick.results);
      return true;
    case "capture-again":
      captureForm({ name: quick.results?.query || "", keepDraft: true });
      return true;
    case "capture-fill":
      captureForm({
        ...quick.preview,
        keepDraft: true,
        name:
          quick.preview?.name ||
          quick.results?.query ||
          quick.captureInput?.name ||
          "",
      });
      return true;
    case "capture-save": {
      const result = await post("/capture/save", {
        recipe: quick.preview.recipe,
        draft_id: quick.draftId,
      });
      quick.draftId = null;
      closeModal();
      toast(result.created ? "菜谱已收好" : "这份来源已经在菜谱盒子里了");
      await render();
      await detail(result.recipe.id);
      return true;
    }
    case "capture-edit":
      editor(quick.preview.recipe, true);
      return true;
    case "capture-draft": {
      const p = quick.preview;
      const body = {
        name: p?.name || quick.results?.query || quick.captureInput?.name || "",
        narration: p?.narration || quick.captureInput?.narration || "",
        source_url: p?.source_url || "",
        author: p?.author || "",
        materials: p?.materials || [],
      };
      if (!body.name) throw Error("先填一个菜名");
      await post(
        quick.draftId ? "/capture/drafts/" + quick.draftId : "/capture/drafts",
        body,
        quick.draftId ? "PUT" : "POST",
      );
      closeModal();
      toast("菜名和已有内容已收进待找菜谱");
      if (state.page === "recipes") await render();
      return true;
    }
    case "continue-draft": {
      const d = quick.drafts.find((d) => d.id === Number(id));
      if (!d) throw Error("待找菜谱已删除");
      quick.results = null;
      quick.preview = null;
      captureForm({ ...d, draftId: d.id });
      return true;
    }
    case "delete-draft":
      await api("/capture/drafts/" + id, { method: "DELETE" });
      toast("已移除待找菜谱");
      await render();
      return true;
  }
  return false;
}
async function submitQuickForm(form, data) {
  switch (form.id) {
    case "random-form":
      await drawRandom(Number(data.count));
      return true;
    case "quick-meal-form": {
      const names = mealNames(data.names);
      if (!names.length) throw Error("至少记一道菜");
      if (names.some((n) => n.length > 100) || names.length > 30)
        throw Error("一次最多 30 道菜，每个菜名不超过 100 字");
      const share = data.servings_eaten ? Number(data.servings_eaten) : null;
      const body = {
        cooked_on: data.cooked_on,
        meal: data.meal,
        note: data.note || "",
      };
      if (quick.editingLog) {
        if (names.length !== 1)
          throw Error("修改时请保留一道菜，多道菜可以另记一顿");
        await post(
          "/food-log/" + quick.editingLog.id,
          { ...body, name: names[0], servings_eaten: share },
          "PUT",
        );
      } else {
        const input = JSON.stringify({
          ...body,
          dishes: names.map((name) => ({ name, servings_eaten: share })),
        });
        const request_id =
          quick.pending?.input === input
            ? quick.pending.id
            : crypto.randomUUID();
        quick.pending = { input, id: request_id };
        await post("/food-log", { ...JSON.parse(input), request_id });
        quick.pending = null;
      }
      stopDictation();
      closeModal();
      toast("这一餐，记下了");
      await render();
      return true;
    }
    case "capture-form": {
      stopDictation();
      const materials = data.materials
        .split("\n")
        .filter((s) => s.trim())
        .map((line) => {
          const [name, ...unit] = line.split(/[|｜]/);
          return {
            name: name.trim(),
            unit: unit.join("|").trim() || "用量待补充",
          };
        });
      const body = {
        name: data.name,
        narration: data.narration,
        url: data.url,
        materials,
        author: data.author || "",
      };
      quick.captureInput = body;
      if (!body.name && !body.url)
        throw Error("报一个菜名，或者粘贴分享链接就好");
      const button = $("button:not([type])", form);
      if (button)
        button.textContent = body.narration
          ? "正在整理你的原话…"
          : body.url
            ? "正在提取公开做法…"
            : "正在找多个来源…";
      if (!body.narration && !body.url) {
        const sources = new FormData(form).getAll("sources");
        if (!sources.length) throw Error("至少选择一个来源");
        searchResults(
          await post("/capture/search", { name: body.name, sources }),
        );
      } else {
        capturePreview(await post("/capture/preview", body));
      }
      return true;
    }
  }
  return false;
}
window.addEventListener("DOMContentLoaded", () => {
  modal.addEventListener("close", () => {
    stopDictation();
    modal.classList.remove("wide");
  });
  window.addEventListener("hashchange", stopDictation);
});
