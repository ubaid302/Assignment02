(() => {
  const boardEl = document.getElementById('board');
  const scoreEl = document.getElementById('score');
  const movesEl = document.getElementById('moves');
  const messageEl = document.getElementById('message');

  const form = document.getElementById('new-game-form');
  const rowsInput = document.getElementById('rows');
  const colsInput = document.getElementById('cols');
  const typesInput = document.getElementById('types');
  const movesInput = document.getElementById('moves-input');
  const emojiInput = document.getElementById('emoji');
  const hintBtn = document.getElementById('hint-btn');
  const shuffleBtn = document.getElementById('shuffle-btn');

  let state = null;
  let selected = null; // {r, c}

  function setMessage(text, type = '') {
    messageEl.textContent = text || '';
    messageEl.className = `message ${type}`;
  }

  async function fetchState() {
    const res = await fetch('/api/state');
    if (!res.ok) return null;
    const data = await res.json();
    return data.state;
  }

  async function newGame(params) {
    const res = await fetch('/api/new', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(params || {}),
    });
    const data = await res.json();
    if (!data.ok) throw new Error('Failed to start new game');
    return data.state;
  }

  function render() {
    if (!state) return;
    scoreEl.textContent = state.score;
    movesEl.textContent = state.remaining_moves;

    const rows = state.rows;
    const cols = state.cols;
    boardEl.style.setProperty('--rows', rows);
    boardEl.style.setProperty('--cols', cols);
    boardEl.innerHTML = '';
    for (let r = 0; r < rows; r++) {
      for (let c = 0; c < cols; c++) {
        const cell = document.createElement('button');
        cell.type = 'button';
        cell.className = 'cell';
        cell.dataset.r = r;
        cell.dataset.c = c;
        const symbol = state.grid[r][c];
        cell.textContent = symbol;
        if (selected && selected.r === r && selected.c === c) {
          cell.classList.add('selected');
        }
        cell.addEventListener('click', onCellClick);
        boardEl.appendChild(cell);
      }
    }
  }

  function areAdjacent(a, b) {
    return Math.abs(a.r - b.r) + Math.abs(a.c - b.c) === 1;
  }

  async function onCellClick(e) {
    const r = parseInt(e.currentTarget.dataset.r, 10);
    const c = parseInt(e.currentTarget.dataset.c, 10);
    const current = { r, c };

    if (!selected) {
      selected = current;
      render();
      return;
    }

    if (selected.r === r && selected.c === c) {
      selected = null;
      render();
      return;
    }

    if (!areAdjacent(selected, current)) {
      selected = current;
      render();
      return;
    }

    const prev = selected;
    selected = null;
    render();
    setMessage('Swapping...');

    try {
      const res = await fetch('/api/swap', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ r1: prev.r, c1: prev.c, r2: r, c2: c }),
      });
      const data = await res.json();
      if (!data.ok) {
        setMessage(data.error === 'invalid_swap' ? 'Invalid swap' : 'Swap failed', 'error');
        return;
      }
      state = data.state;
      render();
      const parts = [`+${data.gained} pts`, `x${data.chains} chain`];
      if (data.shuffled) parts.push('shuffled');
      setMessage(parts.join(', '), 'success');
    } catch (err) {
      console.error(err);
      setMessage('Swap error', 'error');
    }
  }

  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    setMessage('Starting new game...');
    try {
      state = await newGame({
        rows: parseInt(rowsInput.value, 10),
        cols: parseInt(colsInput.value, 10),
        types: parseInt(typesInput.value, 10),
        moves: parseInt(movesInput.value, 10),
        emoji: !!emojiInput.checked,
      });
      setMessage('');
      selected = null;
      render();
    } catch (err) {
      console.error(err);
      setMessage('Failed to create new game', 'error');
    }
  });

  hintBtn.addEventListener('click', async () => {
    setMessage('Looking for a hint...');
    try {
      const res = await fetch('/api/hint');
      const data = await res.json();
      if (!data.ok || !data.hint) {
        setMessage('No hint available');
        return;
      }
      const { r1, c1, r2, c2 } = data.hint;
      setMessage(`Try (${r1},${c1}) with (${r2},${c2})`);
      // Briefly highlight suggested cells
      document.querySelectorAll('.cell').forEach((el) => el.classList.remove('hint'));
      const a = document.querySelector(`.cell[data-r="${r1}"][data-c="${c1}"]`);
      const b = document.querySelector(`.cell[data-r="${r2}"][data-c="${c2}"]`);
      if (a) a.classList.add('hint');
      if (b) b.classList.add('hint');
      setTimeout(() => {
        document.querySelectorAll('.cell.hint').forEach((el) => el.classList.remove('hint'));
      }, 1000);
    } catch (err) {
      console.error(err);
      setMessage('Hint error', 'error');
    }
  });

  shuffleBtn.addEventListener('click', async () => {
    setMessage('Shuffling...');
    try {
      const res = await fetch('/api/shuffle', { method: 'POST' });
      const data = await res.json();
      if (!data.ok) {
        setMessage('Shuffle failed', 'error');
        return;
      }
      state = data.state;
      render();
      setMessage('Board shuffled');
    } catch (err) {
      console.error(err);
      setMessage('Shuffle error', 'error');
    }
  });

  (async function init() {
    try {
      state = await fetchState();
      if (!state) {
        state = await newGame({});
      }
      render();
    } catch (err) {
      console.error(err);
      setMessage('Failed to load game', 'error');
    }
  })();
})();

