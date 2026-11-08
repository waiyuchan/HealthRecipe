"use strict";
const escapeHtml = (value) =>
  String(value).replace(
    /[&<>"']/g,
    (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        c
      ],
  );
fetch("/openapi.json")
  .then((r) => {
    if (!r.ok) throw Error("读取失败");
    return r.json();
  })
  .then((schema) => {
    document.querySelector("#api-content").innerHTML = Object.entries(
      schema.paths,
    )
      .filter(([path]) => path.startsWith("/api/"))
      .flatMap(([path, operations]) =>
        Object.entries(operations).map(([method, operation]) => {
          const body =
            operation.requestBody?.content?.["application/json"]?.schema;
          const resolve = (value) =>
            value?.$ref
              ? schema.components.schemas[value.$ref.split("/").pop()]
              : value;
          return `<details class="api-operation"><summary><span class="api-method">${escapeHtml(method.toUpperCase())}</span><code>${escapeHtml(path)}</code> · ${escapeHtml(operation.summary || "")}</summary>${operation.parameters ? `<p>路径与查询参数</p><pre>${escapeHtml(JSON.stringify(operation.parameters, null, 2))}</pre>` : ""}${body ? `<p>JSON 请求体定义</p><pre>${escapeHtml(JSON.stringify(resolve(body), null, 2))}</pre>` : ""}<p>响应状态：${Object.keys(operation.responses).map(escapeHtml).join("，")}</p></details>`;
        }),
      )
      .join("");
  })
  .catch(() => {
    document.querySelector("#api-content").textContent =
      "无法读取接口定义，请检查服务后刷新。";
  });
