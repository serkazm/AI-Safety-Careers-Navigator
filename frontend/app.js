/* ── State ── */
const state = {
  cvSummary: '',
  questions: [],
  recommendations: '',
  chatHistory: [],
};

/* ── Helpers ── */
const $ = id => document.getElementById(id);

function setSection(name) {
  document.querySelectorAll('.section').forEach(s => s.classList.remove('active'));
  $(`section-${name}`).classList.add('active');
  window.scrollTo({ top: 0, behavior: 'smooth' });

  const stepOrder = { upload: 1, questions: 2, results: 3 };
  const current = stepOrder[name];
  document.querySelectorAll('[data-step]').forEach(el => {
    const n = parseInt(el.dataset.step, 10);
    el.classList.remove('active', 'done');
    if (n === current) el.classList.add('active');
    else if (n < current) el.classList.add('done');
  });
}

function showAlert(type, html) {
  const el = $('upload-alert');
  el.className = `alert ${type}`;
  el.innerHTML = html;
  el.classList.remove('hidden');
}

/* ─────────────────────────────────────────
   Step 1 – Upload
───────────────────────────────────────── */
function setupUpload() {
  const area  = $('upload-area');
  const input = $('cv-input');

  // Drag-and-drop
  area.addEventListener('dragover', e => {
    e.preventDefault();
    area.classList.add('dragover');
  });
  area.addEventListener('dragleave', () => area.classList.remove('dragover'));
  area.addEventListener('drop', e => {
    e.preventDefault();
    area.classList.remove('dragover');
    const file = e.dataTransfer.files[0];
    if (file) handleFile(file);
  });

  // File-picker change
  input.addEventListener('change', () => {
    if (input.files[0]) handleFile(input.files[0]);
  });
}

async function handleFile(file) {
  if (!file.name.toLowerCase().endsWith('.pdf')) {
    showAlert('error', '⚠️ Please upload a PDF file.');
    return;
  }

  showAlert('loading', '<span class="btn-spinner"></span> Uploading and analysing your CV…');

  const formData = new FormData();
  formData.append('file', file);

  try {
    const res = await fetch('/api/classify-cv', { method: 'POST', body: formData });

    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: 'Upload failed.' }));
      throw new Error(err.detail || 'Upload failed.');
    }

    const data = await res.json();
    state.cvSummary = data.cv_summary;

    await showQuestions();
  } catch (err) {
    showAlert('error', `⚠️ ${err.message}`);
  }
}

/* ─────────────────────────────────────────
   Step 2 – Questions
───────────────────────────────────────── */
async function showQuestions() {
  // Fetch questions
  const res = await fetch('/api/questions');
  const { questions } = await res.json();
  state.questions = questions;

  // Render questions
  const container = $('questions-container');
  container.innerHTML = '';
  questions.forEach(q => container.appendChild(renderQuestion(q)));

  setSection('questions');
}

function renderQuestion(q) {
  const group = document.createElement('div');
  group.className = 'question-group';

  const labelText = `<span class="q-num">Q${q.id}.</span> ${q.question}`;

  if (q.type === 'scale') {
    group.innerHTML = `
      <label class="question-label">${labelText}</label>
      <div class="scale-options">
        ${q.options.map((opt, i) => `
          <div class="scale-option">
            <input type="radio" name="q${q.id}" id="q${q.id}_${i}" value="${escapeHtml(opt)}" required>
            <label for="q${q.id}_${i}">${escapeHtml(opt)}</label>
          </div>
        `).join('')}
      </div>`;
  } else if (q.type === 'multi') {
    group.innerHTML = `
      <label class="question-label">${labelText}</label>
      <div class="scale-options">
        ${q.options.map((opt, i) => `
          <div class="scale-option">
            <input type="checkbox" name="q${q.id}" id="q${q.id}_${i}" value="${escapeHtml(opt)}">
            <label for="q${q.id}_${i}">${escapeHtml(opt)}</label>
          </div>
        `).join('')}
      </div>`;
  } else {
    group.innerHTML = `
      <label class="question-label" for="q${q.id}_text">${labelText}</label>
      <textarea
        class="text-answer"
        id="q${q.id}_text"
        name="q${q.id}"
        placeholder="${escapeHtml(q.placeholder || '')}"
        rows="3"
        required
      ></textarea>`;
  }

  return group;
}

function escapeHtml(str) {
  return str
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function setupQuestionsForm() {
  $('questions-form').addEventListener('submit', async e => {
    e.preventDefault();
    const answers = collectAnswers();
    if (!answers) return;
    setSection('results');
    await streamRecommendations(answers);
  });
}

function collectAnswers() {
  const answers = [];

  for (const q of state.questions) {
    if (q.type === 'scale') {
      const checked = document.querySelector(`input[name="q${q.id}"]:checked`);
      if (!checked) {
        alert(`Please answer question ${q.id}.`);
        return null;
      }
      answers.push({ question_id: q.id, answer: checked.value });
    } else if (q.type === 'multi') {
      const checked = document.querySelectorAll(`input[name="q${q.id}"]:checked`);
      if (checked.length === 0) {
        alert(`Please answer question ${q.id}.`);
        return null;
      }
      const values = Array.from(checked).map(el => el.value);
      answers.push({ question_id: q.id, answer: values.join('; ') });
    } else {
      const el = $(`q${q.id}_text`);
      if (!el.value.trim()) {
        alert(`Please answer question ${q.id}.`);
        el.focus();
        return null;
      }
      answers.push({ question_id: q.id, answer: el.value.trim() });
    }
  }

  return answers;
}

/* ─────────────────────────────────────────
   Step 3 – Recommendations (live-streaming cards)
───────────────────────────────────────── */
const CARD_ACCENTS = [
  { color: 'var(--sky)',   text: 'var(--navy)' },
  { color: 'var(--coral)', text: 'white' },
  { color: 'var(--teal)',  text: 'white' },
];

function parseSections(md) {
  const lines = md.split('\n');
  const sections = [];
  let current = null;

  for (const line of lines) {
    const headingMatch = line.match(/^#{1,3}\s+\*{0,2}(.+?)\*{0,2}\s*$/) ||
                         line.match(/^\*{2}(\d+\.\s*.+?)\*{2}\s*$/) ||
                         line.match(/^\*{2}([^*]+)\*{2}\s*$/);

    if (headingMatch) {
      current = { title: headingMatch[1].replace(/\*{2}/g, '').trim(), body: '' };
      sections.push(current);
    } else if (current) {
      current.body += line + '\n';
    }
  }
  return sections;
}

function buildCard(title, bodyMd, index, accent) {
  const card = document.createElement('div');
  card.className = 'program-card';
  card.style.setProperty('--accent', accent.color);
  card.style.setProperty('--accent-text', accent.text);
  card.style.animationDelay = `${index * 0.08}s`;

  card.innerHTML = `
    <div class="program-card-badge">${index + 1}</div>
    <div class="program-card-inner">
      <h3 class="program-card-title">${escapeHtml(title)}</h3>
      <div class="program-card-body">${marked.parse(bodyMd.trim() || '')}</div>
    </div>
  `;
  return card;
}

async function streamRecommendations(answers) {
  const content = $('reco-content');
  const footer  = $('reco-footer');

  // Show heading and content area immediately
  $('reco-heading').classList.remove('hidden');
  $('reco-lead').classList.remove('hidden');
  content.classList.remove('hidden');
  content.innerHTML = '';
  footer.classList.add('hidden');
  $('followup-pills').classList.add('hidden');
  $('followup-section').classList.add('hidden');

  let accumulated = '';
  let cardCount = 0;

  // Live streaming element for in-progress text
  const liveEl = document.createElement('div');
  liveEl.className = 'reco-live';
  content.appendChild(liveEl);

  try {
    const res = await fetch('/api/get-recommendations', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ cv_summary: state.cvSummary, answers }),
    });

    if (!res.ok) throw new Error('Could not fetch recommendations.');

    const reader  = res.body.getReader();
    const decoder = new TextDecoder();

    outer: while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      const raw = decoder.decode(value, { stream: true });
      for (const line of raw.split('\n')) {
        if (!line.startsWith('data: ')) continue;
        const payload = line.slice(6).trim();
        if (payload === '[DONE]') break outer;

        try {
          const { text } = JSON.parse(payload);
          accumulated += text;
        } catch { continue; }
      }

      // After each chunk, update the display
      const sections = parseSections(accumulated);
      const completedCount = Math.max(0, sections.length - 1);

      // Wrap newly completed sections as cards
      while (cardCount < completedCount) {
        const s = sections[cardCount];
        const accent = CARD_ACCENTS[cardCount % CARD_ACCENTS.length];
        const card = buildCard(s.title, s.body, cardCount, accent);
        content.insertBefore(card, liveEl);
        cardCount++;
      }

      // Show in-progress section as live text
      if (sections.length > 0) {
        const current = sections[sections.length - 1];
        liveEl.innerHTML = marked.parse(`**${current.title}**\n${current.body}`);
      } else {
        liveEl.innerHTML = marked.parse(accumulated);
      }
    }

    // Streaming done — finalize remaining sections as cards
    const sections = parseSections(accumulated);
    while (cardCount < sections.length) {
      const s = sections[cardCount];
      const accent = CARD_ACCENTS[cardCount % CARD_ACCENTS.length];
      const card = buildCard(s.title, s.body, cardCount, accent);
      content.insertBefore(card, liveEl);
      cardCount++;
    }

    liveEl.remove();

    state.recommendations = accumulated;
    $('followup-pills').classList.remove('hidden');
    $('followup-section').classList.remove('hidden');
    footer.classList.remove('hidden');

  } catch (err) {
    liveEl.remove();
    content.innerHTML = `<p style="color:#c53030">${err.message} Please try again.</p>`;
    footer.classList.remove('hidden');
  }
}

/* ─────────────────────────────────────────
   Follow-up Questions
───────────────────────────────────────── */
function setupFollowUp() {
  $('followup-form').addEventListener('submit', async e => {
    e.preventDefault();
    const input = $('followup-input');
    const question = input.value.trim();
    if (!question) return;

    input.value = '';
    input.disabled = true;
    $('followup-form').querySelector('button').disabled = true;

    const thread = $('followup-thread');

    // Add user message
    const userBubble = document.createElement('div');
    userBubble.className = 'followup-msg followup-user';
    userBubble.textContent = question;
    thread.appendChild(userBubble);

    // Add assistant placeholder
    const asstBubble = document.createElement('div');
    asstBubble.className = 'followup-msg followup-asst';
    asstBubble.innerHTML = '<span class="btn-spinner"></span>';
    thread.appendChild(asstBubble);
    thread.scrollTop = thread.scrollHeight;

    let accumulated = '';

    try {
      const res = await fetch('/api/follow-up', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          question,
          recommendations: state.recommendations,
          chat_history: state.chatHistory,
        }),
      });

      if (!res.ok) throw new Error('Could not get answer.');

      const reader = res.body.getReader();
      const decoder = new TextDecoder();

      outer: while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        const raw = decoder.decode(value, { stream: true });
        for (const line of raw.split('\n')) {
          if (!line.startsWith('data: ')) continue;
          const payload = line.slice(6).trim();
          if (payload === '[DONE]') break outer;

          try {
            const { text } = JSON.parse(payload);
            accumulated += text;
            asstBubble.innerHTML = marked.parse(accumulated);
          } catch {
            // skip
          }
        }
        thread.scrollTop = thread.scrollHeight;
      }

      asstBubble.innerHTML = marked.parse(accumulated);
      state.chatHistory.push({ role: 'user', content: question });
      state.chatHistory.push({ role: 'assistant', content: accumulated });

    } catch (err) {
      asstBubble.innerHTML = `<span style="color:#c53030">Could not get answer. Please try again.</span>`;
    }

    input.disabled = false;
    $('followup-form').querySelector('button').disabled = false;
    input.focus();
    thread.scrollTop = thread.scrollHeight;
  });
}

/* ── Follow-up Pills ── */
function setupFollowUpPills() {
  $('followup-pills').addEventListener('click', e => {
    const pill = e.target.closest('.pill');
    if (!pill) return;
    $('followup-input').value = pill.dataset.question;
    $('followup-form').requestSubmit();
    $('followup-pills').classList.add('hidden');
  });
}

/* ── Init ── */
document.addEventListener('DOMContentLoaded', () => {
  setupUpload();
  setupQuestionsForm();
  setupFollowUp();
  setupFollowUpPills();
  setSection('upload');
});
