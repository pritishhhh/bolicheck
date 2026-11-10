"use strict";

const byId = id => document.getElementById(id);
const stateLabels = { pending: "Pending", mismatch: "Mismatch", recount: "Recount", match: "Match" };
const loadLabels = { pending: "Pending", hold: "Hold load", ready: "Ready to confirm", confirmed: "Handoff confirmed" };
const manifestRows = byId("rows");
const activity = byId("activity");
const transcript = byId("transcript");
const audioFile = byId("audio-file");
const playback = byId("playback");
const voiceCode = byId("voice-code");
const samples = {
  crates: { short: "Blue crates चौदह हैं", unclear: "चौदह नहीं, चौबीस", exact: "Blue crates चौबीस हैं" },
  cartons: { short: "Sealed cartons दस हैं", unclear: "दस नहीं, बारह", exact: "Sealed cartons बारह हैं" },
};

let config;
let selected;
let mode = "practice";
let results = {};
let confirmed = false;
let busy = false;
let recorder;
let previewUrl;

function setPill(element, state, label) {
  element.dataset.state = state;
  element.textContent = label;
}

function buildRows() {
  for (const [item, entry] of Object.entries(config.manifest)) {
    const row = document.createElement("button");
    row.type = "button";
    row.className = "row";
    row.dataset.item = item;
    row.innerHTML = '<span><strong></strong><small></small></span><span class="heard"></span><span class="pill"></span>';
    row.querySelector("strong").textContent = entry.label;
    row.querySelector("small").textContent = `Expected ${entry.expected}`;
    row.addEventListener("click", () => {
      selected = item;
      activity.textContent = "";
      transcript.value = samples[item].short;
      clearPlayback();
      render();
    });
    manifestRows.append(row);
  }
}

function render() {
  const items = Object.keys(config.manifest);
  const ready = items.every(item => results[item]?.state === "match");
  const hold = items.some(item => ["mismatch", "recount"].includes(results[item]?.state));
  const loadState = confirmed ? "confirmed" : hold ? "hold" : ready ? "ready" : "pending";
  setPill(byId("load-status"), loadState, loadLabels[loadState]);
  byId("confirm").disabled = busy || confirmed || !ready;
  byId("reset").disabled = busy;
  byId("receipt").textContent = confirmed
    ? `Handoff confirmed · ${mode === "voice" ? "Gnani speech" : "Practice"}`
    : "Confirm after physically checking both counts.";

  for (const row of manifestRows.children) {
    const item = row.dataset.item;
    const result = results[item];
    const status = result?.state || "pending";
    row.setAttribute("aria-pressed", String(item === selected));
    row.disabled = busy;
    row.querySelector(".heard").textContent = result?.heard == null ? "—" : `Heard ${result.heard}`;
    setPill(row.querySelector(".pill"), status, stateLabels[status]);
  }

  byId("target").textContent = `Counting ${config.manifest[selected].label.toLowerCase()}`;
  for (const inputMode of ["voice", "practice"]) {
    byId(`${inputMode}-mode`).setAttribute("aria-pressed", String(mode === inputMode));
    byId(`${inputMode}-mode`).disabled = busy;
    byId(`${inputMode}-panel`).hidden = mode !== inputMode;
  }
  byId("voice-help").textContent = config.live
    ? "Record one final count, or upload a short WAV or MP3. Audio is sent to Gnani for transcription. Use a synthetic scenario."
    : config.hosted ? "Live speech is unavailable. Use Practice to try the count checks." : "Restart with --live to enter your Gnani API key and enable audio.";
  byId("voice-access").hidden = !config.hosted || !config.live;
  voiceCode.disabled = busy;
  const voiceReady = config.live && (!config.hosted || Boolean(voiceCode.value.trim()));
  byId("record").textContent = recorder ? "Stop and check" : "Record count";
  byId("record").disabled = !voiceReady || confirmed || (busy && !recorder) || !window.MediaRecorder;
  audioFile.disabled = !voiceReady || confirmed || busy;
  byId("upload-label").setAttribute("aria-disabled", String(audioFile.disabled));
  transcript.disabled = byId("check").disabled = busy || confirmed;
  for (const button of document.querySelectorAll("[data-sample]")) button.disabled = busy || confirmed;

  const result = results[selected];
  byId("result").hidden = !result;
  if (!result) return;
  byId("result").dataset.state = result.state;
  byId("result-state").textContent = stateLabels[result.state];
  byId("result-source").textContent = result.source;
  byId("result-detail").textContent = result.detail;
  byId("result-transcript").textContent = result.transcript ? `“${result.transcript}”` : "";
}

function clearPlayback() {
  if (previewUrl) URL.revokeObjectURL(previewUrl);
  previewUrl = undefined;
  playback.removeAttribute("src");
  playback.hidden = true;
}

function reset() {
  results = {};
  confirmed = false;
  selected = Object.keys(config.manifest)[0];
  transcript.value = samples[selected].short;
  activity.textContent = "";
  clearPlayback();
  render();
}

function startCheck(message) {
  busy = true;
  delete results[selected];
  activity.textContent = message;
  clearPlayback();
  render();
}

function endCheck() {
  busy = false;
  render();
}

async function submitCount(endpoint, type, body) {
  const headers = { "Content-Type": type };
  if (config.hosted && endpoint === "voice") headers["X-BoliCheck-Voice-Code"] = voiceCode.value.trim();
  const response = await fetch(`/api/dispatch?action=${endpoint}&item=${selected}`, {
    method: "POST",
    headers,
    body,
  });
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.error);
  results[selected] = payload;
  activity.textContent = "";
}

async function toWav(clip) {
  const context = new AudioContext();
  let decoded;
  try {
    decoded = await context.decodeAudioData(await clip.arrayBuffer());
  } catch {
    throw new Error("This browser could not read the clip. Try a short WAV or MP3.");
  } finally {
    await context.close();
  }
  if (decoded.duration > 30) throw new Error("Keep each clip under 30 seconds.");
  const sampleRate = 16000;
  const frameCount = Math.ceil(decoded.duration * sampleRate);
  const offline = new OfflineAudioContext(1, frameCount, sampleRate);
  const source = offline.createBufferSource();
  source.buffer = decoded;
  source.connect(offline.destination);
  source.start();
  const signal = (await offline.startRendering()).getChannelData(0);
  const bytes = new ArrayBuffer(44 + frameCount * 2);
  const view = new DataView(bytes);
  for (const [start, label] of [[0, "RIFF"], [8, "WAVE"], [12, "fmt "], [36, "data"]]) {
    [...label].forEach((char, offset) => view.setUint8(start + offset, char.charCodeAt(0)));
  }
  view.setUint32(4, bytes.byteLength - 8, true);
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true);
  view.setUint16(22, 1, true);
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, sampleRate * 2, true);
  view.setUint16(32, 2, true);
  view.setUint16(34, 16, true);
  view.setUint32(40, frameCount * 2, true);
  signal.forEach((value, index) => {
    const sample = Math.max(-1, Math.min(1, value));
    view.setInt16(44 + index * 2, sample * (sample < 0 ? 32768 : 32767), true);
  });
  return new Blob([bytes], { type: "audio/wav" });
}

async function checkClip(clip) {
  activity.textContent = "Transcribing with Gnani…";
  try {
    if (clip.size > 10_000_000) throw new Error("Choose a short audio file under 10 MB.");
    const wav = await toWav(clip);
    previewUrl = URL.createObjectURL(wav);
    playback.src = previewUrl;
    playback.hidden = false;
    await submitCount("voice", "audio/wav", wav);
  } catch (error) {
    activity.textContent = error.message;
  } finally {
    endCheck();
  }
}

async function recordCount() {
  if (recorder) {
    if (recorder.state === "recording") recorder.stop();
    return;
  }
  startCheck("Opening microphone…");
  let stream;
  try {
    stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    recorder = new MediaRecorder(stream);
    const chunks = [];
    let failed = false;
    const timer = setTimeout(() => {
      if (recorder?.state === "recording") recorder.stop();
    }, 12000);
    recorder.addEventListener("dataavailable", event => chunks.push(event.data));
    recorder.addEventListener("error", () => {
      failed = true;
      activity.textContent = "Recording failed. Try again or upload an audio file.";
    });
    recorder.addEventListener("stop", () => {
      clearTimeout(timer);
      for (const track of stream.getTracks()) track.stop();
      const clip = new Blob(chunks, { type: recorder.mimeType });
      recorder = undefined;
      if (failed) endCheck();
      else {
        render();
        checkClip(clip);
      }
    });
    recorder.start();
    activity.textContent = "Recording. Speak one final count, then stop.";
    render();
  } catch {
    for (const track of stream?.getTracks() || []) track.stop();
    recorder = undefined;
    activity.textContent = "The microphone is unavailable. Allow access or upload an audio file.";
    endCheck();
  }
}

async function initialize() {
  const response = await fetch("/api/dispatch?action=config");
  if (!response.ok) throw new Error("Configuration unavailable.");
  config = await response.json();
  mode = config.live && !config.hosted ? "voice" : "practice";
  buildRows();
  reset();

  for (const inputMode of ["voice", "practice"]) {
    byId(`${inputMode}-mode`).addEventListener("click", () => {
      if (inputMode === mode) return;
      mode = inputMode;
      reset();
    });
  }
  byId("reset").addEventListener("click", reset);
  byId("confirm").addEventListener("click", () => {
    confirmed = true;
    render();
  });
  for (const button of document.querySelectorAll("[data-sample]")) {
    button.addEventListener("click", () => { transcript.value = samples[selected][button.dataset.sample]; });
  }
  byId("practice-panel").addEventListener("submit", async event => {
    event.preventDefault();
    const body = JSON.stringify({ transcript: transcript.value });
    startCheck("Checking transcript…");
    try {
      await submitCount("count", "application/json", body);
    } catch (error) {
      activity.textContent = error.message;
    } finally {
      endCheck();
    }
  });
  byId("record").addEventListener("click", recordCount);
  voiceCode.addEventListener("input", render);
  audioFile.addEventListener("change", () => {
    const clip = audioFile.files[0];
    audioFile.value = "";
    if (!clip) return;
    startCheck("Preparing clip…");
    checkClip(clip);
  });
}

initialize().catch(() => { activity.textContent = "Could not load the manifest. Restart BoliCheck and reload this page."; });
