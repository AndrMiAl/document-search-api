const searchForm = document.querySelector('#search-form');
const searchInput = document.querySelector('#search-input');
const resultsList = document.querySelector('#results-list');
const resultsTitle = document.querySelector('#results-title');
const resultCount = document.querySelector('#result-count');
const clearResults = document.querySelector('#clear-results');
const toast = document.querySelector('#toast');

function showToast(message) {
  toast.textContent = message;
  toast.classList.add('show');
  window.clearTimeout(showToast.timer);
  showToast.timer = window.setTimeout(() => toast.classList.remove('show'), 3200);
}

function formatDate(value) {
  return new Intl.DateTimeFormat('ru-RU', { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(value));
}

function renderResults(documents, query) {
  resultsTitle.textContent = query ? `Совпадения для «${query}»` : 'Последние документы';
  resultCount.textContent = query
    ? `${documents.length} ${documents.length === 1 ? 'совпадение' : 'совпадений'}`
    : `${documents.length} последних документов`;
  clearResults.hidden = !query;
  if (!documents.length) {
    const title = query ? 'Ничего не найдено' : 'Пока нет документов';
    const description = query ? 'Проверьте запрос или попробуйте другое слово.' : 'Импортируйте CSV с документами, чтобы начать поиск.';
    resultsList.innerHTML = `<div class="empty-state"><div class="empty-icon">⌕</div><h3>${title}</h3><p>${description}</p></div>`;
    return;
  }
  resultsList.innerHTML = documents.map((document) => `
    <article class="result-card">
      <div class="result-header"><div class="result-id">Документ #${document.id}</div><div class="result-date">${formatDate(document.created_date)}</div></div>
      <p class="result-text result-excerpt">${escapeHtml(document.text)}</p>
      <details class="full-text"><summary>Показать полный текст</summary><p class="result-text">${escapeHtml(document.text)}</p></details>
      <div class="result-header"><div class="tag-list">${(document.rubrics || []).map((rubric) => `<span class="tag">${escapeHtml(rubric)}</span>`).join('')}</div><button class="delete-button" data-delete-id="${document.id}" type="button">Удалить</button></div>
    </article>`).join('');
  resultsList.querySelectorAll('[data-delete-id]').forEach((button) => button.addEventListener('click', () => removeDocument(button.dataset.deleteId)));
}

function escapeHtml(value) {
  return String(value).replace(/[&<>'"]/g, (character) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;' }[character]));
}

async function runSearch(query) {
  if (!query.trim()) {
    await loadLatestDocuments();
    return;
  }
  resultCount.textContent = 'Ищем документы...';
  try {
    const response = await fetch(`/documents/search?q=${encodeURIComponent(query.trim())}`);
    if (!response.ok) throw new Error('Не удалось выполнить поиск');
    renderResults(await response.json(), query.trim());
  } catch (error) {
    showToast(error.message);
    resultCount.textContent = 'Ошибка поиска';
  }
}

async function loadLatestDocuments() {
  resultCount.textContent = 'Загружаем документы...';
  try {
    const response = await fetch('/documents');
    if (!response.ok) throw new Error('Не удалось загрузить документы');
    renderResults(await response.json(), '');
  } catch (error) {
    resultCount.textContent = 'Ошибка загрузки';
    showToast(error.message);
  }
}

async function removeDocument(id) {
  if (!window.confirm(`Удалить документ #${id}?`)) return;
  const response = await fetch(`/documents/${id}`, { method: 'DELETE' });
  if (!response.ok) {
    showToast('Не удалось удалить документ');
    return;
  }
  showToast(`Документ #${id} удалён`);
  if (searchInput.value.trim()) await runSearch(searchInput.value);
  else await loadLatestDocuments();
}

searchForm.addEventListener('submit', (event) => { event.preventDefault(); runSearch(searchInput.value); });
clearResults.addEventListener('click', () => { searchInput.value = ''; loadLatestDocuments(); searchInput.focus(); });

loadLatestDocuments();
