const IS_PRACTICE = (window.EXAM_MODE === 'practice');

let calcDisplay = '';
let examEnded = false;
let isExamNavigation = false;
let practiceFeedbackShown = false;

/* ── Timer ─────────────────────────────────────────────────────── */
function updateTimer() {
    fetch('/time_check')
        .then(r => r.json())
        .then(data => {
            const remaining = data.remaining;
            const minutes = Math.floor(remaining / 60);
            const seconds = remaining % 60;
            const el = document.getElementById('timer');
            if (!el) return;
            el.textContent = `Time Left: ${String(minutes).padStart(2,'0')}:${String(seconds).padStart(2,'0')}`;
            if (remaining <= 60 && remaining > 0) {
                el.style.color = '#ff5068';
                el.style.animation = 'pulse 1s ease-in-out infinite';
            }
            if (remaining <= 0) {
                examEnded = true;
                showEndModal('timeup');
            } else {
                setTimeout(updateTimer, 1000);
            }
        })
        .catch(() => setTimeout(updateTimer, 2000));
}

/* ── Answer submission ──────────────────────────────────────────── */
function submitAnswer(optionIndex) {
    if (IS_PRACTICE) {
        submitAnswerPractice(optionIndex);
        return;
    }
    const formData = new FormData();
    formData.append('option', optionIndex);
    fetch('/answer', { method: 'POST', body: formData })
        .then(r => r.json())
        .then(data => {
            if (data.success) {
                document.querySelectorAll('.option').forEach(opt => opt.classList.remove('selected'));
                document.querySelectorAll('.option')[optionIndex].classList.add('selected');
            }
        });
}

/* ── Practice answer + AI feedback ─────────────────────────────── */
function submitAnswerPractice(optionIndex) {
    const opts = document.querySelectorAll('.option');
    opts.forEach(o => {
        o.classList.remove('selected', 'practice-correct', 'practice-wrong', 'practice-reveal');
        const radio = o.querySelector('input[type="radio"]');
        if (radio) radio.disabled = true;
    });
    opts[optionIndex].classList.add('selected');

    const feedbackEl = document.getElementById('practice-feedback');
    const verdictEl  = document.getElementById('pf-verdict');
    const explainEl  = document.getElementById('pf-explanation');
    if (feedbackEl) {
        feedbackEl.style.display = 'block';
        feedbackEl.style.background = 'rgba(255,255,255,0.04)';
        feedbackEl.style.border = '1px solid rgba(255,255,255,0.08)';
        verdictEl.innerHTML = '<span style="opacity:0.5;font-size:13px;">Checking…</span>';
        explainEl.textContent = '';
    }

    const formData = new FormData();
    formData.append('option', optionIndex);
    fetch('/practice/feedback', { method: 'POST', body: formData })
        .then(r => r.json())
        .then(data => {
            if (!data.success) return;
            // Colour the options
            if (data.correct_index !== null && data.correct_index !== undefined) {
                opts[data.correct_index].classList.add('practice-correct');
            }
            if (!data.is_correct && data.selected_index !== null) {
                opts[data.selected_index].classList.add('practice-wrong');
            }
            // Update feedback panel
            if (feedbackEl) {
                if (data.is_correct) {
                    feedbackEl.style.background = 'rgba(19,122,19,0.10)';
                    feedbackEl.style.border = '1px solid rgba(19,122,19,0.28)';
                    verdictEl.innerHTML = '<svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#1db01d" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg><span style="color:#1db01d;">Correct!</span>';
                } else {
                    feedbackEl.style.background = 'rgba(255,80,104,0.08)';
                    feedbackEl.style.border = '1px solid rgba(255,80,104,0.25)';
                    verdictEl.innerHTML = '<svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#ff5068" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg><span style="color:#ff5068;">Wrong</span>';
                }
                explainEl.textContent = data.explanation || '';
            }
            practiceFeedbackShown = true;
        })
        .catch(() => {
            if (verdictEl) verdictEl.textContent = 'Could not fetch feedback.';
        });
}

/* ── Practice option styles ─────────────────────────────────────── */
(function injectPracticeStyles() {
    if (!IS_PRACTICE) return;
    const s = document.createElement('style');
    s.textContent = `
        .option.practice-correct { border-color: rgba(19,122,19,0.55) !important; background: rgba(19,122,19,0.12) !important; }
        .option.practice-correct .option-text { color: #1db01d !important; font-weight: 600; }
        .option.practice-wrong   { border-color: rgba(255,80,104,0.55) !important; background: rgba(255,80,104,0.10) !important; }
        .option.practice-wrong   .option-text { color: #ff5068 !important; }
        .option input[disabled]  { cursor: not-allowed; }
    `;
    document.head.appendChild(s);
})();

/* ── Calculator ─────────────────────────────────────────────────── */
function toggleCalculator() {
    const calc = document.getElementById('calculator');
    calc.style.display = calc.style.display === 'none' ? 'block' : 'none';
}
function calcBtn(v)    { calcDisplay += v; document.getElementById('calc-display').value = calcDisplay; }
function calcClear()   { calcDisplay = ''; document.getElementById('calc-display').value = ''; }
function calcBackspace(){ calcDisplay = calcDisplay.slice(0,-1); document.getElementById('calc-display').value = calcDisplay; }
function calcEquals()  {
    try { calcDisplay = String(eval(calcDisplay)); document.getElementById('calc-display').value = calcDisplay; }
    catch(e) { document.getElementById('calc-display').value = 'Error'; calcDisplay = ''; }
}

/* ── End-exam modal ─────────────────────────────────────────────── */
function showEndModal(reason) {
    const modal = document.getElementById('end-exam-modal');
    const title = document.getElementById('modal-title');
    const msg   = document.getElementById('modal-msg');
    if (reason === 'timeup') {
        title.textContent = 'Time\'s Up!';
        msg.textContent   = 'Your exam time has expired. Your answers are being submitted now.';
        document.getElementById('modal-continue-btn').style.display = 'none';
        document.getElementById('modal-end-btn').textContent = 'View Results';
        setTimeout(() => {
            examEnded = true;
            document.getElementById('submit-form').submit();
        }, 2000);
    } else {
        title.textContent = IS_PRACTICE ? 'End Practice?' : 'End Exam?';
        msg.textContent   = IS_PRACTICE
            ? 'End the practice session and see your results.'
            : 'If you leave now your current answers will be submitted and the exam will end.';
        document.getElementById('modal-continue-btn').style.display = 'inline-flex';
        document.getElementById('modal-end-btn').textContent = IS_PRACTICE ? 'End & See Results' : 'End & Submit';
    }
    modal.classList.add('active');
}

function hideEndModal() {
    document.getElementById('end-exam-modal').classList.remove('active');
    if (!IS_PRACTICE) history.pushState({ examPage: true }, '', window.location.href);
}

function confirmEndExam() {
    examEnded = true;
    document.getElementById('end-exam-modal').classList.remove('active');
    document.getElementById('submit-form').submit();
}

/* ── Back-button / popstate trap (exam mode only) ───────────────── */
if (!IS_PRACTICE) {
    history.pushState({ examPage: true }, '', window.location.href);
    window.addEventListener('popstate', function(e) {
        if (examEnded) return;
        history.pushState({ examPage: true }, '', window.location.href);
        showEndModal('back');
    });
}

/* ── Page refresh / tab close warning (exam mode only) ──────────── */
if (!IS_PRACTICE) {
    window.addEventListener('beforeunload', function(e) {
        if (examEnded || isExamNavigation) return;
        e.preventDefault();
        e.returnValue = 'Your exam is still in progress. Leaving will end the exam.';
        return e.returnValue;
    });
}

/* ── Mark exam navigation forms so beforeunload doesn't fire ────── */
document.addEventListener('DOMContentLoaded', function() {
    document.querySelectorAll('form').forEach(function(form) {
        var action = form.getAttribute('action') || '';
        if (action.indexOf('navigate') !== -1 || form.id === 'prev-form' || form.id === 'next-form') {
            form.addEventListener('submit', function() {
                isExamNavigation = true;
            });
        }
    });
    document.querySelectorAll('input[name="action"]').forEach(function(inp) {
        var val = inp.value;
        if (val === 'prev' || val === 'next' || val === 'goto' || val === 'prev_subject' || val === 'next_subject' || val === 'switch_subject') {
            var f = inp.closest('form');
            if (f) f.addEventListener('submit', function() { isExamNavigation = true; });
        }
    });
});

/* ── Keyboard shortcuts ─────────────────────────────────────────── */
document.addEventListener('keydown', function(e) {
    const modal = document.getElementById('end-exam-modal');
    if (modal && modal.classList.contains('active')) {
        if (e.key === 'Escape') hideEndModal();
        return;
    }
    if (e.key === 'ArrowLeft') {
        const b = document.getElementById('prev-btn');
        if (b && !b.disabled) { isExamNavigation = true; document.getElementById('prev-form').submit(); }
    } else if (e.key === 'ArrowRight') {
        const b = document.getElementById('next-btn');
        if (b && !b.disabled) { isExamNavigation = true; document.getElementById('next-form').submit(); }
    } else if (!IS_PRACTICE && ['a','A'].includes(e.key)) {
        const o = document.querySelector('input[name="option"][value="0"]');
        if (o && !o.disabled) { o.checked = true; submitAnswer(0); }
    } else if (!IS_PRACTICE && ['b','B'].includes(e.key)) {
        const o = document.querySelector('input[name="option"][value="1"]');
        if (o && !o.disabled) { o.checked = true; submitAnswer(1); }
    } else if (!IS_PRACTICE && ['c','C'].includes(e.key)) {
        const o = document.querySelector('input[name="option"][value="2"]');
        if (o && !o.disabled) { o.checked = true; submitAnswer(2); }
    } else if (!IS_PRACTICE && ['d','D'].includes(e.key)) {
        const o = document.querySelector('input[name="option"][value="3"]');
        if (o && !o.disabled) { o.checked = true; submitAnswer(3); }
    } else if (e.key === 's' || e.key === 'S') {
        showEndModal('back');
    }
});

if (document.getElementById('timer')) updateTimer();
