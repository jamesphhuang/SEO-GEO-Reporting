
document.addEventListener('DOMContentLoaded', () => {
  const buttons = document.querySelectorAll('[data-filter]');
  const cards = document.querySelectorAll('[data-category]');
  buttons.forEach(btn => btn.addEventListener('click', () => {
    const filter = btn.dataset.filter;
    buttons.forEach(b => b.classList.toggle('active', b === btn));
    cards.forEach(card => {
      const ok = filter === 'All' || card.dataset.category === filter;
      card.classList.toggle('hide', !ok);
    });
  }));
});
