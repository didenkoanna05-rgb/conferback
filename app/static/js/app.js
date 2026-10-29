// Спільні сценарії: службовий сценарій для роботи без мережі та живий підрахунок оцінки доцільності.
(function () {
  if ('serviceWorker' in navigator) {
    window.addEventListener('load', function () {
      navigator.serviceWorker.register('/sw.js').catch(function () {});
    });
  }

  // Підказки до показників
  if (window.bootstrap) {
    document.querySelectorAll('[data-bs-toggle="tooltip"]').forEach(function (el) {
      new bootstrap.Tooltip(el, {container: 'body'});
    });
  }

  // Індикатор стану мережі
  var bar = document.getElementById('netStatus');
  function showNet() {
    if (!bar) return;
    if (navigator.onLine) {
      bar.classList.add('d-none');
    } else {
      bar.textContent = 'Немає з’єднання. Записи розмов зберігаються на пристрої й надішлються самі.';
      bar.classList.remove('d-none');
    }
  }
  window.addEventListener('online', showNet);
  window.addEventListener('offline', showNet);
  showNet();

  // Оцінка доцільності: сума балів і висновок за формулою (3.3) одразу під час вибору
  var form = document.querySelector('.score-form');
  if (form) {
    var n = +form.dataset.n, high = +form.dataset.high, low = +form.dataset.low;
    var total = document.getElementById('scoreTotal');
    var verdict = document.getElementById('scoreVerdict');
    form.addEventListener('change', function () {
      var checked = form.querySelectorAll('input[type=radio]:checked');
      var s = 0;
      checked.forEach(function (i) { s += +i.value; });
      total.textContent = s;
      var text = 'оцініть усі критерії', tone = 'secondary';
      if (checked.length === n) {
        if (s >= high) { text = 'Участь рекомендована'; tone = 'success'; }
        else if (s >= low) { text = 'Потрібне обговорення'; tone = 'warning'; }
        else { text = 'Участь не рекомендована'; tone = 'danger'; }
      }
      verdict.textContent = text;
      verdict.className = 'badge text-bg-' + tone;
    });
  }
})();
