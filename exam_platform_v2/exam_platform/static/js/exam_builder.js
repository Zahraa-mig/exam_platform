let qCount = 0;
const container = document.getElementById('questions-container');
const noMsg     = document.getElementById('no-q-msg');
const addBtn    = document.getElementById('add-q-btn');

const OPT_LABELS = { a:'أ', b:'ب', c:'ج', d:'د' };

function addQuestion(data = {}) {
  qCount++;
  const n = qCount;
  if (noMsg) noMsg.style.display = 'none';

  const optionsHtml = ['a','b','c','d'].map(o => `
    <div style="display:grid; grid-template-columns:auto 1fr; gap:.5rem; align-items:center; margin-bottom:.45rem;">
      <label style="color:var(--muted); font-size:.85rem; white-space:nowrap; display:flex; align-items:center; gap:.35rem;">
        <input type="radio" name="q${n}_answer" value="${o}" ${data.answer === o ? 'checked' : ''} required>
        ${OPT_LABELS[o]}
      </label>
      <input type="text" name="q${n}_${o}"
             placeholder="الخيار ${OPT_LABELS[o]}"
             value="${(data[o] || '').replace(/"/g,'&quot;')}"
             style="background:var(--bg);border:1px solid var(--border);border-radius:6px;
                    padding:.48rem .8rem;color:var(--text);font-family:inherit;width:100%;" required>
    </div>
  `).join('');

  // show existing image preview if editing
  const existingImg = data.image_path
    ? `<div id="preview-wrap-${n}" style="margin-top:.5rem;">
         <img src="/uploads/${data.image_path}" alt="صورة السؤال"
              style="max-height:160px;border-radius:6px;border:1px solid var(--border);">
         <p style="font-size:.75rem;color:var(--muted);margin-top:.3rem;">
           الصورة الحالية – ارفع صورة جديدة للاستبدال أو اتركها كما هي
         </p>
       </div>`
    : `<div id="preview-wrap-${n}"></div>`;

  const div = document.createElement('div');
  div.className = 'q-item';
  div.dataset.n = n;
  div.innerHTML = `
    <div class="q-header">
      <span style="color:var(--accent);font-size:.85rem;font-weight:600;">سؤال ${n}</span>
      <button type="button" class="remove-q" onclick="removeQuestion(this)">🗑</button>
    </div>

    <!-- Question text -->
    <div style="margin-bottom:.8rem;">
      <input type="text" name="q${n}_text"
             placeholder="نص السؤال..."
             value="${(data.text || '').replace(/"/g,'&quot;')}"
             style="width:100%;background:var(--bg);border:1px solid var(--border);
                    border-radius:6px;padding:.6rem .9rem;color:var(--text);
                    font-family:inherit;font-size:.95rem;" required>
    </div>
    <!-- Marks -->
    <div style="margin-bottom:.9rem; display:flex; align-items:center; gap:.8rem;">
      <label style="font-size:.8rem;color:var(--muted);white-space:nowrap;">
        ⭐ علامة السؤال:
      </label>
      <input type="number" name="q${n}_marks"
             value="${data.marks || 1}" min="1" max="100"
             style="width:80px;background:var(--bg);border:1px solid var(--border);
                    border-radius:6px;padding:.4rem .6rem;color:var(--text);
                    font-family:inherit;text-align:center;">
      <span style="font-size:.8rem;color:var(--muted);">درجة</span>
    </div>

    <!-- Image upload -->
    <div style="margin-bottom:.9rem;">
      <label style="font-size:.8rem;color:var(--muted);display:block;margin-bottom:.35rem;">
        📎 إرفاق صورة مع السؤال (اختياري – PNG، JPG، GIF، WebP)
      </label>
      <input type="file" name="q${n}_image" accept="image/*"
             onchange="previewImage(this, ${n})"
             style="color:var(--text);font-size:.83rem;">
      ${existingImg}
    </div>

    <!-- Options -->
    <div>
      <p style="font-size:.78rem;color:var(--muted);margin-bottom:.5rem;">
        اختر الإجابة الصحيحة بالضغط على الزر بجانبها:
      </p>
      ${optionsHtml}
    </div>
  `;
  container.appendChild(div);
}

function previewImage(input, n) {
  const wrap = document.getElementById(`preview-wrap-${n}`);
  if (!input.files || !input.files[0]) { wrap.innerHTML = ''; return; }
  const reader = new FileReader();
  reader.onload = e => {
    wrap.innerHTML = `
      <img src="${e.target.result}" alt="معاينة"
           style="max-height:160px;border-radius:6px;border:1px solid var(--border);margin-top:.5rem;">
    `;
  };
  reader.readAsDataURL(input.files[0]);
}

function removeQuestion(btn) {
  btn.closest('.q-item').remove();
  if (!container.querySelectorAll('.q-item').length && noMsg)
    noMsg.style.display = 'block';
}

addBtn.addEventListener('click', () => {
  addQuestion();
  setTimeout(() => {
    window.scrollTo({ top: document.body.scrollHeight, behavior: 'smooth' });
  }, 100);
});

const addBtnBottom = document.getElementById('add-q-btn-bottom');
if (addBtnBottom) {
  addBtnBottom.addEventListener('click', () => {
    addQuestion();
    setTimeout(() => {
      window.scrollTo({ top: document.body.scrollHeight, behavior: 'smooth' });
    }, 100);
  });
}

// Preload for edit mode
if (window.EXISTING_QUESTIONS && EXISTING_QUESTIONS.length)
  EXISTING_QUESTIONS.forEach(q => addQuestion(q));
