// ===== Voice Studio — frontend logic =====

const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => document.querySelectorAll(sel);

// ---------- Theme ----------
const THEME_KEY = "vs-theme"; // "light" | "dark" | "system"

function systemTheme() {
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}
function applyTheme(pref) {
  const resolved = pref === "system" ? systemTheme() : pref;
  document.documentElement.setAttribute("data-theme", resolved);
}
function getThemePref() {
  return localStorage.getItem(THEME_KEY) || "system";
}
function setThemePref(pref) {
  localStorage.setItem(THEME_KEY, pref);
  applyTheme(pref);
  // keep settings segmented in sync
  $$("#themeSeg .seg").forEach((b) => b.classList.toggle("active", b.dataset.theme === pref));
}

// follow system when in system mode
window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => {
  if (getThemePref() === "system") applyTheme("system");
});

// topbar quick toggle: flips between light/dark explicitly
$("#themeToggle").addEventListener("click", () => {
  const current = document.documentElement.getAttribute("data-theme");
  setThemePref(current === "dark" ? "light" : "dark");
});

// settings segmented control
$$("#themeSeg .seg").forEach((btn) =>
  btn.addEventListener("click", () => setThemePref(btn.dataset.theme))
);

setThemePref(getThemePref());

// ---------- Tab navigation ----------
function switchView(name) {
  $$(".tab").forEach((t) => t.classList.toggle("active", t.dataset.view === name));
  $$(".view").forEach((v) => v.classList.toggle("active", v.id === `view-${name}`));
  if (name === "library") loadLibrary();
  if (name === "train") loadFinetuneVoices();
}
$$("#tabs .tab").forEach((t) => t.addEventListener("click", () => switchView(t.dataset.view)));
document.addEventListener("click", (e) => {
  const goto = e.target.closest("[data-goto]");
  if (goto) { e.preventDefault(); switchView(goto.dataset.goto); }
});

// ---------- Generic segmented controls ----------
function bindSegmented(containerSel, onChange) {
  const btns = $$(`${containerSel} .seg`);
  btns.forEach((b) =>
    b.addEventListener("click", () => {
      btns.forEach((x) => x.classList.toggle("active", x === b));
      onChange && onChange(b.dataset);
    })
  );
}
let ENGINE = "sovits";
let DEVICE = "cuda";
bindSegmented("#engineSeg", (d) => (ENGINE = d.engine));
bindSegmented("#deviceSeg", (d) => (DEVICE = d.device));

// ---------- Char counter + speed ----------
const ttsText = $("#ttsText");
ttsText.addEventListener("input", () => ($("#charCount").textContent = ttsText.value.length));
const speed = $("#speed");
speed.addEventListener("input", () => ($("#speedVal").textContent = Number(speed.value).toFixed(2) + "×"));

// ---------- Advanced (발음/톤) ----------
function bindRange(id, valId, fmt) {
  const el = $("#" + id);
  const upd = () => ($("#" + valId).textContent = fmt(Number(el.value)));
  el.addEventListener("input", upd); upd();
  return el;
}
const temperature = bindRange("temperature", "temperatureVal", (v) => v.toFixed(2));
const topK = bindRange("topK", "topKVal", (v) => String(v));
const repPen = bindRange("repPen", "repPenVal", (v) => v.toFixed(2));

const PRESETS = {
  natural:    { temperature: 1.0,  topK: 15, repPen: 1.35 },
  clear:      { temperature: 0.75, topK: 8,  repPen: 1.5 },
  expressive: { temperature: 1.15, topK: 25, repPen: 1.2 },
};
$$(".chip-btn").forEach((b) =>
  b.addEventListener("click", () => {
    const p = PRESETS[b.dataset.preset];
    if (!p) return;
    temperature.value = p.temperature; topK.value = p.topK; repPen.value = p.repPen;
    [temperature, topK, repPen].forEach((el) => el.dispatchEvent(new Event("input")));
    $$(".chip-btn").forEach((x) => x.classList.toggle("on", x === b));
  })
);

// ---------- API helpers ----------
async function api(path, opts) {
  const res = await fetch(path, opts);
  if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || res.statusText);
  return res;
}

// ---------- Load voices + device info ----------
let SELECTED_VOICE = null;
async function loadVoices() {
  try {
    const voices = await (await api("/api/voices")).json();
    const picker = $("#voicePicker");
    if (!voices.length) {
      SELECTED_VOICE = null;
      picker.innerHTML = '<div class="empty-hint">학습된 목소리가 없습니다. <a href="#" data-goto="train">목소리 학습</a>에서 먼저 만들어 주세요.</div>';
      return;
    }
    picker.innerHTML = "";
    voices.forEach((v, i) => {
      const chip = document.createElement("div");
      chip.className = "voice-chip" + (i === 0 ? " selected" : "");
      const label = document.createElement("span");
      label.textContent = v.name;
      const del = document.createElement("button");
      del.className = "chip-x";
      del.textContent = "✕";
      del.title = "이 목소리 삭제";
      chip.appendChild(label);
      chip.appendChild(del);
      chip.addEventListener("click", (e) => {
        if (e.target === del) return;
        $$(".voice-chip").forEach((c) => c.classList.remove("selected"));
        chip.classList.add("selected");
        SELECTED_VOICE = v.id;
      });
      del.addEventListener("click", async (e) => {
        e.stopPropagation();
        if (!confirm(`'${v.name}' 목소리를 삭제할까요? 되돌릴 수 없습니다.`)) return;
        try {
          await api("/api/voices/delete", {
            method: "POST", headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ id: v.id }),
          });
          if (SELECTED_VOICE === v.id) SELECTED_VOICE = null;
          loadVoices();
        } catch (err) { alert("삭제 실패: " + err.message); }
      });
      picker.appendChild(chip);
    });
    SELECTED_VOICE = voices[0].id;
  } catch (e) { /* server may not be ready */ }
}
async function loadDeviceInfo() {
  try {
    const info = await (await api("/api/system")).json();
    $("#deviceInfo").textContent = info.gpu
      ? `${info.gpu} · CUDA ${info.cuda || "?"} · ${info.torch ? "PyTorch " + info.torch : "PyTorch 미설치"}`
      : "GPU 미감지 — CPU로 실행됩니다. (PyTorch 미설치 시 설정 필요)";
  } catch (e) {
    $("#deviceInfo").textContent = "장치 정보를 불러올 수 없습니다.";
  }
}

// ---------- Generate (with progress) ----------
let _elapsedTimer = null, _statusTimer = null;
function startProgress(engine) {
  $("#genResult").classList.add("hidden");
  $("#genProgress").classList.remove("hidden");
  const t0 = Date.now();
  const statuses = engine === "sovits"
    ? ["엔진 준비 중…", "한국어 엔진 로딩 중… (최초 실행은 30초~1분 걸려요)", "음성 생성 중…", "마무리 중…"]
    : ["엔진 준비 중…", "모델 로딩 중…", "음성 생성 중…", "마무리 중…"];
  const thresholds = [2, 7, 14]; // 초 → statuses 인덱스 1,2,3
  let idx = 0;
  $("#genStatus").textContent = statuses[0];
  $("#genElapsed").textContent = "0초";
  _elapsedTimer = setInterval(() => {
    $("#genElapsed").textContent = Math.round((Date.now() - t0) / 1000) + "초";
  }, 500);
  _statusTimer = setInterval(() => {
    const s = (Date.now() - t0) / 1000;
    let want = 0;
    thresholds.forEach((th, i) => { if (s >= th) want = i + 1; });
    if (want !== idx && want < statuses.length) { idx = want; $("#genStatus").textContent = statuses[idx]; }
  }, 500);
}
function stopProgress() {
  clearInterval(_elapsedTimer); clearInterval(_statusTimer);
  $("#genProgress").classList.add("hidden");
}

$("#generateBtn").addEventListener("click", async () => {
  const text = ttsText.value.trim();
  if (!text) return alert("텍스트를 입력해 주세요.");
  const btn = $("#generateBtn");
  btn.classList.add("loading"); btn.disabled = true;
  $(".btn-label").textContent = "생성 중…";
  startProgress(ENGINE);
  try {
    const res = await api("/api/generate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        text, voice: SELECTED_VOICE, engine: ENGINE, device: DEVICE, speed: Number(speed.value),
        temperature: Number(temperature.value), top_k: Number(topK.value),
        repetition_penalty: Number(repPen.value),
      }),
    });
    const data = await res.json();
    $("#genStatus").textContent = "완료!";
    $("#audioPlayer").src = data.url + "?t=" + Date.now();
    LAST_FILE = data.url.split("/").pop();
    $("#downloadMsg").textContent = "";
    $("#genResult").classList.remove("hidden");
  } catch (e) {
    alert("생성 실패: " + e.message);
  } finally {
    stopProgress();
    btn.classList.remove("loading"); btn.disabled = false;
    $(".btn-label").textContent = "생성하기";
  }
});

// ---------- Source toggle (URL vs file) ----------
let SOURCE = "url";
bindSegmented("#sourceSeg", (d) => {
  SOURCE = d.source;
  $("#urlField").classList.toggle("hidden", SOURCE !== "url");
  $("#fileField").classList.toggle("hidden", SOURCE !== "file");
});
const audioFile = $("#audioFile");
audioFile.addEventListener("change", () => {
  const f = audioFile.files[0];
  $("#fileLabel").textContent = f ? `📄 ${f.name}` : "wav · mp3 · m4a 파일 선택 (10~30초 깨끗한 음성 권장)";
  if (f) $("#cleanChk").checked = true; // uploads are usually already clean
});

// ---------- Train (with live progress via streaming) ----------
$("#trainBtn").addEventListener("click", async () => {
  const name = $("#voiceName").value.trim();
  if (!name) return alert("목소리 이름을 입력해 주세요.");

  const clean = $("#cleanChk").checked;
  let res;
  const btn = $("#trainBtn");
  const log = $("#trainLog");

  const startUI = () => {
    btn.disabled = true; btn.textContent = "학습 중…";
    log.classList.remove("hidden"); log.textContent = "";
    $$("#trainSteps .step").forEach((s) => s.classList.remove("active", "done"));
  };

  try {
    if (SOURCE === "file") {
      const f = audioFile.files[0];
      if (!f) return alert("음성 파일을 선택해 주세요.");
      startUI();
      const fd = new FormData();
      fd.append("file", f);
      fd.append("name", name);
      fd.append("engine", ENGINE);
      fd.append("device", DEVICE);
      fd.append("separate", (!clean).toString());
      res = await fetch("/api/train_upload", { method: "POST", body: fd });
    } else {
      const url = $("#ytUrl").value.trim();
      if (!url) return alert("유튜브 주소를 입력해 주세요.");
      startUI();
      res = await fetch("/api/train", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name, url, engine: ENGINE, device: DEVICE, separate: !clean }),
      });
    }
    // stream newline-delimited JSON events
    const reader = res.body.getReader();
    const dec = new TextDecoder();
    let buf = "";
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buf += dec.decode(value, { stream: true });
      const lines = buf.split("\n");
      buf = lines.pop();
      for (const line of lines) {
        if (!line.trim()) continue;
        const ev = JSON.parse(line);
        if (ev.step) markStep(ev.step, ev.state);
        if (ev.msg) { log.textContent += ev.msg + "\n"; log.scrollTop = log.scrollHeight; }
      }
    }
    loadVoices();
  } catch (e) {
    log.textContent += "\n[오류] " + e.message + "\n";
  } finally {
    btn.disabled = false; btn.textContent = "학습 시작";
  }
});

function markStep(step, state) {
  const el = document.querySelector(`.step[data-step="${step}"]`);
  if (!el) return;
  if (state === "start") el.classList.add("active");
  if (state === "done") { el.classList.remove("active"); el.classList.add("done"); }
}

// ---------- Update (GitHub, git 불필요) ----------
$("#updateBtn").addEventListener("click", async () => {
  const btn = $("#updateBtn"), status = $("#updateStatus");
  btn.disabled = true; status.textContent = "확인 중…";
  try {
    const r = await (await api("/api/update", { method: "POST" })).json();
    status.textContent = r.message + (r.version ? ` [${r.version}]` : "");
  } catch (e) {
    status.textContent = "업데이트 실패: " + e.message;
  } finally {
    btn.disabled = false;
  }
});

// ---------- Download (pywebview: Downloads 폴더로 저장) ----------
let LAST_FILE = null;
async function saveToDownloads(file, msgEl) {
  if (!file) return;
  if (msgEl) msgEl.textContent = "저장 중…";
  try {
    const r = await (await api("/api/download", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ file }),
    })).json();
    const m = "Downloads에 저장됨: " + r.name;
    if (msgEl) msgEl.textContent = m; else alert(m);
  } catch (e) {
    const m = "저장 실패: " + e.message;
    if (msgEl) msgEl.textContent = m; else alert(m);
  }
}
$("#downloadBtn").addEventListener("click", () => saveToDownloads(LAST_FILE, $("#downloadMsg")));

// ---------- Library (보관함) ----------
function esc(s) {
  return (s || "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
}
function fmtDate(iso) {
  try { return new Date(iso).toLocaleString("ko-KR", { dateStyle: "short", timeStyle: "short" }); }
  catch (e) { return iso || ""; }
}
async function loadLibrary() {
  const list = $("#libraryList");
  try {
    const items = await (await api("/api/history")).json();
    if (!items.length) {
      list.innerHTML = '<div class="empty-hint">아직 생성한 음성이 없습니다.</div>';
      return;
    }
    list.innerHTML = "";
    items.forEach((it) => {
      const el = document.createElement("div");
      el.className = "lib-item";
      const engine = it.engine === "sovits" ? "GPT-SoVITS" : "F5-TTS";
      el.innerHTML = `
        <div class="lib-main">
          <div class="lib-text" title="${esc(it.text)}">${esc(it.text)}</div>
          <div class="lib-meta">
            <span class="lib-badge">${esc(it.voice_name || "-")}</span>
            <span class="lib-badge">${engine}</span>
            <span>${fmtDate(it.created)}</span>
          </div>
        </div>
        <audio controls src="${it.url}"></audio>
        <div class="lib-actions">
          <button class="icon-btn dl">다운로드</button>
          <button class="icon-btn danger" data-file="${esc(it.file)}">삭제</button>
        </div>`;
      el.querySelector(".dl").addEventListener("click", () => saveToDownloads(it.file, null));
      el.querySelector(".danger").addEventListener("click", async () => {
        if (!confirm("이 음성을 삭제할까요? 되돌릴 수 없습니다.")) return;
        await api("/api/history/delete", {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ file: it.file }),
        });
        loadLibrary();
      });
      list.appendChild(el);
    });
  } catch (e) {
    list.innerHTML = '<div class="empty-hint">보관함을 불러올 수 없습니다.</div>';
  }
}

// ---------- Fine-tuning (정밀 학습) ----------
let FT_VOICE = null;
async function loadFinetuneVoices() {
  const list = $("#ftVoiceList");
  if (!list) return;
  try {
    const voices = await (await api("/api/voices")).json();
    if (!voices.length) {
      list.innerHTML = '<div class="empty-hint">학습된 목소리가 없습니다.</div>';
      $("#finetuneBtn").disabled = true;
      return;
    }
    list.innerHTML = "";
    for (const v of voices) {
      let info = { clips: 0, mode: "zero-shot" };
      try { info = await (await api("/api/dataset-info?voice=" + encodeURIComponent(v.id))).json(); } catch (e) {}
      const chip = document.createElement("div");
      chip.className = "voice-chip";
      chip.innerHTML = `<span>${esc(v.name)}</span> <small style="opacity:.6">${info.clips}클립·${info.mode === "finetuned" ? "학습됨" : "제로샷"}</small>`;
      chip.addEventListener("click", () => {
        $$("#ftVoiceList .voice-chip").forEach((c) => c.classList.remove("selected"));
        chip.classList.add("selected");
        FT_VOICE = v.id;
        $("#finetuneBtn").disabled = false;
        $("#ftStatus").textContent = info.clips < 3 ? "클립이 적어요. 음성을 더 추가하면 좋습니다." : "";
      });
      list.appendChild(chip);
    }
  } catch (e) {}
}
function markFtStep(step) {
  const el = document.querySelector(`#ftSteps .step[data-step="${step}"]`);
  if (!el) return;
  $$("#ftSteps .step").forEach((s) => { if (s.classList.contains("active")) s.classList.add("done"); s.classList.remove("active"); });
  el.classList.add("active");
}
const _ftBtn = $("#finetuneBtn");
if (_ftBtn) _ftBtn.addEventListener("click", async () => {
  if (!FT_VOICE) return;
  if (!confirm("파인튜닝을 시작할까요? GPU로 수십 분 걸릴 수 있어요.")) return;
  const btn = $("#finetuneBtn"), log = $("#ftLog");
  btn.disabled = true; $("#ftStatus").textContent = "학습 중… (창을 닫지 마세요)";
  log.classList.remove("hidden"); log.textContent = "";
  $$("#ftSteps .step").forEach((s) => s.classList.remove("active", "done"));
  try {
    const res = await fetch("/api/finetune", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ voice: FT_VOICE }),
    });
    const reader = res.body.getReader(); const dec = new TextDecoder(); let buf = "";
    let failed = false;
    while (true) {
      const { value, done } = await reader.read(); if (done) break;
      buf += dec.decode(value, { stream: true });
      const lines = buf.split("\n"); buf = lines.pop();
      for (const ln of lines) {
        if (!ln.trim()) continue;
        const ev = JSON.parse(ln);
        if (ev.step && ev.step !== "error" && ev.step !== "registered") markFtStep(ev.step);
        if (ev.msg) { log.textContent += ev.msg + "\n"; log.scrollTop = log.scrollHeight; }
        if (ev.step === "error") { failed = true; $("#ftStatus").textContent = "실패: " + ev.msg; }
      }
    }
    if (!failed) { $("#ftStatus").textContent = "완료! 이제 이 목소리는 학습된 가중치를 씁니다."; $$("#ftSteps .step").forEach((s) => s.classList.add("done")); }
    loadVoices(); loadFinetuneVoices();
  } catch (e) {
    $("#ftStatus").textContent = "실패: " + e.message;
  } finally {
    btn.disabled = false;
  }
});

// ---------- init ----------
loadVoices();
loadDeviceInfo();
loadFinetuneVoices();
