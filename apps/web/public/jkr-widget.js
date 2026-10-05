(function () {
  'use strict';

  // Prevent multiple injections
  if (window.__JKR_WIDGET_INITIALIZED__) return;
  window.__JKR_WIDGET_INITIALIZED__ = true;

  // Find the active script tag to extract data-* config attributes
  const currentScript =
    document.currentScript ||
    document.querySelector('script[data-agent-id]') ||
    document.querySelector('script[src*="jkr-widget.js"]');

  const defaultConfig = {
    agentId: currentScript ? currentScript.getAttribute('data-agent-id') : null,
    apiBase: currentScript ? (currentScript.getAttribute('data-api-base') || '').replace(/\/$/, '') : '',
    themeColor: currentScript ? (currentScript.getAttribute('data-theme-color') || '#4f46e5') : '#4f46e5',
    position: currentScript ? (currentScript.getAttribute('data-position') || 'bottom-right') : 'bottom-right',
    language: currentScript ? (currentScript.getAttribute('data-language') || 'te-IN') : 'te-IN',
    greeting: currentScript ? currentScript.getAttribute('data-greeting') : null,
    autoOpen: currentScript ? currentScript.getAttribute('data-auto-open') === 'true' : false,
  };

  // If apiBase is empty, default to current origin or fallback API host
  if (!defaultConfig.apiBase) {
    if (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1') {
      defaultConfig.apiBase = 'http://localhost:8000';
    } else {
      defaultConfig.apiBase = 'https://jkr-calling-api.onrender.com';
    }
  }

  let state = {
    isOpen: false,
    isListening: false,
    isPlayingAudio: false,
    audioMuted: false,
    sessionId: null,
    config: { ...defaultConfig },
    agentInfo: null,
    messages: [],
    currentLanguage: defaultConfig.language,
    recognition: null,
    audioElement: null,
  };

  // Stylesheet injection
  const css = `
    .jkr-widget-root * {
      box-sizing: border-box;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
      margin: 0;
      padding: 0;
    }
    .jkr-widget-root {
      position: fixed;
      z-index: 9999999;
      bottom: 24px;
      ${defaultConfig.position === 'bottom-left' ? 'left: 24px;' : 'right: 24px;'}
      display: flex;
      flex-direction: column;
      align-items: ${defaultConfig.position === 'bottom-left' ? 'flex-start' : 'flex-end'};
    }
    .jkr-widget-launcher {
      display: flex;
      align-items: center;
      gap: 12px;
      padding: 12px 20px;
      background: ${state.config.themeColor};
      color: #ffffff;
      border: none;
      border-radius: 9999px;
      cursor: pointer;
      box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.3), 0 8px 10px -6px rgba(0, 0, 0, 0.2);
      transition: all 0.25s cubic-bezier(0.16, 1, 0.3, 1);
      outline: none;
    }
    .jkr-widget-launcher:hover {
      transform: scale(1.05);
      box-shadow: 0 14px 28px -4px rgba(0, 0, 0, 0.35);
    }
    .jkr-widget-pulse-ring {
      position: relative;
      width: 12px;
      height: 12px;
      background-color: #22c55e;
      border-radius: 50%;
    }
    .jkr-widget-pulse-ring::after {
      content: '';
      position: absolute;
      top: -4px;
      left: -4px;
      width: 20px;
      height: 20px;
      border-radius: 50%;
      border: 2px solid #22c55e;
      animation: jkr-pulse 1.8s infinite;
    }
    @keyframes jkr-pulse {
      0% { transform: scale(0.6); opacity: 1; }
      100% { transform: scale(1.6); opacity: 0; }
    }
    .jkr-widget-launcher-text {
      font-weight: 600;
      font-size: 14px;
      letter-spacing: -0.01em;
    }
    .jkr-widget-window {
      position: relative;
      width: 380px;
      max-width: calc(100vw - 32px);
      height: 580px;
      max-height: calc(100vh - 120px);
      background: #0f172a;
      color: #f8fafc;
      border: 1px solid rgba(255, 255, 255, 0.12);
      border-radius: 20px;
      box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.6);
      display: none;
      flex-direction: column;
      overflow: hidden;
      margin-bottom: 16px;
      animation: jkr-slide-up 0.3s cubic-bezier(0.16, 1, 0.3, 1);
    }
    .jkr-widget-window.active {
      display: flex;
    }
    @keyframes jkr-slide-up {
      from { opacity: 0; transform: translateY(20px) scale(0.96); }
      to { opacity: 1; transform: translateY(0) scale(1); }
    }
    .jkr-widget-header {
      padding: 16px 20px;
      background: linear-gradient(135deg, ${state.config.themeColor}dd, #1e1b4b);
      border-bottom: 1px solid rgba(255, 255, 255, 0.1);
      display: flex;
      align-items: center;
      justify-content: space-between;
    }
    .jkr-widget-header-info {
      display: flex;
      align-items: center;
      gap: 12px;
    }
    .jkr-widget-avatar {
      width: 40px;
      height: 40px;
      border-radius: 12px;
      background: rgba(255, 255, 255, 0.15);
      backdrop-filter: blur(8px);
      display: flex;
      align-items: center;
      justify-content: center;
      font-size: 20px;
      border: 1px solid rgba(255, 255, 255, 0.2);
    }
    .jkr-widget-title-area {
      display: flex;
      flex-direction: column;
    }
    .jkr-widget-agent-name {
      font-weight: 700;
      font-size: 15px;
      color: #ffffff;
      line-height: 1.2;
    }
    .jkr-widget-status-badge {
      display: flex;
      align-items: center;
      gap: 5px;
      font-size: 11px;
      color: #a7f3d0;
      margin-top: 2px;
    }
    .jkr-widget-status-dot {
      width: 6px;
      height: 6px;
      background: #10b981;
      border-radius: 50%;
    }
    .jkr-widget-header-actions {
      display: flex;
      align-items: center;
      gap: 8px;
    }
    .jkr-widget-icon-btn {
      background: rgba(255, 255, 255, 0.1);
      border: none;
      color: #ffffff;
      width: 30px;
      height: 30px;
      border-radius: 8px;
      cursor: pointer;
      display: flex;
      align-items: center;
      justify-content: center;
      transition: background 0.15s;
    }
    .jkr-widget-icon-btn:hover {
      background: rgba(255, 255, 255, 0.2);
    }
    .jkr-widget-lang-bar {
      padding: 8px 16px;
      background: #1e293b;
      display: flex;
      gap: 8px;
      border-bottom: 1px solid rgba(255, 255, 255, 0.05);
      overflow-x: auto;
    }
    .jkr-widget-lang-chip {
      font-size: 11px;
      padding: 3px 10px;
      border-radius: 999px;
      border: 1px solid rgba(255, 255, 255, 0.1);
      background: transparent;
      color: #94a3b8;
      cursor: pointer;
      white-space: nowrap;
      transition: all 0.15s;
    }
    .jkr-widget-lang-chip.active {
      background: ${state.config.themeColor};
      color: #ffffff;
      border-color: ${state.config.themeColor};
      font-weight: 600;
    }
    .jkr-widget-body {
      flex: 1;
      overflow-y: auto;
      padding: 16px;
      display: flex;
      flex-direction: column;
      gap: 12px;
    }
    .jkr-msg {
      max-width: 82%;
      padding: 10px 14px;
      font-size: 13.5px;
      line-height: 1.45;
      border-radius: 14px;
      word-wrap: break-word;
    }
    .jkr-msg-agent {
      align-self: flex-start;
      background: #1e293b;
      color: #f1f5f9;
      border: 1px solid rgba(255, 255, 255, 0.08);
      border-bottom-left-radius: 4px;
    }
    .jkr-msg-user {
      align-self: flex-end;
      background: ${state.config.themeColor};
      color: #ffffff;
      border-bottom-right-radius: 4px;
    }
    .jkr-card-appointment {
      align-self: stretch;
      background: linear-gradient(135deg, rgba(16, 185, 129, 0.15), rgba(5, 150, 105, 0.05));
      border: 1px solid #10b981;
      border-radius: 12px;
      padding: 12px 14px;
      color: #d1fae5;
      font-size: 12.5px;
      display: flex;
      align-items: center;
      gap: 10px;
    }
    .jkr-widget-voice-viz {
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 4px;
      padding: 6px;
      background: rgba(30, 41, 59, 0.7);
      border-radius: 8px;
      margin-top: 4px;
    }
    .jkr-viz-bar {
      width: 3px;
      height: 12px;
      background: ${state.config.themeColor};
      border-radius: 2px;
      animation: jkr-bounce 1s infinite ease-in-out;
    }
    .jkr-viz-bar:nth-child(2) { animation-delay: 0.15s; }
    .jkr-viz-bar:nth-child(3) { animation-delay: 0.3s; }
    .jkr-viz-bar:nth-child(4) { animation-delay: 0.45s; }
    .jkr-viz-bar:nth-child(5) { animation-delay: 0.6s; }
    @keyframes jkr-bounce {
      0%, 100% { height: 6px; }
      50% { height: 18px; }
    }
    .jkr-widget-footer {
      padding: 12px 16px;
      background: #0b1120;
      border-top: 1px solid rgba(255, 255, 255, 0.08);
      display: flex;
      align-items: center;
      gap: 8px;
    }
    .jkr-widget-input {
      flex: 1;
      background: #1e293b;
      border: 1px solid rgba(255, 255, 255, 0.1);
      border-radius: 10px;
      color: #ffffff;
      padding: 10px 14px;
      font-size: 13.5px;
      outline: none;
      transition: border 0.15s;
    }
    .jkr-widget-input:focus {
      border-color: ${state.config.themeColor};
    }
    .jkr-mic-btn {
      width: 40px;
      height: 40px;
      border-radius: 10px;
      background: #1e293b;
      border: 1px solid rgba(255, 255, 255, 0.1);
      color: #e2e8f0;
      cursor: pointer;
      display: flex;
      align-items: center;
      justify-content: center;
      transition: all 0.2s;
    }
    .jkr-mic-btn.listening {
      background: #ef4444;
      color: #ffffff;
      border-color: #ef4444;
      animation: jkr-pulse-red 1.2s infinite;
    }
    @keyframes jkr-pulse-red {
      0% { box-shadow: 0 0 0 0 rgba(239, 68, 68, 0.7); }
      70% { box-shadow: 0 0 0 10px rgba(239, 68, 68, 0); }
      100% { box-shadow: 0 0 0 0 rgba(239, 68, 68, 0); }
    }
    .jkr-send-btn {
      width: 40px;
      height: 40px;
      border-radius: 10px;
      background: ${state.config.themeColor};
      border: none;
      color: #ffffff;
      cursor: pointer;
      display: flex;
      align-items: center;
      justify-content: center;
      transition: transform 0.15s;
    }
    .jkr-send-btn:hover {
      transform: scale(1.05);
    }
    .jkr-powered-by {
      text-align: center;
      padding: 6px;
      font-size: 10px;
      color: #64748b;
      background: #070c18;
      border-top: 1px solid rgba(255, 255, 255, 0.03);
    }
    .jkr-powered-by a {
      color: #94a3b8;
      text-decoration: none;
      font-weight: 600;
    }
  `;

  // Inject CSS style element
  const styleEl = document.createElement('style');
  styleEl.type = 'text/css';
  styleEl.appendChild(document.createTextNode(css));
  document.head.appendChild(styleEl);

  // Setup UI elements
  const root = document.createElement('div');
  root.className = 'jkr-widget-root';

  root.innerHTML = `
    <div class="jkr-widget-window" id="jkrWidgetWindow">
      <div class="jkr-widget-header">
        <div class="jkr-widget-header-info">
          <div class="jkr-widget-avatar">🤖</div>
          <div class="jkr-widget-title-area">
            <span class="jkr-widget-agent-name" id="jkrAgentName">AI Assistant</span>
            <div class="jkr-widget-status-badge">
              <span class="jkr-widget-status-dot"></span>
              <span id="jkrAgentStatus">Online • Dograh Voice</span>
            </div>
          </div>
        </div>
        <div class="jkr-widget-header-actions">
          <button class="jkr-widget-icon-btn" id="jkrMuteBtn" title="Toggle Voice Audio">🔊</button>
          <button class="jkr-widget-icon-btn" id="jkrCloseBtn" title="Close">✕</button>
        </div>
      </div>
      <div class="jkr-widget-lang-bar">
        <button class="jkr-widget-lang-chip active" data-lang="te-IN">తెలుగు (Telugu)</button>
        <button class="jkr-widget-lang-chip" data-lang="hi-IN">हिंदी (Hindi)</button>
        <button class="jkr-widget-lang-chip" data-lang="en-IN">English</button>
      </div>
      <div class="jkr-widget-body" id="jkrWidgetMessages">
        <div class="jkr-msg jkr-msg-agent" id="jkrGreetingMsg">
          నమస్కారం! నేను ఏఐ అసిస్టెంట్‌ని. మీకు ఎలా సహాయపడగలను?
        </div>
      </div>
      <div class="jkr-widget-voice-viz" id="jkrVoiceViz" style="display: none;">
        <span style="font-size: 11px; color: #94a3b8; margin-right: 6px;">Speaking</span>
        <div class="jkr-viz-bar"></div>
        <div class="jkr-viz-bar"></div>
        <div class="jkr-viz-bar"></div>
        <div class="jkr-viz-bar"></div>
        <div class="jkr-viz-bar"></div>
      </div>
      <form class="jkr-widget-footer" id="jkrWidgetForm">
        <button type="button" class="jkr-mic-btn" id="jkrMicBtn" title="Speak via Microphone">
          🎙️
        </button>
        <input type="text" class="jkr-widget-input" id="jkrWidgetInput" placeholder="Type or click mic to speak..." autocomplete="off" />
        <button type="submit" class="jkr-send-btn" id="jkrSendBtn" title="Send message">
          ➤
        </button>
      </form>
      <div class="jkr-powered-by">
        Powered natively by <a href="https://jkrcalling.com" target="_blank">JKR Calling AI</a>
      </div>
    </div>

    <button class="jkr-widget-launcher" id="jkrWidgetLauncher">
      <div class="jkr-widget-pulse-ring"></div>
      <span class="jkr-widget-launcher-text" id="jkrLauncherText">Talk to AI Assistant</span>
    </button>
  `;

  document.body.appendChild(root);

  // Audio element for TTS playback
  const audio = new Audio();
  state.audioElement = audio;

  audio.onplay = () => {
    state.isPlayingAudio = true;
    const viz = document.getElementById('jkrVoiceViz');
    if (viz) viz.style.display = 'flex';
  };
  audio.onended = () => {
    state.isPlayingAudio = false;
    const viz = document.getElementById('jkrVoiceViz');
    if (viz) viz.style.display = 'none';
  };
  audio.onerror = () => {
    state.isPlayingAudio = false;
    const viz = document.getElementById('jkrVoiceViz');
    if (viz) viz.style.display = 'none';
  };

  // Web Speech API Voice Recognition
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (SpeechRecognition) {
    const recognition = new SpeechRecognition();
    recognition.continuous = false;
    recognition.interimResults = false;
    recognition.lang = state.currentLanguage;

    recognition.onresult = (event) => {
      const transcript = event.results[0][0].transcript;
      const input = document.getElementById('jkrWidgetInput');
      if (input) input.value = transcript;
      sendMessage(transcript);
    };

    recognition.onerror = (e) => {
      console.warn('[JKR Widget] Speech recognition error:', e.error);
      stopListening();
    };

    recognition.onend = () => {
      stopListening();
    };

    state.recognition = recognition;
  }

  function startListening() {
    if (!state.recognition) {
      alert('Speech recognition is not supported in this browser. Please use Chrome/Edge or type your message.');
      return;
    }
    try {
      state.recognition.lang = state.currentLanguage;
      state.recognition.start();
      state.isListening = true;
      const micBtn = document.getElementById('jkrMicBtn');
      if (micBtn) micBtn.classList.add('listening');
    } catch (err) {
      console.warn('[JKR Widget] Recognition start error:', err);
    }
  }

  function stopListening() {
    state.isListening = false;
    const micBtn = document.getElementById('jkrMicBtn');
    if (micBtn) micBtn.classList.remove('listening');
    if (state.recognition) {
      try { state.recognition.stop(); } catch (_) {}
    }
  }

  // API Call helper
  async function fetchJSON(endpoint, options = {}) {
    const url = `${state.config.apiBase}${endpoint}`;
    const res = await fetch(url, {
      ...options,
      headers: {
        'Content-Type': 'application/json',
        ...(options.headers || {}),
      },
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || err.message || `HTTP ${res.status}`);
    }
    return res.json();
  }

  // Load config & agent metadata
  async function loadConfig() {
    if (!state.config.agentId) {
      console.warn('[JKR Widget] No data-agent-id specified. Using default demo assistant.');
      return;
    }
    try {
      const data = await fetchJSON(`/api/v1/widget/config/${state.config.agentId}`);
      state.agentInfo = data;

      const agentNameEl = document.getElementById('jkrAgentName');
      if (agentNameEl) agentNameEl.innerText = data.name;

      const launcherTextEl = document.getElementById('jkrLauncherText');
      if (launcherTextEl) launcherTextEl.innerText = data.launcher_text || `Chat with ${data.name}`;

      const greetingMsgEl = document.getElementById('jkrGreetingMsg');
      if (greetingMsgEl && data.greeting_text) {
        greetingMsgEl.innerText = data.greeting_text;
      }
    } catch (err) {
      console.warn('[JKR Widget] Failed to load config:', err);
    }
  }

  // Initialize or start an active conversation session with Coin wallet metering
  async function ensureSession() {
    if (state.sessionId) return state.sessionId;
    if (!state.config.agentId) return null;

    try {
      const data = await fetchJSON('/api/v1/widget/session', {
        method: 'POST',
        body: JSON.stringify({
          agent_id: state.config.agentId,
          language: state.currentLanguage,
          visitor_name: 'Website Visitor',
        }),
      });
      state.sessionId = data.session_id;

      // Update greeting if returned
      if (data.greeting) {
        const greetingMsgEl = document.getElementById('jkrGreetingMsg');
        if (greetingMsgEl) greetingMsgEl.innerText = data.greeting;
      }
      return data.session_id;
    } catch (err) {
      if (err.message && err.message.includes('Insufficient coins')) {
        appendMessage('agent', '⚠️ [Billing Notice]: Workspace coin wallet is empty. Please recharge your balance at JKR Calling dashboard.');
      } else {
        console.error('[JKR Widget] Failed to create session:', err);
      }
      return null;
    }
  }

  function appendMessage(sender, text) {
    const messagesEl = document.getElementById('jkrWidgetMessages');
    if (!messagesEl) return;

    const msg = document.createElement('div');
    msg.className = `jkr-msg jkr-msg-${sender}`;
    msg.innerText = text;
    messagesEl.appendChild(msg);
    messagesEl.scrollTop = messagesEl.scrollHeight;
  }

  function appendAppointmentCard(details) {
    const messagesEl = document.getElementById('jkrWidgetMessages');
    if (!messagesEl) return;

    const card = document.createElement('div');
    card.className = 'jkr-card-appointment';
    card.innerHTML = `
      <div style="font-size: 20px;">📅</div>
      <div>
        <strong style="color: #6ee7b7; display: block; margin-bottom: 2px;">Appointment Confirmed!</strong>
        <span>Your appointment has been registered in the system. Our team will notify you.</span>
      </div>
    `;
    messagesEl.appendChild(card);
    messagesEl.scrollTop = messagesEl.scrollHeight;
  }

  async function sendMessage(text) {
    if (!text || !text.trim()) return;
    const cleanText = text.trim();

    appendMessage('user', cleanText);
    const input = document.getElementById('jkrWidgetInput');
    if (input) input.value = '';

    // Show temporary thinking indicator
    const thinkingEl = document.createElement('div');
    thinkingEl.className = 'jkr-msg jkr-msg-agent';
    thinkingEl.id = 'jkrThinking';
    thinkingEl.innerHTML = '<em>AI is thinking...</em>';
    const messagesEl = document.getElementById('jkrWidgetMessages');
    if (messagesEl) {
      messagesEl.appendChild(thinkingEl);
      messagesEl.scrollTop = messagesEl.scrollHeight;
    }

    try {
      const sessionId = await ensureSession();
      if (!sessionId) {
        if (thinkingEl) thinkingEl.remove();
        return;
      }

      const reply = await fetchJSON(`/api/v1/widget/session/${sessionId}/message`, {
        method: 'POST',
        body: JSON.stringify({
          message: cleanText,
          language: state.currentLanguage,
        }),
      });

      if (thinkingEl) thinkingEl.remove();
      appendMessage('agent', reply.reply_text);

      if (reply.appointment_booked) {
        appendAppointmentCard();
      }

      // Play audio TTS if available and not muted
      if (reply.audio_url && !state.audioMuted) {
        audio.src = reply.audio_url;
        audio.play().catch((err) => console.warn('[JKR Widget] Audio autoplay blocked:', err));
      }
    } catch (err) {
      if (thinkingEl) thinkingEl.remove();
      if (err.message && err.message.includes('Insufficient coins')) {
        appendMessage('agent', '⚠️ [Billing Notice]: Workspace coins exhausted. Recharge to continue talking.');
      } else {
        appendMessage('agent', `Sorry, encountered an error: ${err.message}`);
      }
    }
  }

  // Event Listeners
  const launcher = document.getElementById('jkrWidgetLauncher');
  const windowEl = document.getElementById('jkrWidgetWindow');
  const closeBtn = document.getElementById('jkrCloseBtn');
  const form = document.getElementById('jkrWidgetForm');
  const input = document.getElementById('jkrWidgetInput');
  const micBtn = document.getElementById('jkrMicBtn');
  const muteBtn = document.getElementById('jkrMuteBtn');

  launcher.addEventListener('click', () => {
    state.isOpen = !state.isOpen;
    if (state.isOpen) {
      windowEl.classList.add('active');
      launcher.style.display = 'none';
      ensureSession();
      if (input) input.focus();
    } else {
      windowEl.classList.remove('active');
      launcher.style.display = 'flex';
    }
  });

  closeBtn.addEventListener('click', () => {
    state.isOpen = false;
    windowEl.classList.remove('active');
    launcher.style.display = 'flex';
  });

  muteBtn.addEventListener('click', () => {
    state.audioMuted = !state.audioMuted;
    muteBtn.innerText = state.audioMuted ? '🔇' : '🔊';
    if (state.audioMuted && audio) {
      audio.pause();
    }
  });

  micBtn.addEventListener('click', () => {
    if (state.isListening) {
      stopListening();
    } else {
      startListening();
    }
  });

  form.addEventListener('submit', (e) => {
    e.preventDefault();
    sendMessage(input.value);
  });

  // Language switch chips
  const langChips = document.querySelectorAll('.jkr-widget-lang-chip');
  langChips.forEach((chip) => {
    chip.addEventListener('click', () => {
      langChips.forEach((c) => c.classList.remove('active'));
      chip.classList.add('active');
      state.currentLanguage = chip.getAttribute('data-lang');
      if (state.recognition) {
        state.recognition.lang = state.currentLanguage;
      }
    });
  });

  // Initial load
  loadConfig();
  if (state.config.autoOpen) {
    launcher.click();
  }

  // Expose global controller
  window.JKRWidget = {
    open: () => {
      if (!state.isOpen) launcher.click();
    },
    close: () => {
      if (state.isOpen) closeBtn.click();
    },
    setLanguage: (lang) => {
      const chip = document.querySelector(`.jkr-widget-lang-chip[data-lang="${lang}"]`);
      if (chip) chip.click();
    },
  };
})();
