const STORAGE_KEY = 'global-knowledge-journal-entries';

const entryForm = document.getElementById('entry-form');
const entriesContainer = document.getElementById('entries');
const clearButton = document.getElementById('clear-button');

function loadEntries() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw ? JSON.parse(raw) : [];
  } catch {
    return [];
  }
}

function saveEntries(entries) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(entries));
}

function renderEntries() {
  const entries = loadEntries();

  if (entries.length === 0) {
    entriesContainer.innerHTML = '<div class="empty">No entries yet. Add your first insight above.</div>';
    return;
  }

  entriesContainer.innerHTML = entries
    .map(
      (entry) => `
        <article class="entry-card">
          <h3>${entry.title}</h3>
          <p>${entry.content}</p>
          <div class="meta">
            ${entry.tags
              .map((tag) => `<span class="tag">${tag}</span>`)
              .join('')}
          </div>
        </article>
      `
    )
    .join('');
}

entryForm.addEventListener('submit', (event) => {
  event.preventDefault();

  const title = document.getElementById('title').value.trim();
  const content = document.getElementById('content').value.trim();
  const tags = document.getElementById('tags').value
    .split(',')
    .map((tag) => tag.trim())
    .filter(Boolean);

  if (!title || !content) {
    return;
  }

  const entries = loadEntries();
  entries.unshift({ title, content, tags });
  saveEntries(entries);
  entryForm.reset();
  renderEntries();
});

clearButton.addEventListener('click', () => {
  localStorage.removeItem(STORAGE_KEY);
  renderEntries();
});

renderEntries();
