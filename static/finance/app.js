(function () {
  const palette = {
    income: "#0f766e",
    expense: "#b91c1c",
    blue: "#2563eb",
    amber: "#b45309",
    text: "#111827",
    muted: "#748094",
    grid: "#e6edf5",
    panel: "#ffffff",
  };

  function money(value) {
    return new Intl.NumberFormat("id-ID", {
      style: "currency",
      currency: "IDR",
      maximumFractionDigits: 0,
    }).format(Number(value || 0));
  }

  function rupiahDigits(value) {
    let raw = String(value || "").replace(/rp/gi, "").replace(/\s/g, "");
    if (/^\d+[.,]00$/.test(raw)) raw = raw.slice(0, -3);
    if (/^\d+\.\d{1,2}$/.test(raw)) raw = raw.split(".")[0];
    return raw.replace(/\D/g, "");
  }

  function groupThousands(digits) {
    if (!digits) return "";
    return digits.replace(/^0+(?=\d)/, "").replace(/\B(?=(\d{3})+(?!\d))/g, ".");
  }

  function formatRupiahInput(input) {
    const formatted = groupThousands(rupiahDigits(input.value));
    input.value = formatted;
  }

  function setupRupiahInputs(root) {
    (root || document).querySelectorAll('input[data-rupiah-input="true"]').forEach((input) => {
      if (input.dataset.rupiahReady === "true") return;
      input.dataset.rupiahReady = "true";
      formatRupiahInput(input);
      input.addEventListener("keydown", (event) => {
        if (["e", "E", "+", "-", "_"].includes(event.key)) event.preventDefault();
      });
      input.addEventListener("input", () => formatRupiahInput(input));
      input.addEventListener("paste", () => window.setTimeout(() => formatRupiahInput(input), 0));
      input.addEventListener("blur", () => formatRupiahInput(input));
    });
  }

  function setup(canvas) {
    const ratio = window.devicePixelRatio || 1;
    const width = Math.max(320, Math.floor(canvas.getBoundingClientRect().width || canvas.parentElement.clientWidth || 320));
    const height = Number(canvas.getAttribute("height") || 220);
    canvas.width = width * ratio;
    canvas.height = height * ratio;
    const ctx = canvas.getContext("2d");
    ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
    ctx.clearRect(0, 0, width, height);
    return { ctx, width, height };
  }

  function emptyState(ctx, width, height, label) {
    ctx.fillStyle = "#f8fafc";
    roundRect(ctx, 18, 18, width - 36, height - 36, 8);
    ctx.fill();
    ctx.fillStyle = palette.muted;
    ctx.font = "700 13px system-ui, sans-serif";
    ctx.textAlign = "center";
    ctx.fillText(label || "No chart data yet", width / 2, height / 2);
    ctx.textAlign = "left";
  }

  function roundRect(ctx, x, y, width, height, radius) {
    const r = Math.min(radius, width / 2, height / 2);
    ctx.beginPath();
    ctx.moveTo(x + r, y);
    ctx.arcTo(x + width, y, x + width, y + height, r);
    ctx.arcTo(x + width, y + height, x, y + height, r);
    ctx.arcTo(x, y + height, x, y, r);
    ctx.arcTo(x, y, x + width, y, r);
    ctx.closePath();
  }

  function chartFrame(ctx, width, height, maxValue) {
    const left = 54;
    const right = width - 14;
    const top = 20;
    const bottom = height - 34;
    ctx.strokeStyle = palette.grid;
    ctx.lineWidth = 1;
    ctx.fillStyle = palette.muted;
    ctx.font = "11px system-ui, sans-serif";
    for (let i = 0; i <= 4; i += 1) {
      const y = top + ((bottom - top) * i) / 4;
      ctx.beginPath();
      ctx.moveTo(left, y);
      ctx.lineTo(right, y);
      ctx.stroke();
      const value = maxValue - (maxValue * i) / 4;
      ctx.fillText(shortMoney(value), 4, y + 4);
    }
    return { left, right, top, bottom, width: right - left, height: bottom - top };
  }

  function shortMoney(value) {
    value = Number(value || 0);
    if (value >= 1000000) return `Rp${Math.round(value / 1000000)}m`;
    if (value >= 1000) return `Rp${Math.round(value / 1000)}k`;
    return `Rp${Math.round(value)}`;
  }

  function legend(ctx, items, width) {
    let x = width - 14;
    ctx.font = "700 11px system-ui, sans-serif";
    items.slice().reverse().forEach((item) => {
      const textWidth = ctx.measureText(item.label).width;
      x -= textWidth + 22;
      ctx.fillStyle = item.color;
      roundRect(ctx, x, 5, 10, 10, 5);
      ctx.fill();
      ctx.fillStyle = palette.muted;
      ctx.fillText(item.label, x + 14, 15);
      x -= 12;
    });
  }

  function barChart(id, rows, keys, options) {
    const canvas = document.getElementById(id);
    if (!canvas) return;
    const { ctx, width, height } = setup(canvas);
    if (!rows || !rows.length) {
      emptyState(ctx, width, height, "No data recorded yet");
      return;
    }
    const values = rows.flatMap((row) => keys.map((key) => Number(row[key] || 0)));
    const max = Math.max(1, ...values) * 1.12;
    const frame = chartFrame(ctx, width, height, max);
    const groupWidth = frame.width / rows.length;
    const colors = options?.colors || [palette.income, palette.expense, palette.blue, palette.amber];
    legend(
      ctx,
      keys.map((key, index) => ({ label: options?.labels?.[key] || key, color: colors[index % colors.length] })),
      width,
    );

    rows.forEach((row, index) => {
      const available = Math.max(14, groupWidth - 14);
      const barWidth = Math.max(7, available / keys.length - 4);
      keys.forEach((key, keyIndex) => {
        const value = Number(row[key] || 0);
        const barHeight = (value / max) * frame.height;
        const x = frame.left + index * groupWidth + 7 + keyIndex * (barWidth + 4);
        const y = frame.bottom - barHeight;
        ctx.fillStyle = colors[keyIndex % colors.length];
        roundRect(ctx, x, y, barWidth, Math.max(2, barHeight), 4);
        ctx.fill();
      });
      if (index % Math.ceil(rows.length / 6) === 0 || rows.length <= 6) {
        ctx.fillStyle = palette.muted;
        ctx.font = "11px system-ui, sans-serif";
        ctx.fillText(String(row.label || row.name || "").slice(0, 12), frame.left + index * groupWidth + 4, height - 10);
      }
    });
  }

  function lineChart(id, rows, key, options) {
    const canvas = document.getElementById(id);
    if (!canvas) return;
    const { ctx, width, height } = setup(canvas);
    if (!rows || !rows.length) {
      emptyState(ctx, width, height, "No trend data yet");
      return;
    }
    const values = rows.map((row) => Number(row[key] || row.amount || 0));
    const max = Math.max(1, ...values) * 1.12;
    const min = Math.min(0, ...values);
    const span = Math.max(1, max - min);
    const frame = chartFrame(ctx, width, height, max);

    ctx.strokeStyle = options?.color || palette.blue;
    ctx.lineWidth = 3;
    ctx.beginPath();
    values.forEach((value, index) => {
      const x = frame.left + (index * frame.width) / Math.max(1, values.length - 1);
      const y = frame.bottom - ((value - min) / span) * frame.height;
      if (index === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    });
    ctx.stroke();

    values.forEach((value, index) => {
      if (index !== values.length - 1 && index !== 0) return;
      const x = frame.left + (index * frame.width) / Math.max(1, values.length - 1);
      const y = frame.bottom - ((value - min) / span) * frame.height;
      ctx.fillStyle = options?.color || palette.blue;
      ctx.beginPath();
      ctx.arc(x, y, 4, 0, Math.PI * 2);
      ctx.fill();
    });

    ctx.fillStyle = palette.text;
    ctx.font = "800 12px system-ui, sans-serif";
    ctx.fillText(options?.label || money(values[values.length - 1] || 0), frame.left, 15);
  }

  function scoreFrame(ctx, width, height) {
    const left = 34;
    const right = width - 18;
    const top = 22;
    const bottom = height - 34;
    ctx.strokeStyle = palette.grid;
    ctx.lineWidth = 1;
    ctx.fillStyle = palette.muted;
    ctx.font = "11px system-ui, sans-serif";
    for (let score = 1; score <= 5; score += 1) {
      const y = bottom - ((score - 1) / 4) * (bottom - top);
      ctx.beginPath();
      ctx.moveTo(left, y);
      ctx.lineTo(right, y);
      ctx.stroke();
      ctx.fillText(String(score), 10, y + 4);
    }
    return { left, right, top, bottom, width: right - left, height: bottom - top };
  }

  function scoreLineChart(id, rows, keys) {
    const canvas = document.getElementById(id);
    if (!canvas) return;
    const { ctx, width, height } = setup(canvas);
    if (!rows || !rows.length) {
      emptyState(ctx, width, height, "No mood trend yet");
      return;
    }
    const frame = scoreFrame(ctx, width, height);
    const colors = { mood: "#9a5b31", energy: "#5d7d52", productivity: "#2563eb" };
    legend(
      ctx,
      keys.map((key) => ({ label: key, color: colors[key] || palette.blue })),
      width,
    );
    keys.forEach((key) => {
      ctx.strokeStyle = colors[key] || palette.blue;
      ctx.lineWidth = 3;
      ctx.beginPath();
      rows.forEach((row, index) => {
        const value = Math.max(1, Math.min(5, Number(row[key] || 1)));
        const x = frame.left + (index * frame.width) / Math.max(1, rows.length - 1);
        const y = frame.bottom - ((value - 1) / 4) * frame.height;
        if (index === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
      });
      ctx.stroke();
    });
    rows.forEach((row, index) => {
      if (index % Math.ceil(rows.length / 5) !== 0 && rows.length > 5) return;
      const x = frame.left + (index * frame.width) / Math.max(1, rows.length - 1);
      ctx.fillStyle = palette.muted;
      ctx.font = "11px system-ui, sans-serif";
      ctx.fillText(String(row.label || "").slice(0, 10), x - 8, height - 10);
    });
  }

  function radarChart(id, values) {
    const canvas = document.getElementById(id);
    if (!canvas) return;
    const { ctx, width, height } = setup(canvas);
    const labels = [
      { key: "mood", label: "Mood" },
      { key: "energy", label: "Energy" },
      { key: "productivity", label: "Productivity" },
    ];
    if (!values || labels.every((item) => Number(values[item.key] || 0) === 0)) {
      emptyState(ctx, width, height, "No 30-day signal yet");
      return;
    }
    const cx = width / 2;
    const cy = height / 2 + 8;
    const radius = Math.min(width, height) * 0.32;
    ctx.strokeStyle = palette.grid;
    ctx.fillStyle = palette.muted;
    ctx.font = "700 12px system-ui, sans-serif";
    for (let ring = 1; ring <= 5; ring += 1) {
      ctx.beginPath();
      labels.forEach((item, index) => {
        const angle = -Math.PI / 2 + (index * Math.PI * 2) / labels.length;
        const r = (radius * ring) / 5;
        const x = cx + Math.cos(angle) * r;
        const y = cy + Math.sin(angle) * r;
        if (index === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
      });
      ctx.closePath();
      ctx.stroke();
    }
    ctx.beginPath();
    labels.forEach((item, index) => {
      const angle = -Math.PI / 2 + (index * Math.PI * 2) / labels.length;
      const value = Math.max(0, Math.min(5, Number(values[item.key] || 0)));
      const r = (radius * value) / 5;
      const x = cx + Math.cos(angle) * r;
      const y = cy + Math.sin(angle) * r;
      if (index === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    });
    ctx.closePath();
    ctx.fillStyle = "rgba(154, 91, 49, 0.28)";
    ctx.fill();
    ctx.strokeStyle = "#9a5b31";
    ctx.lineWidth = 3;
    ctx.stroke();
    labels.forEach((item, index) => {
      const angle = -Math.PI / 2 + (index * Math.PI * 2) / labels.length;
      const x = cx + Math.cos(angle) * (radius + 28);
      const y = cy + Math.sin(angle) * (radius + 28);
      ctx.fillStyle = palette.text;
      ctx.textAlign = "center";
      ctx.fillText(`${item.label} ${Number(values[item.key] || 0).toFixed(1)}`, x, y);
    });
    ctx.textAlign = "left";
  }

  function renderDashboard(data) {
    barChart("incomeExpenseChart", data.incomeExpense || [], ["income", "expense"], {
      labels: { income: "Income", expense: "Expense" },
      colors: [palette.income, palette.expense],
    });
    barChart("categoryChart", data.categorySpending || [], ["amount"], {
      labels: { amount: "Spending" },
      colors: [palette.blue],
    });
    lineChart("dailyChart", data.dailySpending || [], "amount", {
      color: palette.expense,
      label: "Daily spend trend",
    });
    lineChart("balanceChart", data.balanceHistory || [], "balance", {
      color: palette.income,
      label: "Balance trend",
    });
  }

  function renderInvestment(data) {
    barChart("allocationChart", data.allocation || [], ["amount"], {
      labels: { amount: "Allocation" },
      colors: [palette.income],
    });
    barChart("holdingsChart", data.holdings || [], ["amount"], {
      labels: { amount: "Market value" },
      colors: [palette.blue],
    });
  }

  function renderForecast(data) {
    lineChart("forecastChart", data.forecast || [], "balance", {
      color: palette.amber,
      label: "Projected balance",
    });
  }

  function renderJournal(data) {
    scoreLineChart("journalTrendChart", data.weekly || [], ["mood", "energy", "productivity"]);
    radarChart("journalRadarChart", data.radar || {});
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", () => setupRupiahInputs(document));
  } else {
    setupRupiahInputs(document);
  }

  window.MoneyManagerCharts = { renderDashboard, renderInvestment, renderForecast, renderJournal, setupRupiahInputs };
})();
