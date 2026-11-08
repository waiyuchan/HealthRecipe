"use strict";
const companion = {
  draft: "",
  busy: false,
  pending: null,
  status: null,
  messages: [],
  memories: [],
  locations: [],
  editMemory: null,
};
const FOOD_NAMES = [
  "番茄豆腐汤",
  "香菇蒸鸡",
  "西兰花炒虾仁",
  "山药芙蓉汤",
  "彩椒鸡丁",
  "南瓜小米粥",
  "黄瓜拌木耳",
  "萝卜炖牛肉",
  "菠菜鸡蛋面",
  "清蒸鲈鱼",
  "芹菜炒香干",
  "玉米排骨汤",
  "番茄炒鸡蛋",
  "香煎豆腐",
  "荷塘小炒",
  "红薯燕麦碗",
];
function foodPhoto(recipe, classes = "") {
  const index = FOOD_NAMES.indexOf(recipe.name);
  return index < 0
    ? `<div class="food-photo photo-placeholder ${classes}" role="img" aria-label="这道菜还没有照片"><span>你的拿手菜</span></div>`
    : `<div class="food-photo ${classes}" role="img" aria-label="${esc(recipe.name)}的 AI 生成示意图"><div class="photo-square food-${index}"></div></div>`;
}
function caloriesLabel(nutrition) {
  if (!nutrition || nutrition.coverage === 0) return "热量待核算";
  return `${nutrition.complete ? "约" : "已知部分 "}${Math.round(nutrition.per_serving.kcal)} kcal / 份${nutrition.complete ? "" : "，待补全"}`;
}
function nutritionBlock(n) {
  return `<section class="nutrition-detail"><div class="section-head"><div><h3>这一份的热量</h3><p>${esc(n.label)} · 按整道菜分成 ${n.servings} 份</p></div><strong>${n.coverage === 0 ? "—" : Math.round(n.per_serving.kcal)}<small> kcal / 份</small></strong></div><p class="hint">宏量营养${n.macros_complete ? "" : "仅含已知部分，未计完整"}</p><div class="macro-row"><span>蛋白质 <b>${n.per_serving.protein} g</b></span><span>碳水 <b>${n.per_serving.carbs} g</b></span><span>脂肪 <b>${n.per_serving.fat} g</b></span></div><details><summary>查看计算用量与未计入的部分</summary><table class="ingredient-table"><tbody>${n.items.map((i) => `<tr><td>${esc(i.name)}</td><td>${i.grams === null ? "克重待确认" : i.grams + " g"}</td><td>${i.kcal === null ? "未计入" : i.kcal + " kcal"}</td></tr>`).join("")}</tbody></table>${n.warnings.map((w) => `<p class="hint">${esc(w)}</p>`).join("")}<p class="hint">油按全量计入；估算未反映吸收、烹饪损耗或品牌差异。自行填写的热量只更新能量，未据此推算宏量营养。</p><a class="source-link" href="${esc(n.source_url)}" target="_blank" rel="noopener">${esc(n.source)}</a></details></section>`;
}
function dailyCalories(summary) {
  const t = summary.today;
  return `<div class="daily-calories"><div class="eyebrow">今天已记录的摄入<a href="#nutrition">查看核算</a></div><div class="daily-number">${t.counted_dishes ? Math.round(t.totals.kcal) : "—"}<span>kcal</span></div>${t.target ? `<progress value="${Math.min(t.totals.kcal, t.target)}" max="${t.target}" aria-label="相对于自行设置的参考目标"></progress><p>参考目标 ${t.target} kcal / 天 · ${t.counted_dishes} 道有份量记录</p>` : `<p>${t.counted_dishes ? "来自 " + t.counted_dishes + " 道有份量的记录" : "记下吃了多少，才好算得明白。"}</p>`}<small>${t.unquantified ? `另有 ${t.unquantified} 项缺少可核算食材或份量，未计入。` : ""}${t.partial ? "部分食材尚未计入；" : ""}未记录的食物也不包含在内。</small></div>`;
}
function weatherLabel(w) {
  return w.status === "ok"
    ? `${w.location.name} ${w.description} ${w.temperature}°C`
    : w.location
      ? `${w.location.name} · 天气未更新`
      : "选择所在城市";
}
function messageHtml(message) {
  if (message.role === "user")
    return `<article class="message user-message"><p>${esc(message.content)}</p></article>`;
  const p = message.payload || {};
  const ids = p.recipe_ids || [];
  const saved = p.saved_memories || [];
  return `<article class="message assistant-message"><span class="assistant-avatar" aria-hidden="true">饭</span><div class="message-body"><div class="message-name">饭搭子 <small>${esc(p.provider || "饮食助手")}</small></div><p>${esc(message.content)}</p>${p.warning ? `<p class="chat-warning">${esc(p.warning)}</p>` : ""}${p.sources?.length ? `<div class="tool-sources">${p.sources.map((s) => `<span>${esc(s.label)}</span>`).join("")}</div>` : ""}${
    ids.length
      ? `<div class="chat-recipes">${ids
          .map((id) => {
            const r = companion.recipes?.find((r) => r.id === id);
            return r
              ? `<button class="chat-recipe" data-action="detail" data-id="${id}">${foodPhoto(r)}<span><b>${esc(r.name)}</b><small>${r.minutes} 分钟 · ${caloriesLabel(r.nutrition)}</small></span><span>↗</span></button>`
              : "";
          })
          .join("")}</div>`
      : ""
  }${p.location_options?.length ? `<div class="chat-location-options"><p class="hint">确认城市后，才能按当地真实天气继续选菜：</p>${p.location_options.map((l, i) => `<button class="button small" data-action="chat-location" data-id="${message.id}" data-index="${i}">${esc(l.name)} ${esc(l.admin1)} ${esc(l.country)}</button>`).join("")}</div>` : ""}${saved.length ? `<div class="saved-memory">已记下：${saved.map((m) => esc(m.content)).join("；")}<a href="#chat" data-action="show-memories">查看记忆</a></div>` : ""}${p.plan?.length ? `<section class="draft-plan"><b>这几天的菜品灵感</b>${p.plan.map((i) => `<div><span>${esc(i.planned_on.slice(5))} ${esc(i.meal)}</span><span>${esc(i.recipe_name)}</span></div>`).join("")}<button class="button primary small" data-action="apply-chat-plan" data-id="${message.id}">确认加入餐单</button><small>点击加入后，同餐同菜不会重复。单道菜不代表完整配餐，可再搭配主食与配菜。</small></section>` : ""}</div></article>`;
}
async function chatPage() {
  const [status, messages, memories, recipes, weather] = await Promise.all([
    api("/assistant/status"),
    api("/assistant/messages"),
    api("/memories"),
    allRecipes(),
    api("/weather"),
  ]);
  Object.assign(companion, { status, messages, memories, recipes });
  const active = memories.filter(
    (m) => !m.expires_on || m.expires_on >= today(),
  );
  const mode =
    status.mode === "model" ? `${esc(status.provider)}已配置` : "本地选菜模式";
  return (
    heading(
      "今天吃什么，聊聊再决定。",
      "聊胃口，也聊最近的状态。让上一顿的记录，帮下一顿少纠结。",
    ) +
    `<div class="chat-layout"><section class="chat-window"><header class="chat-header"><div><span class="assistant-avatar">饭</span><strong>饭搭子</strong><span class="engine-badge">${mode}</span></div><button class="text-button" data-action="clear-chat" ${companion.busy ? "disabled" : ""}>清空聊天</button></header><p class="privacy-note">${esc(status.notice)}</p><div class="chat-log" id="chat-log" role="log" aria-label="与饭搭子的聊天">${messages.length ? messages.map(messageHtml).join("") : `<div class="chat-welcome"><span class="welcome-symbol">✳</span><h2>先聊聊，你今天的胃口。</h2><p>想吃香一点，还是清爽一点？<br>也可以告诉我最近的身体感受，我会结合有效记忆和饮食记录一起看。</p><div class="prompt-grid">${["看看我最近都吃了什么", "今天想吃热乎的，帮我挑几道", "帮我安排接下来三天的晚餐", "想吃有饱腹感的一餐，看看热量"].map((t) => `<button data-action="ask" data-prompt="${esc(t)}">${esc(t)}</button>`).join("")}</div></div>`}</div><form id="chat-form" class="chat-composer"><label class="sr-only" for="chat-input">想和饭搭子聊什么</label><textarea id="chat-input" name="message" rows="2" maxlength="3000" required placeholder="比如：最近睡得晚，今天在杭州有点冷，晚饭想吃热乎一点…" ${companion.busy ? "disabled" : ""}>${esc(companion.draft)}</textarea><div class="composer-bottom"><label class="inline-check"><input name="remember" type="checkbox" ${status.memory_enabled ? "checked" : ""} ${!status.memory_enabled ? "disabled" : ""}>记住我明确提到的信息</label><button class="button primary" ${companion.busy ? "disabled" : ""}>${companion.busy ? "正在整理…" : "发送 ↗"}</button></div><div class="form-error" role="alert"></div></form><p class="chat-footnote">饮食参考不代替诊疗。身体感受默认记忆 14 天；随时可在右侧修改或删除。</p></section>
    <aside class="context-panel"><section class="context-weather"><span class="eyebrow">把天时，也带上桌</span><button data-action="location" class="weather-select">⌖ ${esc(weatherLabel(weather))}<span>修改</span></button><p>${weather.season}季${weather.status === "ok" ? " · " + esc(weather.forecast[0]?.min ?? "") + "–" + esc(weather.forecast[0]?.max ?? "") + "°C" : " · " + esc(weather.message)}</p>${weather.status === "ok" ? `<small>${esc(weather.observed_at.replace("T", " "))} ${esc(weather.timezone)}<br><a href="https://open-meteo.com/" target="_blank" rel="noopener">Open-Meteo</a> 天气模型数据</small>` : ""}</section><section class="memory-panel" id="memory-panel"><div class="section-head"><h2>饮食记忆 <small>${active.length}</small></h2><button class="text-button" data-action="add-memory">＋ 添加</button></div><p class="hint">这是当前家庭共享的记忆；只记录适合共享的信息。只把有效记忆用于下一次沟通。</p><div class="memory-list">${memories.map((m) => `<article class="memory-item ${m.expires_on && m.expires_on < today() ? "expired" : ""}"><div><span>${esc(m.kind)}</span><small>${m.expires_on ? (m.expires_on < today() ? "已过期 · " : "有效至 ") + esc(m.expires_on) : "长期保留"}</small></div><p>${esc(m.content)}</p><div><button class="text-button" data-action="edit-memory" data-id="${m.id}">修改</button><button class="text-button" data-action="forget-memory" data-id="${m.id}">删除</button></div></article>`).join("") || '<p class="memory-empty">还没有记忆。你明确说过的忌口、口味和近期感受，可以留在这里。</p>'}</div></section><a class="context-history" href="#history"><b>最近吃过什么？</b><span>打开饮食记录，补上这一顿 ↗</span></a></aside></div>`
  );
}
async function submitChat(form, data) {
  if (companion.busy) return;
  const text = data.message.trim();
  if (!text) return;
  const id =
    companion.pending?.message === text
      ? companion.pending.id
      : crypto.randomUUID();
  companion.pending = { id, message: text };
  companion.draft = text;
  companion.busy = true;
  const log = $("#chat-log");
  if (log) {
    $(".chat-welcome", log)?.remove();
    log.insertAdjacentHTML(
      "beforeend",
      `<article class="message user-message optimistic"><p>${esc(text)}</p></article><article class="message assistant-message thinking"><span class="assistant-avatar">饭</span><p>正在看看天气、有效记忆和最近吃过的菜…</p></article>`,
    );
    log.scrollTop = log.scrollHeight;
  }
  const button = $("button", form);
  button.textContent = "正在整理…";
  $("#chat-input").disabled = true;
  try {
    await post("/assistant/chat", {
      message: text,
      remember: !!data.remember,
      request_id: id,
    });
    companion.draft = "";
    companion.pending = null;
  } catch (error) {
    companion.draft = text;
    throw error;
  } finally {
    companion.busy = false;
    if (state.page === "chat") {
      await render();
      positionChatReply();
      if (companion.pending)
        $(".form-error", $("#chat-form")).textContent =
          "刚才没有完成，内容已保留，可以重试。";
    } else toast("饭搭子已处理这条消息，可以回到聊天查看");
  }
}
function locationForm() {
  companion.locations = [];
  showModal(
    '<h2 id="modal-title">你在哪座城市吃饭？</h2><p class="detail-desc">选择城市后，按当地季节、真实气温和未来七天天气一起选菜。不读取设备精确定位。</p><form id="location-form"><div class="inline-row"><label class="field">城市名<input name="city" required minlength="2" maxlength="100" placeholder="例如：杭州、上海、Singapore"></label><button class="button primary">搜索城市</button></div><div class="form-error" role="alert"></div></form><div id="location-results"></div>',
  );
}
function memoryForm(id) {
  const m = id ? companion.memories.find((m) => m.id === Number(id)) : null;
  companion.editMemory = m;
  showModal(
    `<h2 id="modal-title">${m ? "修改饮食记忆" : "记住一件小事"}</h2><form id="memory-form"><div class="form-grid"><label class="field full">记忆类别<select name="kind">${["身体感受", "饮食偏好", "饮食目标", "生活习惯"].map((k) => `<option${selected(m?.kind || "身体感受", k)}>${k}</option>`).join("")}</select></label><label class="field full">你明确提到的信息<textarea name="content" rows="3" maxlength="500" required placeholder="例如：最近想吃温热的食物">${esc(m?.content || "")}</textarea></label><label class="field full">有效至（留空时，身体感受默认 14 天，其他长期保留）<input name="expires_on" type="date" value="${esc(m?.expires_on || "")}"></label></div><p class="hint">修改或删除记忆会清空聊天记录，避免旧上下文继续带入原信息；吃饭记录保留。</p><button class="button primary">保存记忆</button><div class="form-error" role="alert"></div></form>`,
  );
}
function calculatorRow() {
  return `<div class="calculator-row"><label class="field">食材<input name="food" list="food-options" required placeholder="输入食材名"></label><label class="field">可食重量（g）<input name="grams" type="number" min="0.1" max="100000" step="0.1" required placeholder="150"></label><label class="field">包装 kcal / 100g（可选）<input name="energy" type="number" min="0" max="1000" step="0.1" placeholder="缺少数据时可填"></label><button type="button" class="row-remove" data-action="remove-calculator-row" aria-label="移除这一种食材">×</button></div>`;
}
async function nutritionPage() {
  const [summary, reference] = await Promise.all([
    api("/nutrition/summary"),
    api("/nutrition/reference"),
  ]);
  return (
    heading(
      "吃得明白，也吃得尽兴。",
      "看清份量和用油，再聊热量。数字是参考，不是吃饭的评分。",
      '<button class="button primary" data-action="cook">＋ 记下这一餐</button>',
    ) +
    `<div class="nutrition-top">${dailyCalories(summary)}<div class="nutrition-note"><h2>每一口，都有来处。</h2><p>${esc(summary.note)}</p><p>${summary.today.unquantified ? `今天有 ${summary.today.unquantified} 项缺少可核算食材或个人份量，未计入以上热量。` : "按菜谱每份热量 × 你实际吃掉的份数累计。"}</p><a href="#settings" class="text-button">设置自己的参考目标</a></div></div>
    <section class="panel calculator-panel"><div class="section-head"><div><h2>自己算一算</h2><p>可算一碗饭，也可算整道菜。克重使用可食部分；生熟状态请与参考食材一致。</p></div><button type="button" class="button small" data-action="add-calculator-row">＋ 一种食材</button></div><form id="calculator-form"><datalist id="food-options">${reference.foods.map((f) => `<option value="${esc(f.name)}">${esc(f.description)}</option>`).join("")}</datalist><div id="calculator-rows">${calculatorRow()}</div><div class="calculator-bottom"><label class="field">分成几份<input name="servings" type="number" min="0.1" max="100" step="0.1" value="1" required></label><button class="button primary">核算这份热量</button></div><div class="form-error" role="alert"></div></form><div id="calculator-result"></div></section>
    <div class="section-head"><div><h2>最近 14 天，吃了这些</h2><p>${summary.unique_recipes} 道不同的菜，${summary.entries.length} 条记录。</p></div><a href="#history" class="text-button">去补记或修改</a></div><div class="intake-table">${summary.entries.map((h) => `<div><time>${esc(h.cooked_on)} ${esc(h.meal)}</time>${h.recipe_id ? `<button class="text-button" data-action="detail" data-id="${h.recipe_id}">${esc(h.recipe_name)}</button>` : `<span class="intake-dish-name">${esc(h.recipe_name)}</span>`}<span>${h.servings_eaten ? h.servings_eaten + " 份" : "个人份量未记录"}</span><b>${h.nutrition_snapshot ? (h.nutrition_snapshot.complete ? "约 " : "已知部分 ") + Math.round(h.nutrition_snapshot.consumed.kcal) + " kcal" : "未计入摄入"}</b></div>`).join("") || empty("从这一餐开始", "记录实际吃掉的份量，就能在这里回顾。")} </div><p class="hint">参考数据来自 <a href="${reference.source_url}" target="_blank" rel="noopener">${esc(reference.source)}</a>。并非临床营养评估。</p>`
  );
}
async function companionAction(button) {
  const { action, id } = button.dataset;
  switch (action) {
    case "chat-location": {
      const m = companion.messages.find((m) => m.id === Number(id));
      const location =
        m?.payload?.location_options?.[Number(button.dataset.index)];
      if (!location) throw Error("城市选项已经失效");
      const settings = await api("/settings");
      await post("/settings", { ...settings, location }, "PUT");
      companion.draft = "按刚才选择的城市天气，继续帮我看看这一餐怎么吃。";
      await render();
      toast("城市已确认，继续发送即可带上真实天气");
      return true;
    }
    case "ask":
      companion.draft = button.dataset.prompt || "";
      if (state.page === "chat") {
        const input = $("#chat-input");
        input.value = companion.draft;
        input.focus();
      } else {
        location.hash = "chat";
      }
      return true;
    case "location":
      locationForm();
      return true;
    case "choose-location": {
      const location = companion.locations[Number(id)];
      if (!location) throw Error("城市选项已过期，请重新搜索");
      const settings = await api("/settings");
      await post("/settings", { ...settings, location }, "PUT");
      closeModal();
      toast("已选择 " + location.name + "，正在更新天气");
      await render();
      return true;
    }
    case "clear-location": {
      const settings = await api("/settings");
      await post("/settings", { ...settings, location: null }, "PUT");
      toast("已清除城市");
      await render();
      return true;
    }
    case "show-memories":
      $("#memory-panel")?.scrollIntoView({
        behavior: "smooth",
        block: "start",
      });
      return true;
    case "add-memory":
      memoryForm();
      return true;
    case "edit-memory":
      memoryForm(id);
      return true;
    case "forget-memory":
      if (
        confirm(
          "删除这条记忆，并清空聊天记录以避免旧上下文继续带入？吃饭记录会保留。",
        )
      ) {
        await api("/memories/" + id, { method: "DELETE" });
        toast("已删除记忆并清空聊天上下文");
        await render();
      }
      return true;
    case "clear-chat":
      if (confirm("清空聊天记录？饮食记忆和吃饭记录会保留，可分别管理。")) {
        await api("/assistant/messages", { method: "DELETE" });
        companion.pending = null;
        toast("聊天已清空");
        await render();
      }
      return true;
    case "apply-chat-plan": {
      const message = companion.messages.find((m) => m.id === Number(id));
      if (!message?.payload?.plan?.length) throw Error("这份建议已不可用");
      await post("/plans/batch", {
        items: message.payload.plan.map(({ recipe_id, planned_on, meal }) => ({
          recipe_id,
          planned_on,
          meal,
        })),
      });
      toast("已加入餐单，重复安排已自动合并");
      return true;
    }
    case "add-calculator-row":
      $("#calculator-rows").insertAdjacentHTML("beforeend", calculatorRow());
      return true;
    case "remove-calculator-row":
      if (document.querySelectorAll(".calculator-row").length > 1)
        button.closest(".calculator-row").remove();
      else toast("至少保留一种食材");
      return true;
  }
  return false;
}
async function submitCompanionForm(form, data) {
  switch (form.id) {
    case "chat-form":
      await submitChat(form, data);
      return true;
    case "home-chat-form":
      companion.draft = data.message;
      location.hash = "chat";
      return true;
    case "location-form": {
      const locations = await api(
        "/locations?q=" + encodeURIComponent(data.city),
      );
      companion.locations = locations;
      $("#location-results").innerHTML = locations.length
        ? locations
            .map(
              (l, i) =>
                `<button class="location-result" data-action="choose-location" data-id="${i}"><b>${esc(l.name)}</b><span>${esc([l.admin1, l.country].filter(Boolean).join("，"))}</span><small>${l.latitude.toFixed(2)}, ${l.longitude.toFixed(2)}</small></button>`,
            )
            .join("")
        : '<p class="hint">没有找到这座城市。可以尝试拼音、英文或加上国家名。</p>';
      return true;
    }
    case "memory-form": {
      const body = { ...data, expires_on: data.expires_on || null };
      await post(
        companion.editMemory
          ? "/memories/" + companion.editMemory.id
          : "/memories",
        body,
        companion.editMemory ? "PUT" : "POST",
      );
      closeModal();
      toast("记忆已保存");
      await render();
      return true;
    }
    case "calculator-form": {
      const materials = [...document.querySelectorAll(".calculator-row")].map(
        (row) => ({
          name: $("[name=food]", row).value.trim(),
          unit: "实际称重",
          grams: Number($("[name=grams]", row).value),
          kcal_per100g:
            $("[name=energy]", row).value === ""
              ? null
              : Number($("[name=energy]", row).value),
        }),
      );
      const n = await post("/nutrition/estimate", {
        materials,
        servings: Number(data.servings),
      });
      $("#calculator-result").innerHTML = nutritionBlock(n);
      return true;
    }
  }
  return false;
}
document.addEventListener("keydown", (event) => {
  if (
    event.target.id === "chat-input" &&
    event.key === "Enter" &&
    !event.shiftKey &&
    !event.isComposing
  ) {
    event.preventDefault();
    if (!companion.busy) event.target.form.requestSubmit();
  }
});

function positionChatReply() {
  const log = $("#chat-log");
  if (!log) return;
  const replies = log.querySelectorAll(".assistant-message");
  const last = replies[replies.length - 1];
  if (last)
    log.scrollTop +=
      last.getBoundingClientRect().top - log.getBoundingClientRect().top - 12;
}
