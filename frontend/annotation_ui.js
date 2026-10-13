// Live annotation: speech capture + transcript panel, typed notes, phase chips, mute (ADR-0006,
// ADR-0008). Owns the mic, the /ws/audio socket and the panel DOM. Every failure here is reported in
// the panel and never thrown into the game: play, recording and typed notes must keep working
// without a mic or model.
import { Chunker, Resampler, TAG_OPUS, TAG_PCM, TARGET_RATE, floatToPcm16, meterPercent, rms, tagFrame } from "/static/audio_utils.js";
import { PHASES } from "/static/hotkeys.js";

const FLUSH_TIMEOUT_MS = 8000;

export function createAnnotationUI(
  panelEl,
  { sendNote, sendPhase, sendHypothesisAdd, sendHypothesisSelect, sendVerdict, sendDictate },
) {
  const statusEl = panelEl.querySelector("[data-role=status]");
  const meterEl = panelEl.querySelector("[data-role=meter-fill]");
  const muteEl = panelEl.querySelector("[data-role=mute]");
  const phasesEl = panelEl.querySelector("[data-role=phases]");
  const finalsEl = panelEl.querySelector("[data-role=finals]");
  const interimEl = panelEl.querySelector("[data-role=interim]");
  const bannerEl = panelEl.querySelector("[data-role=banner]");
  const noteEl = panelEl.querySelector("[data-role=note]");
  const hypListEl = panelEl.querySelector("[data-role=hyp-list]");
  const hypEmptyEl = panelEl.querySelector("[data-role=hyp-empty]");
  const hypAddEl = panelEl.querySelector("[data-role=hyp-add]");
  const dictateEl = panelEl.querySelector("[data-role=dictate]");
  const dictatingEl = panelEl.querySelector("[data-role=hyp-dictating]");
  let dictating = false;
  const promptEl = panelEl.querySelector("[data-role=prompt]");
  const promptTextEl = panelEl.querySelector("[data-role=prompt-text]");
  promptEl.querySelector("[data-role=prompt-dismiss]").addEventListener("click", () => hidePrompt());

  let socket = null;
  let stream = null;
  let audioCtx = null;
  let recorder = null;
  let capturing = false;
  let muted = false;
  let active = false;
  let generation = 0;
  let flushWaiter = null;

  const phaseChips = new Map();
  for (const [i, phase] of PHASES.entries()) {
    const chip = document.createElement("button");
    chip.type = "button";
    chip.className = "phase-chip";
    chip.dataset.phase = phase;
    chip.textContent = `${i + 1} ${phase}`;
    chip.tabIndex = -1; // keep keyboard focus on the game
    chip.addEventListener("click", () => sendPhase(phase));
    phasesEl.appendChild(chip);
    phaseChips.set(phase, chip);
  }

  // The add box stays focused after Enter so several hypotheses can be entered in a row; Esc hands
  // the keyboard back to the game.
  hypAddEl.addEventListener("keydown", (event) => {
    event.stopPropagation();
    if (event.key === "Enter") {
      const text = hypAddEl.value.trim();
      if (text) sendHypothesisAdd(text);
      hypAddEl.value = "";
    } else if (event.key === "Escape") {
      hypAddEl.value = "";
      hypAddEl.blur();
    }
  });
  dictateEl.addEventListener("click", () => {
    sendDictate(!dictating);
    dictateEl.blur();
  });
  dictatingEl.querySelector("button").addEventListener("click", () => {
    sendDictate(false);
    document.activeElement.blur();
  });

  noteEl.addEventListener("keydown", (event) => {
    event.stopPropagation(); // typing must never reach the game or the hotkeys
    if (event.key === "Enter") {
      const text = noteEl.value.trim();
      if (text) sendNote(text);
      noteEl.value = "";
      noteEl.blur();
    } else if (event.key === "Escape") {
      noteEl.value = "";
      noteEl.blur();
    }
  });

  function hidePrompt() {
    promptEl.style.display = "none";
  }

  function showPrompt(text) {
    promptTextEl.textContent = text;
    promptEl.style.display = "flex";
  }

  function onServerMessageHypotheses(message) {
    ui.setHypotheses(message);
  }

  function setStatus(text) {
    statusEl.textContent = text;
  }

  function banner(text) {
    bannerEl.textContent = text;
    bannerEl.style.display = text ? "block" : "none";
  }

  function stepsLabel(startStep, endStep) {
    return startStep === endStep ? `step ${endStep}` : `steps ${startStep}→${endStep}`;
  }

  function addRow({ eventId, label, text, typed }) {
    const row = document.createElement("div");
    row.className = typed ? "final typed" : "final";
    row.dataset.eventId = eventId;
    const steps = document.createElement("span");
    steps.className = "steps";
    steps.textContent = label;
    const body = document.createElement("span");
    body.textContent = text;
    row.append(steps, body);
    finalsEl.appendChild(row);
    finalsEl.scrollTop = finalsEl.scrollHeight;
  }

  function renderMuted() {
    muteEl.textContent = muted ? "muted (M)" : "mic on (M)";
    muteEl.classList.toggle("is-muted", muted);
    if (muted) meterEl.style.width = "0%";
  }

  function onServerMessage(message) {
    if (message.type === "status") {
      if (message.state === "loading") setStatus("loading speech model… (first run downloads it)");
      else if (message.state === "ready") beginCapture(`listening · ${message.engine}`);
    } else if (message.type === "interim") {
      if (!muted) interimEl.textContent = message.text;
    } else if (message.type === "final") {
      interimEl.textContent = "";
      addRow({
        eventId: message.event_id,
        label: stepsLabel(message.step_at_start, message.step_at_end),
        text: message.text,
      });
    } else if (message.type === "discard") {
      interimEl.textContent = "";
    } else if (message.type === "mute") {
      muted = message.muted;
      renderMuted();
    } else if (message.type === "hypothesis_state") {
      onServerMessageHypotheses(message);
    } else if (message.type === "flushed") {
      if (flushWaiter) flushWaiter();
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
        if (muted) return; // a muted mic sends nothing, and the meter stays flat
        const block = event.data;
        meterEl.style.width = `${meterPercent(rms(block))}%`;
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
          if (!muted && event.data.size && socket && socket.readyState === WebSocket.OPEN) {
            socket.send(tagFrame(TAG_OPUS, await event.data.arrayBuffer()));
          }
        };
        recorder.start(1000);
      }
      socket.send(JSON.stringify({ type: "audio_start" }));
      setStatus(statusText);
    } catch (err) {
      capturing = false;
      banner(`Microphone unavailable: ${err.message || err}. Play, recording and typed notes continue.`);
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

  function closeSocket() {
    if (socket) {
      socket.close();
      socket = null;
    }
  }

  function actionButton(label, className, title, onClick) {
    const button = document.createElement("button");
    button.type = "button";
    button.tabIndex = -1; // keep keyboard focus on the game
    button.className = className;
    button.textContent = label;
    button.title = title;
    button.addEventListener("click", (event) => {
      event.stopPropagation(); // don't also select the row
      onClick();
      button.blur(); // Space/Enter must keep acting in the game, not re-press this button
    });
    return button;
  }

  function buildRow(h, selected) {
    const row = document.createElement("div");
    row.className = `hyp-row ${h.status}${selected ? " is-selected" : ""}`;
    row.dataset.hypothesisId = h.id;
    row.dataset.status = h.status;
    row.title = `${h.id}, stated at step ${h.step}. Click to mark it as the one you're testing.`;
    row.addEventListener("click", () => sendHypothesisSelect(h.id));

    const id = document.createElement("span");
    id.className = "hyp-id";
    id.textContent = h.id;
    const text = document.createElement("span");
    text.className = "hyp-text";
    text.textContent = h.statement;
    row.append(id, text);

    const badge = document.createElement("span");
    const badgeFor = { confirmed: ["TRUE", "true"], refuted: ["FALSE", "false"] }[h.status] ||
      (selected ? ["testing", "testing"] : null);
    if (badgeFor) {
      badge.textContent = badgeFor[0];
      badge.className = `badge ${badgeFor[1]}`;
      row.appendChild(badge);
    }

    const actions = document.createElement("span");
    actions.className = "hyp-actions";
    actions.append(
      actionButton("\u2713 true", `yes${h.status === "confirmed" ? " is-active" : ""}`, "This hypothesis is true", () =>
        sendVerdict(h.id, "confirmed"),
      ),
      actionButton("\u2717 false", `no${h.status === "refuted" ? " is-active" : ""}`, "This hypothesis is false", () =>
        sendVerdict(h.id, "refuted"),
      ),
    );
    if (h.status !== "open") {
      actions.append(actionButton("\u21ba", "reset", "Not sure after all: back to open", () => sendVerdict(h.id, "open")));
    }
    row.appendChild(actions);
    return row;
  }

  const ui = {
    get active() {
      return active;
    },

    start(sessionId) {
      this.stop();
      generation += 1;
      active = true;
      muted = false;
      renderMuted();
      this.setPhase("observe");
      this.setHypotheses({ hypotheses: [], selected: null, pending: false, batch: false });
      hypAddEl.value = "";
      hidePrompt();
      panelEl.style.display = "flex";
      finalsEl.textContent = "";
      interimEl.textContent = "";
      noteEl.value = "";
      banner("");
      setStatus("connecting…");
      socket = new WebSocket(`ws://${location.host}/ws/audio?session=${encodeURIComponent(sessionId)}`);
      socket.binaryType = "arraybuffer";
      socket.addEventListener("message", (event) => onServerMessage(JSON.parse(event.data)));
      socket.addEventListener("close", () => active && setStatus("speech connection closed"));
    },

    stop() {
      generation += 1;
      active = false;
      stopMedia();
      closeSocket();
      panelEl.style.display = "none";
    },

    // End of session: stop the mic, have the server finish the sentence in progress, then close.
    async finish() {
      if (!active) return;
      stopMedia();
      if (socket && socket.readyState === WebSocket.OPEN) {
        await new Promise((resolve) => {
          flushWaiter = resolve;
          setTimeout(resolve, FLUSH_TIMEOUT_MS);
          socket.send(JSON.stringify({ type: "audio_end" }));
        });
        flushWaiter = null;
      }
      this.stop();
    },

    toggleMute() {
      if (!active || !socket || socket.readyState !== WebSocket.OPEN) return;
      muted = !muted;
      renderMuted();
      if (muted && recorder && recorder.state === "recording") recorder.pause();
      if (!muted && recorder && recorder.state === "paused") recorder.resume();
      socket.send(JSON.stringify({ type: "mute", muted }));
      if (muted) interimEl.textContent = "";
    },

    focusNote() {
      if (active) noteEl.focus();
    },

    setPhase(phase) {
      for (const [name, chip] of phaseChips) chip.classList.toggle("is-current", name === phase);
      panelEl.dataset.phase = phase;
      // The level-clear prompt invites a reflection; once you're reflecting it just coaches, and any
      // other phase means you've moved on.
      if (phase === "reflect") {
        showPrompt("Reflecting: what was the rule, what misled you, what would be faster? Press 1 to observe the next level.");
      } else {
        hidePrompt();
      }
    },

    showLevelCleared(level) {
      showPrompt(`Level ${level} cleared. Press 5 and say the rule, what misled you, and what would be faster.`);
    },

    focusHypothesisInput() {
      if (active) hypAddEl.focus();
    },

    get dictating() {
      return dictating;
    },

    setHypotheses(state) {
      dictating = Boolean(state.batch);
      dictateEl.classList.toggle("is-on", dictating);
      dictateEl.innerHTML = dictating ? "&#9209; stop dictating (V)" : "&#127897; dictate (V)";
      dictatingEl.style.display = dictating ? "flex" : "none";
      hypEmptyEl.style.display = state.hypotheses.length === 0 ? "block" : "none";
      hypListEl.textContent = "";
      for (const h of state.hypotheses) hypListEl.appendChild(buildRow(h, h.id === state.selected));
    },

    addNote(message) {
      addRow({
        eventId: message.event_id,
        label: `${stepsLabel(message.step_at_end, message.step_at_end)} ✎`,
        text: message.text,
        typed: true,
      });
    },
  };
  return ui;
}
