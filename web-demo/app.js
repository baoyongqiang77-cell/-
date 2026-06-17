(function () {
  const data = window.DEMO_DATA;
  const state = {
    account: null,
    page: "overview"
  };

  const pageConfig = [
    { id: "overview", label: "总览", icon: "▦", allow: () => true },
    { id: "flight", label: "飞控任务", icon: "⌁", allow: account => hasAny(account, ["飞控", "遥测", "媒体同步", "平台运维"]) },
    { id: "analysis", label: "分析工单", icon: "◎", allow: account => hasAny(account, ["视觉分析", "视觉分析结果", "告警", "工单", "平台运维"]) },
    { id: "annotation", label: "数据标注", icon: "□", allow: account => hasAny(account, ["数据标注", "平台运维"]) },
    { id: "training", label: "训练发布", icon: "◇", allow: account => hasAny(account, ["训练", "模型发布", "平台运维"]) },
    { id: "algorithms", label: "14 算法", icon: "≋", allow: () => true },
    { id: "reports", label: "测试报告", icon: "✓", allow: () => true }
  ];

  const el = id => document.getElementById(id);

  function hasAny(account, features) {
    return features.some(feature => account.features.includes(feature));
  }

  function badge(value) {
    const normalized = String(value);
    let cls = "badge";
    if (["PASS", "READY", "FRAME_READY", "COMPLETED", "DISPATCHED", "ANALYSIS_READY"].includes(normalized)) cls += " ok";
    if (["PENDING", "NEEDS_REVIEW", "NEEDS_GEO_REVIEW", "候选池"].includes(normalized)) cls += " warn";
    if (["BLOCKED", "FEATURE_403"].includes(normalized)) cls += " blocked";
    return `<span class="${cls}">${normalized}</span>`;
  }

  function renderAccounts() {
    el("environment-copy").textContent = `${data.environment.name} · ${data.environment.operator}`;
    el("account-list").innerHTML = data.accounts.map(account => `
      <button class="account-card" type="button" data-account="${account.username}">
        <strong>${account.username}</strong>
        <span>${account.role} · ${account.tenantType}</span>
      </button>
    `).join("");
    document.querySelectorAll("[data-account]").forEach(button => {
      button.addEventListener("click", () => {
        const account = data.accounts.find(item => item.username === button.dataset.account);
        el("username").value = account.username;
        el("password").value = account.password;
      });
    });
  }

  function login(username, password) {
    const account = data.accounts.find(item => item.username === username && item.password === password);
    if (!account) {
      el("login-error").textContent = "账号或密码不匹配";
      return;
    }
    state.account = account;
    state.page = "overview";
    el("login-view").classList.add("hidden");
    el("app-view").classList.remove("hidden");
    renderShell();
  }

  function renderShell() {
    const account = state.account;
    el("tenant-type").textContent = account.tenantType;
    el("user-role").textContent = `${account.username} · ${account.role}`;
    el("current-tenant").textContent = account.tenant;
    el("test-result").textContent = data.environment.testResult;
    el("notice").textContent = data.environment.limitations;
    renderNav();
    renderPage();
  }

  function renderNav() {
    el("nav-list").innerHTML = pageConfig.map(page => {
      const allowed = page.allow(state.account);
      const cls = ["nav-item", state.page === page.id ? "active" : "", allowed ? "" : "locked"].join(" ");
      return `<button class="${cls}" type="button" data-page="${page.id}"><span>${page.icon}</span>${page.label}</button>`;
    }).join("");
    document.querySelectorAll("[data-page]").forEach(button => {
      button.addEventListener("click", () => {
        state.page = button.dataset.page;
        renderPage();
        renderNav();
      });
    });
  }

  function renderPage() {
    const page = pageConfig.find(item => item.id === state.page);
    el("page-title").textContent = page.label;
    if (!page.allow(state.account)) {
      el("main-panel").innerHTML = `
        <section class="access-denied">
          <h3>FEATURE_403</h3>
          <p>当前租户未开通目标功能。客户租户默认不开放训练、模型发布、跨租户统计和平台运维。</p>
        </section>
      `;
      return;
    }

    const renderers = {
      overview: renderOverview,
      flight: renderFlight,
      analysis: renderAnalysis,
      annotation: renderAnnotation,
      training: renderTraining,
      algorithms: renderAlgorithms,
      reports: renderReports
    };
    el("main-panel").innerHTML = renderers[state.page]();
  }

  function renderOverview() {
    return `
      <section class="grid cols-3">
        <div class="card metric"><span class="muted">自动化测试</span><strong>${data.environment.testResult}</strong><span>${data.environment.date}</span></div>
        <div class="card metric"><span class="muted">M1 模拟闭环</span><strong>可展示</strong><span>飞控到工单</span></div>
        <div class="card metric"><span class="muted">M2 / U7</span><strong>BLOCKED</strong><span>真实算法与生产材料待补齐</span></div>
      </section>
      <section class="grid cols-2" style="margin-top:14px">
        <div class="panel">
          <h3>开发单元</h3>
          <div class="table-wrap" style="margin-top:12px">${unitTable()}</div>
        </div>
        <div class="panel">
          <h3>M1 模拟闭环</h3>
          <div class="timeline" style="margin-top:12px">${workflowTimeline()}</div>
        </div>
      </section>
    `;
  }

  function unitTable() {
    return `
      <table>
        <thead><tr><th>单元</th><th>名称</th><th>测试</th><th>生产/真实验收</th></tr></thead>
        <tbody>
          ${data.units.map(unit => `<tr><td>${unit.unit}</td><td>${unit.name}</td><td>${badge(unit.test)}</td><td>${badge(unit.status)}</td></tr>`).join("")}
        </tbody>
      </table>
    `;
  }

  function workflowTimeline() {
    return data.workflow.map((step, index) => `
      <div class="timeline-item">
        <span class="dot">${index + 1}</span>
        <div><strong>${step.name}</strong><p class="muted">${step.evidence}</p></div>
        ${badge(step.status)}
      </div>
    `).join("");
  }

  function renderFlight() {
    return `
      <section class="grid cols-2">
        ${data.missions.map(mission => `
          <article class="card">
            <h3>${mission.route}</h3>
            <p class="muted" style="margin-top:6px">${mission.id} · ${mission.dock}</p>
            <div class="grid cols-3" style="margin-top:14px">
              <div>${badge(mission.status)}</div>
              <div><span class="muted">电量</span><br><strong>${mission.battery}</strong></div>
              <div><span class="muted">信号</span><br><strong>${mission.signal}</strong></div>
            </div>
          </article>
        `).join("")}
      </section>
      <section class="panel" style="margin-top:14px"><h3>任务链路</h3><div class="timeline" style="margin-top:12px">${workflowTimeline()}</div></section>
    `;
  }

  function renderAnalysis() {
    return `
      <section class="table-wrap">
        <table>
          <thead><tr><th>事件</th><th>算法</th><th>标签</th><th>置信度</th><th>状态</th><th>工单</th><th>资产定位</th></tr></thead>
          <tbody>
            ${data.events.map(event => `<tr><td>${event.id}</td><td>${event.algorithm}</td><td>${event.label}</td><td>${event.confidence}</td><td>${badge(event.status)}</td><td>${event.workOrder}</td><td>${event.asset}</td></tr>`).join("")}
          </tbody>
        </table>
      </section>
    `;
  }

  function renderAnnotation() {
    return `
      <section class="table-wrap">
        <table>
          <thead><tr><th>任务/数据集</th><th>算法</th><th>样本</th><th>状态</th><th>处理人</th></tr></thead>
          <tbody>
            ${data.annotationTasks.map(task => `<tr><td>${task.id}</td><td>${task.algorithm}</td><td>${task.samples}</td><td>${badge(task.status)}</td><td>${task.assignee}</td></tr>`).join("")}
          </tbody>
        </table>
      </section>
    `;
  }

  function renderTraining() {
    return `
      <section class="grid cols-2">
        <div class="card">
          <h3>训练任务</h3>
          <p class="muted" style="margin-top:8px">平台方可创建训练任务；客户租户默认返回 FEATURE_403。</p>
          ${badge(state.account.tenantType === "PLATFORM_OPERATOR" ? "PASS" : "FEATURE_403")}
        </div>
        <div class="card">
          <h3>模型发布</h3>
          <p class="muted" style="margin-top:8px">发布前必须满足指标、数据授权和双硬件制品门禁。</p>
          ${badge("BLOCKED")}
        </div>
      </section>
    `;
  }

  function renderAlgorithms() {
    return `
      <section class="table-wrap">
        <table>
          <thead><tr><th>编码</th><th>算法</th><th>验收目标</th><th>状态</th></tr></thead>
          <tbody>
            ${data.algorithms.map(algorithm => `<tr><td>${algorithm.code}</td><td>${algorithm.name}</td><td>${algorithm.target}</td><td>${badge(algorithm.status)}</td></tr>`).join("")}
          </tbody>
        </table>
      </section>
      <section class="panel" style="margin-top:14px">
        <h3>双硬件候选池</h3>
        <p class="muted" style="margin-top:8px">${data.hardware.note}</p>
        <div style="margin-top:12px">${badge(data.hardware.status)}</div>
      </section>
    `;
  }

  function renderReports() {
    return `
      <section class="grid cols-3">
        ${data.reports.map(report => `
          <article class="card">
            <h3>${report.name}</h3>
            <p class="muted" style="margin-top:8px">${report.path}</p>
            <div style="margin-top:12px">${badge(report.status.includes("PASS") ? "PASS" : report.status)}</div>
          </article>
        `).join("")}
      </section>
    `;
  }

  function bindEvents() {
    el("login-form").addEventListener("submit", event => {
      event.preventDefault();
      login(el("username").value.trim(), el("password").value);
    });
    el("logout-button").addEventListener("click", () => {
      state.account = null;
      el("app-view").classList.add("hidden");
      el("login-view").classList.remove("hidden");
    });
  }

  renderAccounts();
  bindEvents();
})();
