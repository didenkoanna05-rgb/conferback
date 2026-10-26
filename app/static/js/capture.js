// Фіксація розмови з роботою без мережі (ФВ-13, ДВ-05, ДВ-06).
// Кожен запис спершу лягає в чергу локального сховища з унікальним client_uid,
// а потім надсилається на сервер. Без мережі запис чекає й надсилається пізніше.
(function () {
  var form = document.getElementById('captureForm');
  if (!form) return;
  var KEY = 'conferback.pending';
  var delays = JSON.parse(form.dataset.delays);
  var toast = document.getElementById('captureToast');
  var badge = document.getElementById('pendingBadge');
  var counter = document.getElementById('pendingCount');
  var sending = false;

  function pending() {
    try { return JSON.parse(localStorage.getItem(KEY)) || []; } catch (e) { return []; }
  }
  function setPending(list) {
    localStorage.setItem(KEY, JSON.stringify(list));
    renderBadge();
  }
  function renderBadge() {
    var n = pending().length;
    counter.textContent = n;
    badge.classList.toggle('d-none', n === 0);
  }
  function uid() {
    if (window.crypto && crypto.randomUUID) return crypto.randomUUID().replace(/-/g, '');
    return Date.now().toString(36) + Math.random().toString(36).slice(2, 12);
  }
  function localIso(d) {
    var p = function (x) { return String(x).padStart(2, '0'); };
    return d.getFullYear() + '-' + p(d.getMonth() + 1) + '-' + p(d.getDate()) +
      'T' + p(d.getHours()) + ':' + p(d.getMinutes()) + ':' + p(d.getSeconds());
  }
  function say(text, tone) {
    toast.textContent = text;
    toast.className = 'alert py-2 alert-' + tone;
    clearTimeout(say.t);
    say.t = setTimeout(function () { toast.classList.add('d-none'); }, 6000);
  }

  // Надсилання накопичених записів; сервер повертає перелік опрацьованих
  function flush() {
    var list = pending();
    if (!list.length || sending || !navigator.onLine) return Promise.resolve(null);
    sending = true;
    return fetch(form.dataset.syncUrl, {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': form.dataset.csrf },
      body: JSON.stringify({ leads: list })
    }).then(function (r) {
      if (r.status === 401) throw new Error('login');
      if (!r.ok) throw new Error('server');
      return r.json();
    }).then(function (res) {
      var done = new Set(res.done);
      setPending(pending().filter(function (x) { return !done.has(x.client_uid); }));
      return res;
    }).catch(function (e) {
      if (e.message === 'login') say('Сеанс завершився. Увійдіть знову — записи збережено на пристрої.', 'warning');
      return null;
    }).finally(function () { sending = false; });
  }

  // Дата фолоу-апу за формулою (3.4) — показуємо одразу
  var preview = document.getElementById('duePreview');
  function showDue() {
    var checked = form.querySelector('input[name=intent]:checked');
    if (!checked) return;
    if (document.getElementById('no_prospect').checked) {
      preview.textContent = 'Неперспективний: фолоу-ап не плануємо.';
      return;
    }
    var days = delays[checked.value];
    var d = new Date(); d.setDate(d.getDate() + days);
    var when = days === 0 ? 'сьогодні' : (days === 2 ? 'через 2 дні' : 'через ' + days + ' днів');
    preview.innerHTML = '<i class="bi bi-calendar-check"></i> Фолоу-ап: <b>' + when + '</b>, ' + d.toLocaleDateString('uk-UA');
    preview.classList.add('ready');
  }
  form.addEventListener('change', function (e) {
    if (e.target.name === 'intent' || e.target.id === 'no_prospect') showDue();
  });

  // Вибір зі списку або спонтанна розмова
  var pick = document.getElementById('targetPick');
  var select = document.getElementById('targetSelect');
  form.querySelectorAll('input[name=who]').forEach(function (r) {
    r.addEventListener('change', function () {
      var fromList = r.value === 'target' && r.checked;
      pick.classList.toggle('d-none', !fromList);
      if (!fromList) select.selectedIndex = -1;
    });
  });
  select.addEventListener('change', function () {
    var o = select.selectedOptions[0];
    if (!o) return;
    form.full_name.value = o.dataset.name;
    form.company.value = o.dataset.company;
    form.position.value = o.dataset.position;
  });
  var search = document.getElementById('targetSearch');
  search.addEventListener('input', function () {
    var q = search.value.trim().toLowerCase();
    Array.prototype.forEach.call(select.options, function (o) {
      o.hidden = q && o.textContent.toLowerCase().indexOf(q) === -1;
    });
  });

  // Кнопки-підказки заповнюють поле одним дотиком
  form.querySelectorAll('.chip-select').forEach(function (box) {
    var input = document.getElementById(box.dataset.target);
    box.addEventListener('click', function (e) {
      if (!e.target.classList.contains('chip')) return;
      box.querySelectorAll('.chip').forEach(function (c) { c.classList.remove('active'); });
      e.target.classList.add('active');
      input.value = e.target.textContent;
    });
  });

  form.addEventListener('submit', function (ev) {
    ev.preventDefault();
    var data = Object.fromEntries(new FormData(form).entries());
    if (!data.full_name.trim()) { say('Вкажіть ім’я співрозмовника.', 'danger'); form.full_name.focus(); return; }
    if (!data.intent) { say('Оберіть рівень зацікавленості.', 'danger'); return; }
    if (form.querySelector('input[name=who]:checked').value !== 'target') delete data.target_id;
    delete data.who;
    delete data.csrf_token;
    data.event_id = form.dataset.event;
    data.client_uid = uid();
    // Час розмови фіксується на пристрої, а не в момент надсилання
    data.captured_at = localIso(new Date());
    var list = pending(); list.push(data); setPending(list);

    var name = data.full_name;
    var keepOwner = form.owner_id.value;
    form.reset();
    form.owner_id.value = keepOwner;
    form.querySelectorAll('.chip.active').forEach(function (c) { c.classList.remove('active'); });
    preview.textContent = 'Оберіть зацікавленість — система визначить дату фолоу-апу.';
    preview.classList.remove('ready');
    pick.classList.toggle('d-none', !form.querySelector('#whoTarget:checked'));
    window.scrollTo({ top: 0, behavior: 'smooth' });

    if (!navigator.onLine) { say('Немає мережі. Розмову з ' + name + ' збережено на пристрої, надішлю пізніше.', 'warning'); return; }
    flush().then(function (res) {
      if (!res) say('Розмову з ' + name + ' збережено на пристрої, надішлю, щойно з’явиться зв’язок.', 'warning');
      else if (res.rejected) say('Частину записів сервер не прийняв, вони лишилися на пристрої.', 'danger');
      else say('Розмову з ' + name + ' збережено ✓', 'success');
    });
  });

  window.addEventListener('online', function () {
    flush().then(function (res) { if (res && res.saved) say('Надіслано записів: ' + res.saved + ' ✓', 'success'); });
  });
  renderBadge();
  flush();
})();
