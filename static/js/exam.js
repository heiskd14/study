let calcDisplay = '';
let examEnded = false;

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
        title.textContent = 'End Exam?';
        msg.textContent   = 'If you leave now your current answers will be submitted and the exam will end.';
        document.getElementById('modal-continue-btn').style.display = 'inline-flex';
        document.getElementById('modal-end-btn').textContent = 'End & Submit';
    }
    modal.classList.add('active');
}

function hideEndModal() {
    document.getElementById('end-exam-modal').classList.remove('active');
    // Re-push state so back button is caught again
    history.pushState({ examPage: true }, '', window.location.href);
}

function confirmEndExam() {
    examEnded = true;
    document.getElementById('end-exam-modal').classList.remove('active');
    document.getElementById('submit-form').submit();
}

/* ── Back-button / popstate trap ────────────────────────────────── */
// Push an extra history entry so the first "back" is caught here
history.pushState({ examPage: true }, '', window.location.href);

window.addEventListener('popstate', function(e) {
    if (examEnded) return;
    // Re-push so another back press is also caught
    history.pushState({ examPage: true }, '', window.location.href);
    showEndModal('back');
});

/* ── Page refresh / tab close warning ──────────────────────────── */
window.addEventListener('beforeunload', function(e) {
    if (examEnded) return;
    e.preventDefault();
    e.returnValue = 'Your exam is still in progress. Leaving will end the exam.';
    return e.returnValue;
});

/* ── Keyboard shortcuts ─────────────────────────────────────────── */
document.addEventListener('keydown', function(e) {
    // Don't fire if modal is open
    if (document.getElementById('end-exam-modal').classList.contains('active')) {
        if (e.key === 'Escape') hideEndModal();
        return;
    }
    if (e.key === 'ArrowLeft') {
        const b = document.getElementById('prev-btn');
        if (b && !b.disabled) document.getElementById('prev-form').submit();
    } else if (e.key === 'ArrowRight') {
        const b = document.getElementById('next-btn');
        if (b && !b.disabled) document.getElementById('next-form').submit();
    } else if (['a','A'].includes(e.key)) {
        const o = document.querySelector('input[name="option"][value="0"]');
        if (o) { o.checked = true; submitAnswer(0); }
    } else if (['b','B'].includes(e.key)) {
        const o = document.querySelector('input[name="option"][value="1"]');
        if (o) { o.checked = true; submitAnswer(1); }
    } else if (['c','C'].includes(e.key)) {
        const o = document.querySelector('input[name="option"][value="2"]');
        if (o) { o.checked = true; submitAnswer(2); }
    } else if (['d','D'].includes(e.key)) {
        const o = document.querySelector('input[name="option"][value="3"]');
        if (o) { o.checked = true; submitAnswer(3); }
    } else if (['s','S'].includes(e.key)) {
        showEndModal('back');
    }
});

if (document.getElementById('timer')) updateTimer();
