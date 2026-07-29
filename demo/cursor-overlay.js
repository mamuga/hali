// Injected into every recorded page so mouse intent remains visible in the cut.
window.__installCursor = () => {
  if (document.getElementById('__hali-demo-cursor')) return;
  const dot = document.createElement('div');
  dot.id = '__hali-demo-cursor';
  dot.style.cssText = `
    position: fixed; width: 18px; height: 18px; border-radius: 50%;
    background: rgba(127, 119, 221, 0.85); border: 2px solid white;
    box-shadow: 0 1px 4px rgba(0,0,0,0.4); pointer-events: none;
    z-index: 999999; transition: transform 60ms linear; left: 0; top: 0;
  `;
  document.body.appendChild(dot);
  document.addEventListener('mousemove', (event) => {
    dot.style.transform = `translate(${event.clientX - 9}px, ${event.clientY - 9}px)`;
  });
};
