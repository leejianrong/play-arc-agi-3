// Live speech capture + transcript panel (ADR-0006). Owns the mic, the /ws/audio socket and the
// DOM of the transcript panel. Every failure here is reported in the panel and never thrown into
// the game: play, recording and (later) typed notes must keep working without a mic or model.
import { Chunker, Resampler, TAG_OPUS, TAG_PCM, TARGET_RATE, floatToPcm16, rms, tagFrame } from "/static/audio_utils.js";

export function createAnnotationUI(panelEl) {
  const statusEl = panelEl.querySelector("[data-role=status]");
  const meterEl = panelEl.querySelector("[data-role=meter-fill]");
  const finalsEl = panelEl.querySelector("[data-role=finals]");
  const interimEl = panelEl.querySelector("[data-role=interim]");
  const bannerEl = panelEl.querySelector("[data-role=banner]");

  let socket = null;
  let stream = null;
  let audioCtx = null;
  let recorder = null;
  let capturing = false;
  let generation = 0;

  function setStatus(text) {
    statusEl.textContent = text;
  }

  function banner(text) {
    bannerEl.textContent = text;
    bannerEl.style.display = text ? "block" : "none";
  }

  function addFinal(message) {
    const row = document.createElement("div");
    row.className = "final";
    row.dataset.eventId = message.event_id;
    const steps = document.createElement("span");
    steps.className = "steps";
    steps.textContent =
      message.step_at_start === message.step_at_end
        ? `step ${message.step_at_end}`
        : `steps ${message.step_at_start}→${message.step_at_end}`;
    const text = document.createElement("span");
    text.textContent = message.text;
    row.append(steps, text);
    finalsEl.appendChild(row);
    finalsEl.scrollTop = finalsEl.scrollHeight;
    interimEl.textContent = "";
  }

  function onServerMessage(message) {
    if (message.type === "status") {
      if (message.state === "loading") setStatus("loading speech model… (first run downloads it)");
      else if (message.state === "ready") beginCapture(`listening · ${message.engine}`);
    } else if (message.type === "interim") {
      interimEl.textContent = message.text;
    } else if (message.type === "final") {
      addFinal(message);
    } else if (message.type === "discard") {
      interimEl.textContent = "";
    } else if (message.type === "error") {
      banner(`Speech: ${message.message}`);
      // No model: keep recording raw audio so nothing is lost; there is just no live text.
      if (message.code === "stt_unavailable") beginCapture("no live transcript · audio only");
    }
  }

  async function beginCapture(statusText) {
    if (capturing) return;
    capturing = true;
    const myGeneration = generation;
    try {
      stream = await navigator.mediaDevices.getUserMedia({
        audio: { echoCancellation: false, noiseSuppression: false, channelCount: 1 },
      });
      if (myGeneration !== generation) return stopMedia();
      audioCtx = new AudioContext();
      await audioCtx.audioWorklet.addModule("/static/audio_worklet.js");
      const source = audioCtx.createMediaStreamSource(stream);
      const node = new AudioWorkletNode(audioCtx, "capture");
      const resampler = new Resampler(audioCtx.sampleRate, TARGET_RATE);
      const chunker = new Chunker();
      node.port.onmessage = (event) => {
        const block = event.data;
        meterEl.style.width = `${Math.min(100, Math.round(rms(block) * 400))}%`;
        for (const chunk of chunker.push(resampler.process(block))) {
          if (socket && socket.readyState === WebSocket.OPEN) socket.send(tagFrame(TAG_PCM, floatToPcm16(chunk)));
        }
      };
      source.connect(node);
      // The worklet needs a path to the destination to be pulled; mute it so we never echo the mic.
      const silent = audioCtx.createGain();
      silent.gain.value = 0;
      node.connect(silent).connect(audioCtx.destination);

      const mime = ["audio/webm;codecs=opus", "audio/webm"].find((t) => MediaRecorder.isTypeSupported(t));
      if (mime) {
        recorder = new MediaRecorder(stream, { mimeType: mime });
        recorder.ondataavailable = async (event) => {
          if (event.data.size && socket && socket.readyState === WebSocket.OPEN) {
            socket.send(tagFrame(TAG_OPUS, await event.data.arrayBuffer()));
          }
        };
        recorder.start(1000);
      }
      socket.send(JSON.stringify({ type: "audio_start" }));
      setStatus(statusText);
    } catch (err) {
      capturing = false;
      banner(`Microphone unavailable: ${err.message || err}. Play and recording continue.`);
      setStatus("mic off");
    }
  }

  function stopMedia() {
    capturing = false;
    if (recorder && recorder.state !== "inactive") recorder.stop();
    recorder = null;
    if (stream) stream.getTracks().forEach((t) => t.stop());
    stream = null;
    if (audioCtx) audioCtx.close();
    audioCtx = null;
    meterEl.style.width = "0%";
  }

  return {
    start(sessionId) {
      this.stop();
      generation += 1;
      panelEl.style.display = "flex";
      finalsEl.textContent = "";
      interimEl.textContent = "";
      banner("");
      setStatus("connecting…");
      socket = new WebSocket(`ws://${location.host}/ws/audio?session=${encodeURIComponent(sessionId)}`);
      socket.binaryType = "arraybuffer";
      socket.addEventListener("message", (event) => onServerMessage(JSON.parse(event.data)));
      socket.addEventListener("close", () => setStatus("speech connection closed"));
    },
    stop() {
      generation += 1;
      stopMedia();
      if (socket) {
        socket.close();
        socket = null;
      }
      panelEl.style.display = "none";
    },
  };
}
