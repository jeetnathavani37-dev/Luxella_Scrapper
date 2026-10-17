/* LUXELLA — gender showcase + wishlist.
   Spec: docs/specs/2026-10-17-gender-showcase-homepage.md
   - <lx-showcase>: MEN/WOMEN switch, category tabs (lazy via the Section Rendering API), rail arrows.
   - <lx-wishlist>: renders saved handles with sections/luxella-wishlist-card.liquid.
   - Wishlist hearts anywhere on the page (delegated). Saved handles stay in this browser only. */
(() => {
  const WISH_KEY = 'luxella:wishlist';
  const GENDER_KEY = 'luxella:gender';
  const MAX_SAVED = 100;
  const ROOT = (window.Shopify && Shopify.routes && Shopify.routes.root) || '/';

  const wishlist = {
    read() {
      try {
        const list = JSON.parse(localStorage.getItem(WISH_KEY) || '[]');
        return Array.isArray(list) ? list.filter((h) => typeof h === 'string') : [];
      } catch (e) {
        return [];
      }
    },
    write(list) {
      try {
        localStorage.setItem(WISH_KEY, JSON.stringify(list.slice(0, MAX_SAVED)));
      } catch (e) {
        /* storage blocked (private mode): hearts still toggle for this page view */
      }
    },
    toggle(handle) {
      const list = this.read();
      const index = list.indexOf(handle);
      if (index === -1) list.unshift(handle);
      else list.splice(index, 1);
      this.write(list);
      return index === -1;
    },
  };

  function announce(from, text) {
    const scope = from.closest('.lx-showcase') || document;
    const live = scope.querySelector('[data-lx-live]');
    if (!live) return;
    live.textContent = '';
    requestAnimationFrame(() => (live.textContent = text));
  }

  function paintHearts(scope = document) {
    const saved = new Set(wishlist.read());
    scope.querySelectorAll('[data-lx-wish]').forEach((button) => {
      const on = saved.has(button.dataset.lxWish);
      button.setAttribute('aria-pressed', String(on));
      button.setAttribute('aria-label', `${on ? 'Remove' : 'Save'} ${button.dataset.lxTitle}`);
    });
    document.querySelectorAll('[data-lx-wish-count]').forEach((count) => {
      count.textContent = String(saved.size);
      count.hidden = saved.size === 0;
    });
  }

  document.addEventListener('click', (event) => {
    const button = event.target.closest('[data-lx-wish]');
    if (!button) return;
    event.preventDefault();
    const added = wishlist.toggle(button.dataset.lxWish);
    paintHearts();
    announce(button, `${button.dataset.lxTitle} ${added ? 'saved' : 'removed from saved pieces'}`);
  });

  window.addEventListener('storage', (event) => {
    if (event.key === WISH_KEY) paintHearts();
  });

  // Image dots follow the card's swipeable image track.
  function initTracks(scope) {
    scope.querySelectorAll('[data-lx-track]:not([data-lx-ready])').forEach((track) => {
      track.setAttribute('data-lx-ready', '');
      const dots = track.closest('.lx-card__frame').querySelectorAll('.lx-dot');
      if (dots.length < 2) return;
      let frame = 0;
      track.addEventListener(
        'scroll',
        () => {
          cancelAnimationFrame(frame);
          frame = requestAnimationFrame(() => {
            const index = Math.round(track.scrollLeft / track.clientWidth);
            dots.forEach((dot, i) => dot.classList.toggle('is-active', i === index));
          });
        },
        { passive: true }
      );
    });
  }

  function railUrl(src, section) {
    return `${src}${src.includes('?') ? '&' : '?'}section_id=${encodeURIComponent(section)}`;
  }

  function errorMessage(href) {
    const p = document.createElement('p');
    p.className = 'lx-empty';
    p.append('These pieces did not load. ');
    const link = document.createElement('a');
    link.href = href;
    link.className = 'lx-viewall';
    link.textContent = 'See them on their page';
    p.append(link);
    return p;
  }

  class LxShowcase extends HTMLElement {
    connectedCallback() {
      this.onClick = this.onClick.bind(this);
      this.onKeydown = this.onKeydown.bind(this);
      this.updateArrows = this.updateArrows.bind(this);
      this.addEventListener('click', this.onClick);
      this.addEventListener('keydown', this.onKeydown);
      this.addEventListener('scroll', this.updateArrows, { capture: true, passive: true });
      this.addEventListener('shopify:block:select', (event) => this.onBlockSelect(event.target));

      initTracks(this);
      paintHearts(this);
      const tab = this.activePanel()?.querySelector('[role="tab"][aria-selected="true"]');
      if (tab) this.loadPanel(this.panelFor(tab));
      this.updateArrows();
    }

    activePanel() {
      return this.querySelector('[data-lx-panel]:not([hidden])');
    }

    panelFor(tab) {
      return document.getElementById(tab.getAttribute('aria-controls'));
    }

    activeRail() {
      return this.activePanel()?.querySelector('.lx-tabpanel:not([hidden]) .lx-rail');
    }

    onClick(event) {
      const gender = event.target.closest('[data-lx-gender]');
      if (gender) return this.setGender(gender.dataset.lxGender);
      const tab = event.target.closest('[role="tab"]');
      if (tab) return this.selectTab(tab);
      const arrow = event.target.closest('[data-lx-scroll]');
      if (arrow) this.scrollRail(Number(arrow.dataset.lxScroll));
    }

    onKeydown(event) {
      const tab = event.target.closest('[role="tab"]');
      if (!tab) return;
      const tabs = Array.from(tab.parentElement.querySelectorAll('[role="tab"]'));
      const index = tabs.indexOf(tab);
      const next = {
        ArrowRight: tabs[(index + 1) % tabs.length],
        ArrowLeft: tabs[(index - 1 + tabs.length) % tabs.length],
        Home: tabs[0],
        End: tabs[tabs.length - 1],
      }[event.key];
      if (!next) return;
      event.preventDefault();
      this.selectTab(next, true);
    }

    setGender(key) {
      const panel = this.querySelector(`[data-lx-panel="${CSS.escape(key)}"]`);
      if (!panel) return;
      this.querySelectorAll('[data-lx-panel]').forEach((p) => (p.hidden = p !== panel));
      this.querySelectorAll('[data-lx-gender]').forEach((b) =>
        b.setAttribute('aria-pressed', String(b.dataset.lxGender === key))
      );
      this.dataset.gender = key;
      this.dataset.theme = panel.dataset.theme;
      try {
        localStorage.setItem(GENDER_KEY, key);
      } catch (e) {
        /* preference just won't persist */
      }
      const tab = panel.querySelector('[role="tab"][aria-selected="true"]');
      if (tab) this.loadPanel(this.panelFor(tab));
      this.updateArrows();
    }

    selectTab(tab, focus = false) {
      tab.parentElement.querySelectorAll('[role="tab"]').forEach((t) => {
        const on = t === tab;
        t.setAttribute('aria-selected', String(on));
        t.tabIndex = on ? 0 : -1;
        const panel = this.panelFor(t);
        if (panel) panel.hidden = !on;
      });
      if (focus) tab.focus();
      tab.scrollIntoView({ block: 'nearest', inline: 'nearest' });
      this.loadPanel(this.panelFor(tab));
      this.updateArrows();
    }

    loadPanel(panel) {
      if (!panel || panel.hasAttribute('data-lx-loaded') || panel.hasAttribute('data-lx-loading')) return;
      const wrap = panel.querySelector('[data-lx-rail-wrap]');
      const src = panel.dataset.lxSrc;
      panel.setAttribute('data-lx-loading', '');
      wrap.setAttribute('aria-busy', 'true');

      fetch(railUrl(src, this.dataset.railSection))
        .then((response) => {
          if (!response.ok) throw new Error(`HTTP ${response.status}`);
          return response.text();
        })
        .then((html) => {
          const doc = new DOMParser().parseFromString(html, 'text/html');
          const rail = doc.querySelector('[data-lx-rail]');
          if (!rail) throw new Error('rail missing from response');
          const empty = doc.querySelector('[data-lx-empty]');
          wrap.replaceChildren(rail, ...(empty ? [empty] : []));
          panel.setAttribute('data-lx-loaded', '');
          initTracks(wrap);
          paintHearts(wrap);
        })
        .catch(() => wrap.replaceChildren(errorMessage(src)))
        .finally(() => {
          panel.removeAttribute('data-lx-loading');
          wrap.removeAttribute('aria-busy');
          this.updateArrows();
        });
    }

    scrollRail(direction) {
      const rail = this.activeRail();
      if (rail) rail.scrollBy({ left: direction * rail.clientWidth * 0.85 });
    }

    updateArrows() {
      const panel = this.activePanel();
      if (!panel) return;
      const rail = this.activeRail();
      const [prev, next] = panel.querySelectorAll('[data-lx-scroll]');
      if (!prev || !next) return;
      const max = rail ? rail.scrollWidth - rail.clientWidth : 0;
      prev.disabled = !rail || rail.scrollLeft <= 2;
      next.disabled = !rail || rail.scrollLeft >= max - 2;
    }

    // Theme editor: selecting a block shows the audience (and tab) it belongs to.
    onBlockSelect(target) {
      const panel = target.closest('[data-lx-panel]');
      if (panel) this.setGender(panel.dataset.lxPanel);
      if (target.matches('[role="tab"]')) this.selectTab(target);
    }
  }

  class LxWishlist extends HTMLElement {
    connectedCallback() {
      this.list = this.querySelector('[data-lx-wishlist-items]');
      this.empty = this.querySelector('[data-lx-wishlist-empty]');
      this.render();
    }

    async render() {
      const handles = wishlist.read().slice(0, 48);
      if (!handles.length) return this.finish();

      const results = [];
      for (let i = 0; i < handles.length; i += 8) {
        results.push(...(await Promise.all(handles.slice(i, i + 8).map((h) => this.fetchCard(h)))));
      }

      const gone = handles.filter((_, i) => results[i].gone);
      if (gone.length) wishlist.write(wishlist.read().filter((h) => !gone.includes(h)));
      results.forEach((result) => result.card && this.list.append(result.card));

      if (!this.list.children.length && results.some((r) => r.failed)) {
        this.list.replaceWith(errorMessage(window.location.href));
        return;
      }
      this.finish();
    }

    fetchCard(handle) {
      return fetch(`${ROOT}products/${encodeURIComponent(handle)}?section_id=${this.dataset.cardSection}`)
        .then((response) => {
          if (response.status === 404) return { gone: true };
          if (!response.ok) return { failed: true };
          return response.text().then((html) => ({
            card: new DOMParser().parseFromString(html, 'text/html').querySelector('[data-lx-card]'),
          }));
        })
        .catch(() => ({ failed: true }));
    }

    finish() {
      this.list.removeAttribute('aria-busy');
      this.empty.hidden = this.list.children.length > 0;
      initTracks(this);
      paintHearts(this);
    }
  }

  if (!customElements.get('lx-showcase')) customElements.define('lx-showcase', LxShowcase);
  if (!customElements.get('lx-wishlist')) customElements.define('lx-wishlist', LxWishlist);
})();
