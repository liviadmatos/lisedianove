(() => {
  'use strict';

  const app = document.getElementById('app');
  const toastEl = document.getElementById('toast');
  const API_BASE = String(window.LISE_CONFIG?.API_BASE_URL || '').replace(/\/$/, '');
  const state = {
    token: localStorage.getItem('lise_access_token') || '', user: null, view: 'auth', authMode: 'login',
    dashboard: null, classDetail: null, classId: null, classTab: '', classDate: '',
    explore: null, exploreKind: 'both', exploreSearch: '', exploreArea: '', sort: 'asc',
    detail: null, detailType: '', detailBack: 'explore', collections: [], collection: null,
    sources: null, practiceSource: null, practiceGame: '', trailCatalog: null, trailAreas: [],
    gameSession: null, gameFeedback: null, gameIndex: 0, memorySelected: [], memoryPairs: [],
    memoryMatched: new Set(), memoryAttempts: 0, memoryStartedAt: 0, flashRevealed: false, result: null, busy: false,
    studentDetail: null, assessmentTarget: null, assessmentSession: null, assessmentIndex: 0,
    assessmentAnswer: null, assessmentResult: null,
    sidebarCollapsed: localStorage.getItem('lise_sidebar_collapsed') === 'true'
  };

  const GAMES = [
    { id: 'familia_palavras', title: 'Família de palavras', icon: 'FP', description: 'Leia o significado de um radical e marque todos os termos que o utilizam.' },
    { id: 'memoria', title: 'Memória', icon: 'M', description: 'Encontre pares de termos e definições ou de radicais e significados.' },
    { id: 'decifrador', title: 'Decifrador', icon: 'D', description: 'Use a definição biológica como pista e descubra o termo com as letras embaralhadas.' },
    { id: 'flashcard', title: 'Flashcards', icon: 'FC', description: 'Revise os cartões que você desbloqueou ao acertar jogos.' }
  ];

  const esc = (value) => String(value ?? '').replace(/[&<>"']/g, ch => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[ch]));
  const fmtDate = (value, includeTime = true) => {
    if (!value) return 'Ainda não acessou';
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return 'Ainda não acessou';
    return new Intl.DateTimeFormat('pt-BR', includeTime ? { dateStyle: 'short', timeStyle: 'short' } : { dateStyle: 'short' }).format(date);
  };
  const gameTitle = (id) => id === 'avaliacao_trilha' ? 'Avaliação da trilha' : (GAMES.find(g => g.id === id)?.title || id);
  const button = (label, action, cls = 'btn-primary', extra = '') => `<button class="btn ${cls}" type="button" data-action="${action}" ${extra}>${label}</button>`;
  const empty = (title, detail) => `<div class="empty"><strong>${esc(title)}</strong>${esc(detail)}</div>`;

  async function api(path, options = {}) {
    if (!API_BASE) throw new Error('Configure o endereço da API em frontend_spa/config.js.');
    const headers = { Accept: 'application/json' };
    if (options.body !== undefined) headers['Content-Type'] = 'application/json';
    if (state.token) headers.Authorization = `Bearer ${state.token}`;
    let response;
    try {
      response = await fetch(`${API_BASE}/api/v1${path}`, {
        method: options.method || 'GET', headers, credentials: 'omit',
        body: options.body === undefined ? undefined : JSON.stringify(options.body)
      });
    } catch (_error) {
      throw new Error('Não consegui acessar o backend. Confira o endereço da API e a configuração de CORS.');
    }
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      if (response.status === 401 && state.token) {
        localStorage.removeItem('lise_access_token'); state.token = ''; state.user = null;
      }
      throw new Error(data.error || 'Não foi possível concluir essa ação.');
    }
    return data;
  }

  function toast(message) {
    toastEl.textContent = message;
    toastEl.classList.add('show');
    clearTimeout(toast.timer);
    toast.timer = setTimeout(() => toastEl.classList.remove('show'), 3200);
  }

  function setLoading(message = 'Carregando…') {
    app.innerHTML = `<div class="loading">${esc(message)}</div>`;
  }

  function shell(content) {
    if (!state.user) return content;
    const student = state.user.role === 'Aluno';
    const nav = student
      ? [['dashboard', 'IN', 'Início'], ['explore', 'EX', 'Explorar'], ['games', 'GA', 'Games'], ['collections', 'CO', 'Coleções']]
      : [['dashboard', 'PA', 'Painel'], ['explore', 'EX', 'Explorar']];
    return `<div class="app-layout ${state.sidebarCollapsed?'sidebar-collapsed':''}">
      <aside class="sidebar">
        <a class="brand" href="#" data-action="go-dashboard"><span class="brand-mark">L</span><span class="brand-name">LISE</span></a>
        <nav class="nav-list" aria-label="Navegação principal">
          ${nav.map(([view, icon, label]) => `<button class="nav-button ${state.view === view ? 'active' : ''}" data-action="navigate" data-view="${view}"><span class="nav-icon">${icon}</span><span>${label}</span></button>`).join('')}
        </nav>
        <div class="side-bottom"><div class="user-chip"><strong>${esc(state.user.name)}</strong><small>${student ? 'Estudante' : 'Professor'}</small></div><button class="btn btn-plain btn-block" data-action="logout">Sair da conta</button></div>
      </aside>
      <div class="main-column">
        <header class="topbar"><div class="topbar-start"><button class="btn btn-plain btn-small sidebar-toggle" data-action="toggle-sidebar" aria-label="${state.sidebarCollapsed?'Expandir':'Recolher'} navegação">${state.sidebarCollapsed?'Expandir menu':'Recolher menu'}</button><div class="brand"><span class="brand-mark">L</span><span>LISE</span></div></div><div class="topbar-user"><small>${esc(state.user.name)} · ${student ? 'Aluno' : 'Professor'}</small>${button('Sair','logout','btn-plain btn-small')}</div></header>
        <main class="content">${content}</main>
      </div>
    </div>`;
  }

  function renderAuth() {
    const isRegister = state.authMode === 'register';
    const isRecovery = state.authMode === 'recovery';
    const title = isRegister ? 'Crie sua conta' : isRecovery ? 'Recupere sua senha' : 'Que bom ter você de volta';
    let fields = '';
    if (isRegister) fields = `<div class="field"><label for="auth-name">Nome</label><input id="auth-name" name="name" maxlength="150" required autocomplete="name"></div>
      <div class="field"><label for="auth-role">Perfil</label><select id="auth-role" name="role" required><option value="ALUNO">Aluno</option><option value="PROFESSOR">Professor</option></select></div><div class="field" data-teacher-code hidden><label for="teacher-code">Código de acesso do professor</label><input id="teacher-code" name="teacher_code" maxlength="100" autocomplete="off"></div>`;
    fields += `<div class="field"><label for="auth-email">E-mail</label><input id="auth-email" name="email" type="email" maxlength="255" required autocomplete="email"></div>`;
    if (!isRecovery) fields += `<div class="field"><label for="auth-password">Senha</label><input id="auth-password" name="password" type="password" minlength="8" required autocomplete="${isRegister ? 'new-password' : 'current-password'}"></div>`;
    if (!isRegister && !isRecovery) fields += `<label class="check-row"><input type="checkbox" name="remember"><span>Manter conectado</span></label>`;
    const formType = isRegister ? 'register' : isRecovery ? 'recovery' : 'login';
    const submit = isRegister ? 'Criar conta' : isRecovery ? 'Enviar instruções' : 'Entrar';
    app.innerHTML = `<div class="auth-page"><section class="auth-aside"><div class="brand"><span class="brand-mark">L</span> LISE</div><div><div class="eyebrow" style="color:#d7c795">Biologia por etimologia</div><h1 class="auth-title">Descubra a história dentro de cada palavra.</h1><p class="auth-copy">Explore termos e radicais, pratique com jogos e acompanhe seu aprendizado junto da sua turma.</p></div><small>Aprender começa por uma raiz.</small></section>
      <section class="auth-main"><div class="auth-card"><div class="eyebrow">Área de aprendizagem</div><h2>${title}</h2><p>${isRegister ? 'Escolha seu perfil para começar a explorar a LISE.' : isRecovery ? 'Enviaremos um link para o e-mail da sua conta.' : 'Entre para continuar de onde você parou.'}</p>
        <form data-form="${formType}" class="card" style="box-shadow:none;padding:1.2rem;margin-top:1.5rem">${fields}<button class="btn btn-primary btn-block" type="submit">${submit}</button></form>
        <p class="small">${isRegister ? 'Já tem conta? ' : isRecovery ? 'Lembrou a senha? ' : 'Ainda não tem conta? '}<button class="btn btn-plain btn-small" data-action="auth-mode" data-mode="${isRegister || isRecovery ? 'login' : 'register'}">${isRegister || isRecovery ? 'Entrar' : 'Criar conta'}</button></p>
        ${!isRegister && !isRecovery ? `<button class="btn btn-plain btn-small" data-action="auth-mode" data-mode="recovery">Esqueci minha senha</button>` : ''}
      </div></section></div>`;
  }

  function renderDashboard() {
    if (!state.dashboard) { setLoading(); return; }
    const d = state.dashboard;
    if (d.role === 'Professor') {
      const classes = d.classes || [];
      const trails = d.trails || [];
      return `<div class="section-heading"><div><div class="eyebrow">Área do professor</div><h1 class="page-title">Painel da turma</h1><p>Organize trilhas, escolha termos do banco e acompanhe a prática dos estudantes.</p></div><div class="card-actions">${button('+ Nova turma', 'new-class')} ${button('+ Nova trilha', 'new-trail', 'btn-soft')} ${button('Criar termo', 'new-teacher-term', 'btn-plain')}</div></div>
        <div class="grid grid-3"><div class="stat-card"><strong>${classes.length}</strong><span>Turmas</span></div><div class="stat-card"><strong>${trails.length}</strong><span>Trilhas criadas</span></div><div class="stat-card"><strong>${d.areas.length}</strong><span>Áreas de Biologia</span></div></div>
        <div class="split-heading"><h2>Minhas turmas</h2></div>
        ${classes.length ? `<div class="grid grid-3">${classes.map(c => `<article class="card"><div class="card-top"><span class="chip">${esc(c.code)}</span><span class="muted small">${c.alunos?.length || 0} alunos</span></div><h3>${esc(c.name)}</h3><p>${c.trilhas?.length || 0} trilhas atribuídas</p><div class="card-actions">${button('Ver turma →', 'open-class', 'btn-primary btn-small', `data-id="${c.id}"`)}</div></article>`).join('')}</div>` : empty('Você ainda não tem turmas', 'Crie uma turma para compartilhar o código com seus alunos.')}
        <div class="split-heading"><h2>Minhas trilhas</h2><span class="muted small">Apagar uma trilha também remove suas atribuições.</span></div>
        ${trails.length ? `<div class="grid grid-2">${trails.map(t => `<article class="card"><div class="card-top"><span class="chip gold">${esc(t.area || 'Todas as áreas')}</span>${button('Apagar', 'delete-trail', 'btn-danger btn-small', `data-id="${t.id}"`)}</div><h3>${esc(t.name)}</h3><p>${esc(t.description || 'Sem descrição')} · ${t.terms?.length || 0} termos</p></article>`).join('')}</div>` : empty('Nenhuma trilha criada', 'Crie uma trilha e escolha os termos cadastrados que deseja incluir.')}`;
    }
    const classes = d.classes || [];
    const cols = d.collections || [];
    return `<div class="section-heading"><div><div class="eyebrow">Sua área de estudos</div><h1 class="page-title">Olá, ${esc(state.user.name.split(' ')[0])}!</h1><p>Explore palavras, monte suas coleções e pratique no seu ritmo.</p></div><div class="card-actions">${button('Criar coleção', 'new-collection')} ${button('Criar palavra', 'new-student-term', 'btn-soft')}</div></div>
      <div class="grid grid-4"><div class="stat-card"><strong>${d.stats?.xp || 0}</strong><span>XP</span></div><div class="stat-card"><strong>${d.stats?.jogadas || 0}</strong><span>Jogadas</span></div><div class="stat-card"><strong>${d.stats?.streak || 0}</strong><span>Dias seguidos</span></div><div class="stat-card"><strong>${classes.length}</strong><span>Turmas</span></div></div>
      <div class="split-heading"><h2>Minhas turmas</h2>${button('Entrar com código', 'join-class', 'btn-plain btn-small')}</div>
      ${classes.length ? `<div class="grid grid-3">${classes.map(c => `<article class="card"><span class="chip">Turma</span><h3>${esc(c.name)}</h3><p>Abra a turma para ver atividades, trilhas e o ranking de XP.</p><div class="card-actions">${button('Entrar na turma →', 'open-class', 'btn-primary btn-small', `data-id="${c.id}"`)}</div></article>`).join('')}</div>` : empty('Você ainda não entrou em uma turma', 'Peça o código ao professor e entre para acompanhar o ranking e as atividades da turma.')}
      <div class="split-heading"><h2>Minhas coleções</h2>${button('Ver coleções', 'navigate', 'btn-plain btn-small', 'data-view="collections"')}</div>
      ${cols.length ? `<div class="grid grid-3">${cols.slice(0,3).map(c => `<article class="card"><span class="chip gold">${c.terms?.length || 0} termos</span><h3>${esc(c.name)}</h3><div class="card-actions">${button('Abrir', 'open-collection', 'btn-primary btn-small', `data-id="${c.id}"`)} ${button('Praticar', 'practice-collection', 'btn-soft btn-small', `data-id="${c.id}" data-name="${esc(c.name)}"`)}</div></article>`).join('')}</div>` : empty('Crie sua primeira coleção', 'Escolha palavras do banco ou suas palavras pessoais para praticar depois.')}`;
  }

  function renderExplore() {
    const d = state.explore;
    if (!d) { setLoading(); return; }
    const kinds = [['terms','Termos'],['radicals','Radicais'],['both','Termos e radicais'],['favorites','Favoritos']];
    let terms = [...(d.terms || [])], radicals = [...(d.radicals || [])];
    const direction = state.sort === 'asc' ? 1 : -1;
    terms.sort((a,b) => direction * a.name.localeCompare(b.name,'pt-BR'));
    radicals.sort((a,b) => direction * a.name.localeCompare(b.name,'pt-BR'));
    const termGrid = terms.length ? `<div class="grid grid-3">${terms.map(t => `<article class="card term-card" data-action="open-term" data-id="${t.id}"><div class="card-top"><span class="chip">${esc(t.area)}</span>${button(t.favorite ? 'Favorito' : 'Favoritar', 'toggle-favorite', t.favorite ? 'btn-soft btn-small' : 'btn-plain btn-small', `aria-label="${t.favorite ? 'Remover dos favoritos' : 'Favoritar termo'}" data-favorite="${t.favorite}" data-type="term" data-id="${t.id}"`)}</div><h3>${esc(t.name)} ${t.created_by_me ? '<span class="chip gold">Criado por você</span>' : ''}</h3><p class="definition">${esc(t.definition)}</p><div class="radical-list">${(t.radical_list || []).slice(0,3).map(r => `<div class="radical-row"><strong>${esc(r.text)}</strong><span class="small muted">${esc(r.meaning)}</span></div>`).join('')}</div><div class="card-actions"><span class="muted small">${t.radical_list?.length || 0} radical(is)</span></div></article>`).join('')}</div>` : empty('Nenhum termo encontrado', 'Ajuste a busca ou o filtro de área.');
    const radicalGrid = radicals.length ? `<div class="grid grid-3">${radicals.map(r => `<article class="card radical-card" data-action="open-radical" data-id="${r.id}"><div class="card-top"><span class="chip">${esc(r.area)}</span>${button(r.favorite ? 'Favorito' : 'Favoritar', 'toggle-favorite', r.favorite ? 'btn-soft btn-small' : 'btn-plain btn-small', `aria-label="${r.favorite ? 'Remover dos favoritos' : 'Favoritar radical'}" data-favorite="${r.favorite}" data-type="radical" data-id="${r.id}"`)}</div><h3>${esc(r.name)}</h3><p>${esc(r.meaning)}</p><div class="card-actions"><span class="muted small">${esc(r.classification)} · ${r.related_count} termos</span>${button('Ver termos →', 'open-radical', 'btn-soft btn-small', `data-id="${r.id}"`)}</div></article>`).join('')}</div>` : empty('Nenhum radical encontrado', 'Ajuste a busca ou o filtro de área.');
    return `<div class="section-heading"><div><div class="eyebrow">Dicionário etimológico</div><h1 class="page-title">Explorar</h1><p>Pesquise palavras e radicais, veja como eles se conectam e guarde o que quer revisar depois.</p></div>${state.exploreKind==='favorites' ? button('Praticar favoritos','practice-favorites','btn-primary') : ''}</div>
      <form class="toolbar" data-form="explore-filter"><select name="kind">${kinds.map(([v,l]) => `<option value="${v}" ${state.exploreKind===v?'selected':''}>${l}</option>`).join('')}</select><input name="search" value="${esc(state.exploreSearch)}" placeholder="Buscar termo ou significado"><select name="area"><option value="">Todas as áreas</option>${d.areas.map(a => `<option ${state.exploreArea===a?'selected':''}>${esc(a)}</option>`).join('')}</select><button class="btn btn-primary" type="submit">Filtrar</button><button class="btn btn-plain" type="button" data-action="toggle-sort">Ordem ${state.sort === 'asc' ? 'A–Z' : 'Z–A'}</button></form>
      ${(state.exploreKind==='terms' || state.exploreKind==='both' || state.exploreKind==='favorites') ? `<div class="split-heading"><h2>Termos <span class="chip">${terms.length}</span></h2></div>${termGrid}` : ''}
      ${(state.exploreKind==='radicals' || state.exploreKind==='both' || state.exploreKind==='favorites') ? `<div class="split-heading"><h2>Radicais <span class="chip">${radicals.length}</span></h2></div>${radicalGrid}` : ''}`;
  }

  function renderDetail() {
    if (!state.detail) { setLoading(); return; }
    if (state.detailType === 'term') {
      const { term, similar_terms: similar } = state.detail;
      const collections = state.collections || [];
      return `<div class="section-heading"><div><button class="btn btn-plain btn-small" data-action="detail-back">← Voltar</button><div class="eyebrow" style="margin-top:1rem">${esc(term.area)}</div><h1 class="page-title">${esc(term.name)}</h1></div><span class="chip">${term.created_by_me ? 'Criado por você · privado' : 'Termo de Biologia'}</span></div>
        <div class="grid grid-2"><article class="card"><h2>Definição biológica</h2><p>${esc(term.definition)}</p></article><article class="card"><h2>Radicais</h2><div class="radical-list">${(term.radical_list || []).map(r => `<div class="radical-row"><div><strong>${esc(r.text)}</strong><span class="muted small"> · ${esc(r.type)}</span></div><span>${esc(r.meaning)}</span></div>`).join('') || '<p>Sem radicais vinculados.</p>'}</div></article></div>
        <div class="card-actions">${button(term.favorite ? 'Favorito' : 'Favoritar', 'toggle-favorite', term.favorite ? 'btn-soft' : 'btn-primary', `data-favorite="${term.favorite}" data-type="term" data-id="${term.id}"`)}
          ${collections.length ? `<form data-form="add-to-collection" class="card-actions"><input type="hidden" name="term_id" value="${term.id}"><select name="collection_id" required class="field" style="margin:0"><option value="">Adicionar a uma coleção…</option>${collections.map(c=>`<option value="${c.id}">${esc(c.name)}</option>`).join('')}</select><button class="btn btn-soft" type="submit">Adicionar</button></form>` : button('Criar coleção', 'new-collection', 'btn-soft')}
        </div><div class="split-heading"><h2>Termos parecidos</h2><span class="muted small">Compartilham pelo menos um radical</span></div>${similar.length ? `<div class="grid grid-3">${similar.map(t=>`<article class="card term-card" data-action="open-term" data-id="${t.id}"><span class="chip">${esc(t.area)}</span><h3>${esc(t.name)}</h3><p>${esc(t.definition)}</p></article>`).join('')}</div>` : empty('Sem termos relacionados', 'Este termo ainda não compartilha radicais com outros termos visíveis.')}`;
    }
    const { radical, terms } = state.detail;
    return `<div class="section-heading"><div><button class="btn btn-plain btn-small" data-action="detail-back">← Voltar</button><div class="eyebrow" style="margin-top:1rem">${esc(radical.classification)} · ${esc(radical.area)}</div><h1 class="page-title">${esc(radical.name)}</h1><p>${esc(radical.meaning)}</p></div>${button(radical.favorite ? 'Favorito' : 'Favoritar', 'toggle-favorite', radical.favorite ? 'btn-soft' : 'btn-primary', `data-favorite="${radical.favorite}" data-type="radical" data-id="${radical.id}"`)}</div>
      <div class="split-heading"><h2>Termos que usam este radical</h2><span class="chip">${terms.length}</span></div>${terms.length ? `<div class="grid grid-3">${terms.map(t=>`<article class="card term-card" data-action="open-term" data-id="${t.id}"><span class="chip">${esc(t.area)}</span><h3>${esc(t.name)}</h3><p>${esc(t.definition)}</p></article>`).join('')}</div>` : empty('Nenhum termo visível', 'Ainda não há termos ligados a este radical nas suas áreas e turmas.')}`;
  }

  function renderCollections() {
    const rows = state.collections || [];
    return `<div class="section-heading"><div><div class="eyebrow">Espaço pessoal</div><h1 class="page-title">Minhas coleções</h1><p>Monte listas privadas de palavras para praticar com qualquer jogo.</p></div>${button('+ Nova coleção', 'new-collection')}</div>
      ${rows.length ? `<div class="grid grid-3">${rows.map(c=>`<article class="card"><div class="card-top"><span class="chip gold">${c.terms?.length || 0} palavras</span>${button('Apagar', 'delete-collection', 'btn-danger btn-small', `data-id="${c.id}"`)}</div><h3>${esc(c.name)}</h3><div class="card-actions">${button('Abrir coleção', 'open-collection', 'btn-primary btn-small', `data-id="${c.id}"`)} ${button('Praticar', 'practice-collection', 'btn-soft btn-small', `data-id="${c.id}" data-name="${esc(c.name)}"`)}</div></article>`).join('')}</div>` : empty('Nenhuma coleção por enquanto', 'Crie uma coleção e escolha termos do catálogo ou palavras feitas por você.')}`;
  }

  function renderCollection() {
    const c = state.collection;
    if (!c) { setLoading(); return; }
    return `<div class="section-heading"><div><button class="btn btn-plain btn-small" data-action="navigate" data-view="collections">← Coleções</button><div class="eyebrow" style="margin-top:1rem">Lista pessoal</div><h1 class="page-title">${esc(c.name)}</h1><p>${c.terms.length} termo(s) nesta coleção</p></div><div class="card-actions">${button('Praticar', 'practice-collection', 'btn-primary', `data-id="${c.id}" data-name="${esc(c.name)}"`)} ${button('Adicionar palavras', 'new-collection', 'btn-soft')}</div></div>
      ${c.terms.length ? `<div class="grid grid-3">${c.terms.map(t=>`<article class="card term-card"><div class="card-top"><span class="chip">${esc(t.area)}</span>${button('Remover', 'remove-collection-term', 'btn-danger btn-small', `data-collection="${c.id}" data-term="${t.id}"`)}</div><h3 data-action="open-term" data-id="${t.id}">${esc(t.name)} ${t.created_by_me ? '<span class="chip gold">Criado por você</span>' : ''}</h3><p>${esc(t.definition)}</p><button class="btn btn-plain btn-small" data-action="open-term" data-id="${t.id}">Ver termo</button></article>`).join('')}</div>` : empty('Coleção vazia', 'Adicione termos por aqui ou na área Explorar.')}`;
  }

  function renderNewCollection() {
    const items = state.trailCatalog?.terms || [];
    const own = items.filter(t=>t.created_by_me), catalog = items.filter(t=>!t.created_by_me);
    const rows = (list) => list.map(t=>`<label class="check-row"><input type="checkbox" name="term_ids" value="${t.id}"><span><strong>${esc(t.name)}</strong><small class="muted"> · ${esc(t.area)}</small><br><small class="muted">${esc(t.definition)}</small></span></label>`).join('');
    return `<div class="section-heading"><div><button class="btn btn-plain btn-small" data-action="navigate" data-view="collections">← Coleções</button><div class="eyebrow" style="margin-top:1rem">Nova lista privada</div><h1 class="page-title">Criar coleção</h1><p>Suas palavras aparecem primeiro para facilitar a seleção.</p></div></div>
      <form class="card" data-form="collection-create"><div class="field"><label>Nome da coleção</label><input name="name" maxlength="100" required placeholder="Ex.: Revisão de citologia"></div><div class="toolbar"><input data-role="collection-search" placeholder="Pesquisar termos…"><select data-role="collection-area"><option value="">Todas as áreas</option>${state.trailAreas.map(a=>`<option>${esc(a.name)}</option>`).join('')}</select><span class="muted small"><b data-role="selected-count">0</b> selecionado(s)</span></div>
      ${own.length ? `<div class="split-heading"><h2>Palavras criadas por você</h2><span class="chip gold">${own.length}</span></div><div class="checklist" data-list-group="own">${rows(own)}</div>` : ''}
      <div class="split-heading"><h2>Termos do catálogo</h2></div><div class="checklist" data-list-group="catalog">${rows(catalog)}</div><div class="card-actions"><button class="btn btn-primary" type="submit">Salvar coleção</button><button class="btn btn-plain" type="button" data-action="navigate" data-view="collections">Cancelar</button></div></form>`;
  }

  function renderCreateTrail() {
    const d = state.dashboard || {classes:[], areas:[]};
    const terms = state.trailCatalog?.terms || [];
    return `<div class="section-heading"><div><button class="btn btn-plain btn-small" data-action="navigate" data-view="dashboard">← Painel</button><div class="eyebrow" style="margin-top:1rem">Professor</div><h1 class="page-title">Criar trilha</h1><p>Pesquise no banco ou filtre por área; marque quantos termos quiser para compor a trilha.</p></div></div>
      <form class="card" data-form="trail-create"><div class="form-row"><div class="field"><label>Nome da trilha</label><input name="name" maxlength="150" required placeholder="Ex.: Sistema circulatório"></div><div class="field"><label>Área principal</label><select name="area"><option value="">Todas as áreas</option>${state.trailAreas.map(a=>`<option>${esc(a.name)}</option>`).join('')}</select></div></div><div class="field"><label>Descrição</label><textarea name="description" maxlength="3000" placeholder="Objetivo ou observação para os alunos"></textarea></div>
      <div class="split-heading"><h2>Termos da trilha</h2><span class="chip"><b data-role="selected-count">0</b>&nbsp;selecionados</span></div><div class="toolbar"><input data-role="trail-search" placeholder="Pesquisar palavra ou definição"><select data-role="trail-area"><option value="">Todas as áreas</option>${state.trailAreas.map(a=>`<option>${esc(a.name)}</option>`).join('')}</select></div><div class="checklist" data-role="trail-terms">${terms.map(t=>`<label class="check-row term-choice" data-name="${esc((t.name+' '+t.definition).toLocaleLowerCase())}" data-area="${esc(t.area)}"><input type="checkbox" name="term_ids" value="${t.id}"><span><strong>${esc(t.name)}</strong>${t.created_by_me ? ' <small class="chip gold">Criado por você</small>' : ''}<br><small class="muted">${esc(t.area)} · ${esc(t.definition)}</small></span></label>`).join('')}</div>
      ${d.classes.length ? `<div class="split-heading"><h2>Atribuir agora</h2><span class="muted small">Opcional</span></div><div class="field"><label>Prazo para as turmas selecionadas (opcional)</label><input type="date" name="due_date"></div><div class="checklist">${d.classes.map(c=>`<label class="check-row"><input type="checkbox" name="class_ids" value="${c.id}"><span><strong>${esc(c.name)}</strong> · código ${esc(c.code)}</span></label>`).join('')}</div>` : '<div class="notice">Você poderá atribuir esta trilha a uma turma depois de criá-la.</div>'}
      <div class="card-actions"><button class="btn btn-primary" type="submit">Salvar trilha</button><button class="btn btn-plain" type="button" data-action="navigate" data-view="dashboard">Cancelar</button></div></form>`;
  }

  function renderTeacherTerm() {
    const d = state.dashboard || {classes:[], areas:[]};
    return `<div class="section-heading"><div><button class="btn btn-plain btn-small" data-action="navigate" data-view="dashboard">← Painel</button><div class="eyebrow" style="margin-top:1rem">Professor</div><h1 class="page-title">Criar termo para a turma</h1><p>O termo e seus radicais ficam privados até serem compartilhados com as turmas selecionadas.</p></div></div>
      <form class="card" data-form="teacher-term"><div class="form-row"><div class="field"><label>Palavra completa</label><input name="name" maxlength="200" required></div><div class="field"><label>Área</label><select name="area_id" required>${d.areas.map(a=>`<option value="${a.id}">${esc(a.name)}</option>`).join('')}</select></div></div><div class="field"><label>Definição biológica</label><textarea name="definition" maxlength="5000" required></textarea></div><div class="field"><label>Radicais, na ordem da palavra</label><textarea name="radicals" required placeholder="hemo | sangue | PREFIXO\nlogia | estudo | SUFIXO"></textarea><small class="muted">Uma linha por radical: texto | significado | PREFIXO, RADICAL ou SUFIXO.</small></div><div class="form-row"><div class="field"><span class="field-label">Compartilhar com turmas</span><div class="checklist">${d.classes.map(c=>`<label class="check-row"><input type="checkbox" name="class_ids" value="${c.id}"><span>${esc(c.name)}</span></label>`).join('')}</div></div><div class="field"><span class="field-label">Adicionar a trilhas</span><div class="checklist">${(d.trails || []).map(t=>`<label class="check-row"><input type="checkbox" name="trail_ids" value="${t.id}"><span>${esc(t.name)}</span></label>`).join('') || '<p class="muted small">Crie uma trilha antes ou compartilhe diretamente com uma turma.</p>'}</div></div></div><div class="notice">Escolha pelo menos uma turma ou trilha. O termo ficará disponível somente para esses destinos e para você.</div><button class="btn btn-primary" type="submit">Salvar termo</button></form>`;
  }

  function renderStudentTerm() {
    const areas = state.trailAreas;
    const radicals = state.trailCatalog?.radicals || [];
    const collections = state.collections || [];
    return `<div class="section-heading"><div><button class="btn btn-plain btn-small" data-action="navigate" data-view="dashboard">← Início</button><div class="eyebrow" style="margin-top:1rem">Palavra pessoal</div><h1 class="page-title">Criar termo</h1><p>Este termo e sua definição ficarão visíveis apenas para você. Escolha radicais existentes no banco para relacionar o termo com o catálogo e adicioná-lo a uma coleção.</p></div></div>
      <form class="card" data-form="student-term"><div class="form-row"><div class="field"><label>Palavra completa</label><input name="name" maxlength="200" required></div><div class="field"><label>Área (opcional)</label><select name="area_id"><option value="">Geral</option>${areas.map(a=>`<option value="${a.id}">${esc(a.name)}</option>`).join('')}</select></div></div><div class="field"><label>Definição biológica</label><textarea name="definition" maxlength="5000" required></textarea></div><div class="field"><label>Radicais do banco (selecione de 1 a 10)</label><input data-role="radical-search" placeholder="Pesquisar radical ou significado"><div class="checklist" data-role="radical-choices">${radicals.map(r=>`<label class="check-row radical-choice" data-search="${esc((r.name+' '+r.meaning).toLocaleLowerCase())}"><input type="checkbox" name="radical_ids" value="${r.id}"><span><strong>${esc(r.name)}</strong> — ${esc(r.meaning)} <small class="muted">(${esc(r.classification)})</small></span></label>`).join('')}</div></div><div class="field"><label>Adicionar a uma coleção (opcional)</label><select name="collection_id"><option value="">Não adicionar agora</option>${collections.map(c=>`<option value="${c.id}">${esc(c.name)}</option>`).join('')}</select></div><button class="btn btn-primary" type="submit">Salvar palavra privada</button></form>`;
  }

  function renderClass() {
    const d = state.classDetail;
    if (!d) { setLoading(); return; }
    const teacher = d.role === 'Professor';
    const tabs = teacher ? [['students','Alunos'],['daily','XP por dia'],['results','Avaliações'],['trails','Trilhas']] : [['feed','Atividades'],['rank','Ranking XP'],['trails','Trilhas']];
    let body = '';
    if (state.classTab === 'feed') body = renderFeed(d.feed || []);
    if (state.classTab === 'students') body = renderStudents(d.students || []);
    if (state.classTab === 'rank') body = renderRank(d);
    if (state.classTab === 'daily') body = renderDaily(d);
    if (state.classTab === 'results') body = renderAssessmentResults(d.assessment_results || []);
    if (state.classTab === 'trails') body = renderClassTrails(d, teacher);
    return `<div class="section-heading"><div><button class="btn btn-plain btn-small" data-action="navigate" data-view="dashboard">← ${teacher?'Painel':'Minhas turmas'}</button><div class="eyebrow" style="margin-top:1rem">${teacher?'Área do professor':'Sua turma'}</div><h1 class="page-title">${esc(d.name)}</h1><p>${teacher ? `Código de entrada: <strong>${esc(d.code)}</strong> · Acompanhe o andamento das trilhas, as avaliações e o último acesso.` : 'Acompanhe até 15 atividades recentes, pratique as trilhas e veja o ranking de XP.'}</p></div></div>
      <div class="tabs">${tabs.map(([id,label])=>`<button class="tab ${state.classTab===id?'active':''}" data-action="class-tab" data-tab="${id}">${label}</button>`).join('')}</div>${body}`;
  }

  function renderFeed(feed) {
    return `<div class="card"><div class="card-top"><div><h2>Atividades recentes da turma</h2><p class="muted small">As 15 ações mais recentes aparecem aqui quando você entra nesta turma.</p></div><span class="chip">${feed.length}/15</span></div>${feed.length ? `<div class="feed-list">${feed.map(f=>`<div class="feed-item"><div><strong>${esc(f.student)}</strong> praticou <b>${esc(gameTitle(f.game))}</b><div class="muted small">${f.correct}/${f.total} acerto(s) · ${f.score}%</div></div><time class="muted small">${fmtDate(f.at)}</time></div>`).join('')}</div>` : empty('Ainda sem atividades', 'As atividades feitas dentro das trilhas desta turma aparecerão aqui.')}</div>`;
  }

  function renderStudents(students) {
    return `<div class="card"><h2>Alunos desta turma</h2><p class="muted small">Abra um aluno para ver, somente nesta turma, o andamento de cada trilha atribuída.</p>${students.length ? `<div class="table-wrap"><table><thead><tr><th>#</th><th>Aluno</th><th>Trilhas</th><th>XP na turma</th><th>XP hoje</th><th>Último acesso</th><th></th></tr></thead><tbody>${students.map((s,i)=>`<tr><td class="rank">${i+1}</td><td><strong>${esc(s.name)}</strong><br><small class="muted">${esc(s.email)}</small></td><td><span class="chip ${s.late_trails?'danger':'gold'}">${esc(s.trail_status)}</span>${s.assigned_trails?`<br><small class="muted">${s.pending_trails} pendente(s)</small>`:''}</td><td>${s.total_xp}</td><td>${s.daily_xp}</td><td>${fmtDate(s.last_access)}</td><td>${button('Ver detalhes','open-student','btn-soft btn-small',`data-id="${esc(s.user_id)}"`)}</td></tr>`).join('')}</tbody></table></div>` : empty('Nenhum aluno nesta turma', 'Compartilhe o código de entrada para que os alunos possam participar.')}</div>`;
  }

  function renderStudentDetail() {
    const detail = state.studentDetail;
    if (!detail) { setLoading(); return; }
    const s = detail.student;
    return `<div class="section-heading"><div><button class="btn btn-plain btn-small" data-action="back-to-class">← ${esc(detail.class_name)}</button><div class="eyebrow" style="margin-top:1rem">Acompanhamento da turma</div><h1 class="page-title">${esc(s.name)}</h1><p>${esc(s.email)} · Último acesso: ${fmtDate(s.last_access)}</p></div></div>
      <div class="grid grid-2"><div class="stat-card"><strong>${s.total_xp}</strong><span>XP nesta turma</span></div><div class="stat-card"><strong>${s.daily_xp}</strong><span>XP hoje nesta turma</span></div></div>
      <div class="split-heading"><h2>Trilhas atribuídas nesta turma</h2></div>
      ${detail.trails.length ? `<div class="grid grid-2">${detail.trails.map(t=>`<article class="card"><div class="card-top"><span class="chip">${esc(t.area)}</span><span class="chip ${['atrasado','concluida_com_atraso'].includes(t.status)?'danger':'gold'}">${esc(t.status_label)}</span></div><h3>${esc(t.name)}</h3><p>${t.played} de ${t.total} termos praticados (${t.percent}%)</p><div class="progress-track"><div class="progress-fill" style="width:${t.percent}%"></div></div><p class="muted small">Prazo: ${t.due_date?fmtDate(t.due_date,false):'Sem prazo'}</p><p>${t.completed?'Trilha concluída.':t.assessment?.passed?'Avaliação aprovada; falta praticar todos os termos.':t.assessment?'Avaliação ainda não aprovada.': 'Avaliação ainda não configurada pelo professor.'}</p>${t.attempts.length?`<div class="table-wrap"><table style="min-width:0"><thead><tr><th>Tentativa</th><th>Nota</th><th>Resultado</th><th>Data</th></tr></thead><tbody>${t.attempts.map((a,i)=>`<tr><td>${i+1}</td><td>${a.score}%</td><td>${a.passed?'Aprovado':'Não aprovado'}</td><td>${fmtDate(a.played_at)}</td></tr>`).join('')}</tbody></table></div>`:''}</article>`).join('')}</div>`:empty('Nenhuma trilha atribuída', 'Esta turma ainda não tem trilhas para acompanhar.')}`;
  }

  function renderAssessmentConfig() {
    const target=state.assessmentTarget;
    if (!target) { setLoading(); return; }
    const a=target.assessment || {};
    return `<div class="section-heading"><div><button class="btn btn-plain btn-small" data-action="back-to-class">← Voltar para a turma</button><div class="eyebrow" style="margin-top:1rem">Avaliação do professor</div><h1 class="page-title">${a.id?'Editar avaliação':'Configurar avaliação'}</h1><p>${esc(target.trail_name)} · A avaliação só fica disponível ao aluno depois que ele praticar todos os termos da trilha.</p></div></div>
      <form class="card question" data-form="assessment-config"><div class="field"><label>Título</label><input name="title" maxlength="150" required value="${esc(a.title || `Avaliação: ${target.trail_name}`)}"></div><div class="form-row"><div class="field"><label>Quantidade de questões</label><input name="question_count" type="number" min="1" max="50" value="${a.question_count || 10}" required></div><div class="field"><label>Nota mínima (%)</label><input name="pass_score" type="number" min="0" max="100" value="${a.pass_score ?? 70}" required></div></div><div class="form-row"><div class="field"><label>Conteúdo</label><select name="content"><option value="ambos" ${!a.content||a.content==='ambos'?'selected':''}>Termos e radicais</option><option value="termos" ${a.content==='termos'?'selected':''}>Somente termos</option><option value="radicais" ${a.content==='radicais'?'selected':''}>Somente radicais</option></select></div><div class="field"><label>Formato</label><select name="mode"><option value="misto" ${!a.mode||a.mode==='misto'?'selected':''}>Misto</option><option value="termo_definicao" ${a.mode==='termo_definicao'?'selected':''}>Termo para definição</option><option value="definicao_termo" ${a.mode==='definicao_termo'?'selected':''}>Definição para termo</option><option value="radical_significado" ${a.mode==='radical_significado'?'selected':''}>Radical para significado</option><option value="significado_radical" ${a.mode==='significado_radical'?'selected':''}>Significado para radical</option></select></div></div><button class="btn btn-primary" type="submit">Salvar avaliação</button></form>`;
  }

  function renderAssessment() {
    const session=state.assessmentSession;
    if (!session) { setLoading(); return; }
    const q=session.questions[state.assessmentIndex];
    if (!q) { setLoading('Preparando avaliação…'); return; }
    const progress=Math.round(state.assessmentIndex/session.total*100);
    return `<section class="card question"> <div class="eyebrow">Avaliação da trilha · Questão ${state.assessmentIndex+1} de ${session.total}</div><div class="progress-track"><div class="progress-fill" style="width:${progress}%"></div></div><h1 class="question-title">${esc(q.prompt)}</h1>${state.assessmentAnswer?`<div class="feedback ${state.assessmentAnswer.correct?'good':'bad'}"><strong>${state.assessmentAnswer.correct?'Resposta correta':'Resposta incorreta'}</strong><p>Resposta: ${esc(state.assessmentAnswer.answer)}</p></div><div class="card-actions">${button(state.assessmentIndex+1<session.total?'Próxima questão':'Finalizar avaliação','assessment-next','btn-primary')}</div>`:`<form data-form="assessment-answer"><div class="option-list">${q.options.map(o=>`<label class="option"><input type="radio" name="answer" value="${esc(o.id)}" required><span>${esc(o.label)}</span></label>`).join('')}</div><button class="btn btn-primary" type="submit">Responder</button></form>`}</section>`;
  }

  function renderAssessmentResult() {
    const r=state.assessmentResult;
    if (!r) { setLoading(); return; }
    return `<section class="card question" style="text-align:center"><div class="eyebrow">Avaliação concluída</div><h1 class="page-title">${r.score}%</h1><p>Você acertou ${r.correct} de ${r.total} questões. Nota mínima: ${r.pass_score}%.</p><p class="chip ${r.passed?'gold':''}">${r.passed?'Avaliação aprovada':'Tente novamente depois de revisar a trilha'}</p><div class="card-actions" style="justify-content:center">${button('Voltar à turma','open-class','btn-primary',`data-id="${state.classId}"`)}</div></section>`;
  }

  function renderRank(d) {
    const all = d.leaderboard || [], day = d.daily_leaderboard || [];
    return `<div class="grid grid-2"><article class="card"><div class="card-top"><div><h2>Ranking da turma</h2><p class="muted small">XP acumulado nas atividades desta turma.</p></div><span class="chip gold">Geral</span></div>${rankTable(all)}</article><article class="card"><div class="card-top"><div><h2>XP do dia</h2><p class="muted small">Atualizado por dia no fuso de Brasília.</p></div><span class="chip">${esc(d.daily_date)}</span></div>${rankTable(day)}</article></div>`;
  }

  function rankTable(rows) {
    return rows.length ? `<div class="table-wrap"><table style="min-width:0"><thead><tr><th>#</th><th>Aluno</th><th>XP</th></tr></thead><tbody>${rows.map(r=>`<tr ${r.is_me?'style="background:#f2f6ef"':''}><td class="rank">${r.rank}</td><td>${esc(r.name)} ${r.is_me?'<small class="chip">Você</small>':''}</td><td><strong>${r.xp}</strong></td></tr>`).join('')}</tbody></table></div>` : empty('Sem alunos para ranquear', 'O ranking aparece quando estudantes entram na turma.');
  }

  function renderDaily(d) {
    const rows = d.daily_leaderboard || [];
    return `<div class="card"><div class="card-top"><div><h2>Ranking diário de XP</h2><p class="muted small">Selecione um dia para comparar o XP obtido por cada estudante.</p></div><label class="field" style="margin:0"><span class="field-label">Dia</span><input type="date" data-role="class-date" value="${esc(d.daily_date)}"></label></div><div style="margin-top:1rem">${rankTable(rows)}</div></div>`;
  }

  function renderAssessmentResults(rows) {
    return `<div class="card"><h2>Notas das avaliações de trilha</h2><p class="muted small">A avaliação é uma etapa do professor, separada dos jogos de prática.</p>${rows.length ? `<div class="table-wrap"><table><thead><tr><th>Aluno</th><th>Trilha</th><th>Avaliação</th><th>Nota</th><th>Resultado</th><th>Data</th></tr></thead><tbody>${rows.map(q=>`<tr><td>${esc(q.student)}</td><td>${esc(q.trail)}</td><td>${esc(q.assessment)}</td><td><strong>${q.score}%</strong><br><small class="muted">${q.correct}/${q.total} questões</small></td><td><span class="chip ${q.passed?'gold':''}">${q.passed?'Aprovado':'Não aprovado'}</span></td><td>${fmtDate(q.played_at)}</td></tr>`).join('')}</tbody></table></div>` : empty('Nenhuma avaliação concluída', 'Configure uma avaliação em uma trilha atribuída para registrar as notas dos alunos.')}</div>`;
  }

  function renderClassTrails(d, teacher) {
    const trails = d.trails || [];
    let assign = '';
    if (teacher) {
      const used = new Set(trails.map(t=>t.id));
      const available = (d.available_trails || []).filter(t=>!used.has(t.id));
      assign = `<form data-form="assign-trail" class="toolbar"><select name="trail_id" required><option value="">Atribuir uma trilha existente…</option>${available.map(t=>`<option value="${t.id}">${esc(t.name)} · ${esc(t.area)}</option>`).join('')}</select><label class="small muted">Prazo <input type="date" name="due_date"></label><button class="btn btn-primary" type="submit">Atribuir</button><button class="btn btn-soft" type="button" data-action="new-trail">Criar trilha</button></form>`;
    }
    return `${assign}${trails.length ? `<div class="grid grid-2">${trails.map(t=>{
      const learning=t.status_label ? `<div class="trail-progress"><span>${t.played || 0} de ${t.total || t.terms?.length || 0} termos praticados</span><span class="chip ${['atrasado','concluida_com_atraso'].includes(t.status)?'danger':''}">${esc(t.status_label)}</span></div><div class="progress-track"><div class="progress-fill" style="width:${t.progress ?? 0}%"></div></div>` : `<p class="muted small">${t.terms?.length || 0} termos · ${t.due_date ? `Prazo: ${fmtDate(t.due_date,false)}` : 'Sem prazo definido'}</p>`;
      const assessmentAction=teacher ? button(t.assessment?'Editar avaliação':'Configurar avaliação','configure-assessment','btn-soft btn-small',`data-assignment="${t.assignment_id}" data-trail="${t.id}" data-name="${esc(t.name)}" data-class="${d.id}"`) : t.assessment ? button(t.assessment.passed?'Avaliação aprovada':t.assessment.can_start?'Fazer avaliação':'Pratique todos os termos primeiro','start-assessment',t.assessment.can_start?'btn-soft btn-small':'btn-plain btn-small',`data-assignment="${t.assignment_id}" data-class="${d.id}" ${t.assessment.can_start?'':'disabled'}`) : '<span class="muted small">Aguardando avaliação do professor</span>';
      const practice=teacher?'':button('Praticar trilha','practice-trail','btn-primary btn-small',`data-assignment="${t.assignment_id}" data-trail="${t.id}" data-name="${esc(t.name)}" data-class="${d.id}"`);
      return `<article class="card"><div class="card-top"><span class="chip">${esc(t.area)}</span>${teacher?button('Remover da turma','unassign-trail','btn-danger btn-small',`data-id="${t.id}" data-class="${d.id}"`):`<span class="chip gold">${t.progress ?? 0}%</span>`}</div><h3>${esc(t.name)}</h3>${learning}<div class="card-actions">${teacher?assessmentAction:button('Ver termos','open-trail','btn-plain btn-small',`data-id="${t.id}" data-assignment="${t.assignment_id}"`)}${practice}</div></article>`;
    }).join('')}</div>` : empty('Nenhuma trilha atribuída', teacher ? 'Crie uma trilha ou atribua uma das existentes.' : 'Seu professor ainda não atribuiu uma trilha a esta turma.')}`;
  }

  function renderTrail() {
    const t = state.collection; // shared detail slot for this simple view
    if (!t) { setLoading(); return; }
    return `<div class="section-heading"><div><button class="btn btn-plain btn-small" data-action="back-to-class">← Voltar para a turma</button><div class="eyebrow" style="margin-top:1rem">${esc(t.area)}</div><h1 class="page-title">${esc(t.name)}</h1><p>${esc(t.description || '')} · ${t.term_items.length} termos</p></div>${button('Praticar trilha', 'practice-trail', 'btn-primary', `data-assignment="${t.assignment_id}" data-trail="${t.id}" data-name="${esc(t.name)}" data-class="${t.class_id}"`)}</div>
      ${t.term_items.length ? `<div class="grid grid-3">${t.term_items.map(term=>`<article class="card term-card" data-action="open-term" data-id="${term.id}"><div class="card-top"><span class="chip">${esc(term.area)}</span>${button(term.favorite?'Favorito':'Favoritar','toggle-favorite',term.favorite?'btn-soft btn-small':'btn-plain btn-small',`data-favorite="${term.favorite}" data-type="term" data-id="${term.id}"`)}</div><h3>${esc(term.name)}</h3><p>${esc(term.definition)}</p></article>`).join('')}</div>` : empty('Trilha sem termos', 'O professor pode adicionar termos do catálogo a esta trilha.')}`;
  }

  function renderGames() {
    return `<div class="section-heading"><div><div class="eyebrow">Prática com o banco de Biologia</div><h1 class="page-title">Games</h1><p>Escolha um jogo. Depois, selecione uma área, trilha, coleção ou seus favoritos como conteúdo de prática.</p></div></div><div class="grid grid-3">${GAMES.map(g=>`<article class="card game-card"><span class="game-icon">${g.icon}</span><h3>${g.title}</h3><p>${g.description}</p><div class="card-actions">${button('Escolher conteúdo →','select-game','btn-primary btn-small',`data-game="${g.id}"`)}</div></article>`).join('')}</div>`;
  }

  function renderSources() {
    const s = state.sources;
    if (!s) { setLoading(); return; }
    const areaCards = s.areas.map(a=>`<button class="card" data-action="choose-source" data-type="area" data-name="${esc(a.name)}"><span class="chip">Área</span><h3>${esc(a.name)}</h3><p>Termos cadastrados nesta área.</p></button>`).join('');
    const trailCards = s.trails.map(t=>`<button class="card" data-action="choose-source" data-type="trail" data-id="${t.assignment_id}" data-class="${t.class_id}" data-name="${esc(t.name)}"><span class="chip gold">${esc(t.class_name)}</span><h3>${esc(t.name)}</h3><p>Trilha atribuída · ${esc(t.area)}</p></button>`).join('');
    const collectionCards = s.collections.map(c=>`<button class="card" data-action="choose-source" data-type="collection" data-id="${c.id}" data-name="${esc(c.name)}"><span class="chip">Coleção</span><h3>${esc(c.name)}</h3><p>Suas palavras selecionadas.</p></button>`).join('');
    return `<div class="section-heading"><div><button class="btn btn-plain btn-small" data-action="games-back">← Games</button><div class="eyebrow" style="margin-top:1rem">${state.practiceGame ? esc(gameTitle(state.practiceGame)) : 'Escolha um jogo'}</div><h1 class="page-title">Escolha o conteúdo</h1><p>Os jogos montam perguntas automaticamente a partir dos seus termos, radicais e relações cadastrados.</p></div></div>
      <div class="card-actions" style="margin-bottom:1rem">${button(`Favoritos (${s.favorites_count})`, 'choose-source', 'btn-soft', 'data-type="favorites" data-name="Seus favoritos"')}</div>
      ${s.trails.length ? `<div class="split-heading"><h2>Trilhas das suas turmas</h2></div><div class="grid grid-3">${trailCards}</div>` : ''}
      ${s.collections.length ? `<div class="split-heading"><h2>Suas coleções</h2></div><div class="grid grid-3">${collectionCards}</div>` : `<div class="notice">Você ainda não tem coleção. Crie uma em Coleções ou pratique por área.</div>`}
      <div class="split-heading"><h2>Áreas</h2></div><div class="grid grid-3">${areaCards}</div>`;
  }

  function renderChooseGame() {
    const source = state.practiceSource;
    return `<div class="section-heading"><div><button class="btn btn-plain btn-small" data-action="practice-back">← Voltar</button><div class="eyebrow" style="margin-top:1rem">Conteúdo selecionado</div><h1 class="page-title">${esc(source?.name || 'Seus favoritos')}</h1><p>Agora escolha como quer praticar.</p></div></div><div class="grid grid-3">${GAMES.map(g=>`<article class="card game-card"><span class="game-icon">${g.icon}</span><h3>${g.title}</h3><p>${g.description}</p><div class="card-actions">${button('Jogar →','configure-game','btn-primary btn-small',`data-game="${g.id}"`)}</div></article>`).join('')}</div>`;
  }

  function renderGameConfig() {
    const game = GAMES.find(g=>g.id===state.practiceGame);
    const source = state.practiceSource;
    const modeSelector = state.practiceGame === 'memoria' ? `<div class="field"><label>Tipo de pares</label><select name="mode"><option value="termo_definicao">Termos e definições</option><option value="radical_significado">Radicais e significados</option></select></div>` : '';
    const count = state.practiceGame === 'memoria' ? `<div class="field"><label>Quantidade de pares</label><select name="question_count"><option value="6">6 pares</option><option value="8">8 pares</option><option value="10">10 pares</option></select></div>` : `<div class="field"><label>Quantidade de questões</label><select name="question_count"><option value="5">5 questões</option><option value="10" selected>10 questões</option><option value="15">15 questões</option><option value="20">20 questões</option></select></div>`;
    return `<div class="section-heading"><div><button class="btn btn-plain btn-small" data-action="choose-game-back">← Jogos</button><div class="eyebrow" style="margin-top:1rem">Preparar prática</div><h1 class="page-title">${game?.icon || ''} ${esc(game?.title || '')}</h1><p>Conteúdo: <strong>${esc(source?.name || '')}</strong></p></div></div><form class="card question" data-form="game-config">${modeSelector}${count}<button class="btn btn-primary" type="submit">Começar</button></form>`;
  }

  function renderGameQuestion() {
    const session = state.gameSession;
    if (!session) { setLoading(); return; }
    const question = session.questions[state.gameIndex];
    if (!question) { return ''; }
    const progress = Math.round(state.gameIndex / session.questions.length * 100);
    const header = `<div class="eyebrow">${esc(gameTitle(session.game))} · Questão ${state.gameIndex+1} de ${session.questions.length}</div><div class="progress-track"><div class="progress-fill" style="width:${progress}%"></div></div>`;
    if (state.gameFeedback) {
      const f = state.gameFeedback.feedback || {};
      const correctText = f.correct_answer ? `<p>Resposta: <strong>${esc(f.correct_answer)}</strong></p>` : '';
      const roots = f.radicals?.length ? `<p>Radicais: ${f.radicals.map(r=>`<b>${esc(r.text)}</b> (${esc(r.meaning)})`).join(' · ')}</p>` : '';
      const family = f.correct_terms?.length ? `<div class="family-feedback"><p><strong>Você marcou corretamente:</strong> ${f.correct_selected?.length ? f.correct_selected.map(esc).join(', ') : 'nenhum termo'}</p><p><strong>Faltaram:</strong> ${f.omitted_terms?.length ? f.omitted_terms.map(esc).join(', ') : 'nenhum termo'}</p><p><strong>Não se aplicavam:</strong> ${f.incorrect_terms?.length ? f.incorrect_terms.map(esc).join(', ') : 'nenhum termo'}</p><p><strong>Termos relacionados:</strong> ${f.correct_terms.map(esc).join(', ')}</p></div>` : '';
      const favorites = [...(f.favorite_terms || []).map(x=>({ ...x, type:'term', text:x.name })), ...(f.favorite_radicals || []).map(x=>({ ...x, type:'radical', text:x.name }))];
      const favoriteActions = favorites.length ? `<div class="card-actions">${favorites.map(x=>button(`${x.favorite?'Favorito':'Favoritar'}: ${esc(x.text)}`, 'toggle-game-favorite', x.favorite?'btn-soft btn-small':'btn-plain btn-small', `data-favorite="${x.favorite}" data-type="${x.type}" data-id="${x.id}"`)).join('')}</div>` : '';
      const radicalReveal=f.radical?`<p>Radical: <strong>${esc(f.radical)}</strong></p>`:'';
      return `<section class="card question">${header}<div class="feedback ${state.gameFeedback.correct?'good':'bad'}"><strong>${state.gameFeedback.correct ? 'Muito bem!' : 'Vamos revisar esta resposta.'}</strong><p>${state.gameFeedback.correct ? `Você recebeu ${state.gameFeedback.xp || 0} XP.` : 'Confira a resposta correta e tente novamente na próxima rodada.'}</p>${correctText}${roots}${family}${radicalReveal}${f.flashcard_unlocked?'<p>Você desbloqueou um flashcard deste termo.</p>':''}</div>${favoriteActions}<div class="card-actions">${button(state.gameIndex+1 < session.questions.length ? 'Próxima questão →' : 'Ver resultado', 'next-question', 'btn-primary')}</div></section>`;
    }
    if (session.game === 'familia_palavras') return `<section class="card question">${header}<form data-form="game-answer"><h2 class="question-title">Leia o significado: “${esc(question.prompt)}”</h2><p>Marque todos os termos que usam esse radical. Você pode escolher várias palavras.</p><div class="option-list">${question.options.map(o=>`<label class="option"><input type="checkbox" name="answer" value="${o.id}"><span>${esc(o.name)}</span></label>`).join('')}</div><button class="btn btn-primary">Conferir termos</button></form></section>`;
    if (session.game === 'decifrador') return `<section class="card question">${header}<h2 class="question-title">Que termo corresponde a esta definição?</h2><p>${esc(question.clue)}</p><div class="letter-bank">${question.letters.map(l=>`<span class="letter">${esc(l)}</span>`).join('')}</div><p class="muted small">Radicais: ${question.radicals.map(r=>`${esc(r.text)} — ${esc(r.meaning)}`).join(' · ')}</p><form data-form="game-answer"><div class="field"><label>Sua resposta</label><input name="answer" autocomplete="off" required></div><button class="btn btn-primary">Conferir</button></form></section>`;
    if (session.game === 'flashcard') return `<section class="card question">${header}<div class="eyebrow">Flashcard</div><h2 class="question-title">${esc(question.term_name)}</h2>${state.flashRevealed ? `<div class="feedback good"><strong>Definição</strong><p>${esc(question.definition)}</p><div class="radical-list">${question.radicals.map(r=>`<div class="radical-row"><strong>${esc(r.text)}</strong><span>${esc(r.meaning)}</span></div>`).join('')}</div></div><p>Você lembrou a resposta?</p><div class="card-actions">${button('Sim, lembrei', 'flash-answer', 'btn-primary', 'data-remembered="true"')}${button('Preciso revisar', 'flash-answer', 'btn-soft', 'data-remembered="false"')}</div>` : `${button('Mostrar resposta', 'reveal-flashcard', 'btn-primary')}`}</section>`;
    if (session.game === 'memoria') {
      const cards = question.cards || [];
      const seconds=Math.max(0,Math.floor((Date.now()-(state.memoryStartedAt||Date.now()))/1000));
      const elapsed=`${String(Math.floor(seconds/60)).padStart(2,'0')}:${String(seconds%60).padStart(2,'0')}`;
      return `<section class="card question">${header}<h2 class="question-title">Encontre os pares</h2><p class="muted">${question.mode === 'termo_definicao' ? 'Termo e definição' : 'Radical e significado'}. Vire dois cartões para conferir a combinação.</p><div class="memory-grid">${cards.map(c=>`<button class="memory-card ${state.memoryMatched.has(c.id)?'matched':''} ${state.memorySelected.includes(c.id)?'selected':''}" data-action="memory-card" data-card="${esc(c.id)}" ${state.memoryMatched.has(c.id)?'disabled':''}>${state.memoryMatched.has(c.id)||state.memorySelected.includes(c.id)?esc(c.text):'LISE'}</button>`).join('')}</div><p class="muted small">Pares: ${state.memoryPairs.length}/${cards.length/2} · Tentativas: ${state.memoryAttempts} · Tempo: ${elapsed}</p></section>`;
    }
    return '';
  }

  function renderResult() {
    const r = state.result;
    if (!r) { setLoading(); return; }
    return `<div class="question card" style="text-align:center"><div class="eyebrow">Prática concluída</div><h1 class="page-title">${r.score}%</h1><p>Você acertou ${r.correct} de ${r.total} questões e recebeu <strong>${r.xp} XP</strong>.</p><div class="card-actions" style="justify-content:center">${button('Jogar novamente', 'again-game', 'btn-primary')} ${button('Voltar aos Games', 'nav-games', 'btn-soft')} ${state.classId ? button('Voltar para a turma', 'open-class', 'btn-plain', `data-id="${state.classId}"`) : ''}</div></div>`;
  }

  function renderSmallForm(view) {
    if (view === 'new-class') return `<div class="section-heading"><div><button class="btn btn-plain btn-small" data-action="navigate" data-view="dashboard">← Painel</button><div class="eyebrow" style="margin-top:1rem">Professor</div><h1 class="page-title">Criar turma</h1><p>Depois de criar, compartilhe o código de entrada com seus alunos.</p></div></div><form class="card question" data-form="new-class"><div class="field"><label>Nome da turma</label><input name="name" maxlength="150" required placeholder="Ex.: 3º ano A"></div><button class="btn btn-primary">Criar turma</button></form>`;
    if (view === 'join-class') return `<div class="section-heading"><div><button class="btn btn-plain btn-small" data-action="navigate" data-view="dashboard">← Início</button><div class="eyebrow" style="margin-top:1rem">Entrar em uma turma</div><h1 class="page-title">Digite o código</h1><p>Peça ao professor o código de seis caracteres da turma.</p></div></div><form class="card question" data-form="join-class"><div class="field"><label>Código da turma</label><input name="code" maxlength="6" required autocapitalize="characters" placeholder="ABC234"></div><button class="btn btn-primary">Entrar na turma</button></form>`;
    return '';
  }

  function render() {
    let content = '';
    switch (state.view) {
      case 'auth': renderAuth(); return;
      case 'dashboard': content = renderDashboard(); break;
      case 'new-class': case 'join-class': content = renderSmallForm(state.view); break;
      case 'explore': content = renderExplore(); break;
      case 'detail': content = renderDetail(); break;
      case 'collections': content = renderCollections(); break;
      case 'collection': content = renderCollection(); break;
      case 'collection-create': content = renderNewCollection(); break;
      case 'trail-create': content = renderCreateTrail(); break;
      case 'teacher-term': content = renderTeacherTerm(); break;
      case 'student-term': content = renderStudentTerm(); break;
      case 'class': content = renderClass(); break;
      case 'student-detail': content = renderStudentDetail(); break;
      case 'trail': content = renderTrail(); break;
      case 'assessment-config': content = renderAssessmentConfig(); break;
      case 'assessment': content = renderAssessment(); break;
      case 'assessment-result': content = renderAssessmentResult(); break;
      case 'games': content = renderGames(); break;
      case 'sources': content = renderSources(); break;
      case 'choose-game': content = renderChooseGame(); break;
      case 'game-config': content = renderGameConfig(); break;
      case 'game': content = renderGameQuestion(); break;
      case 'result': content = renderResult(); break;
      default: content = '<div class="empty">Tela não encontrada.</div>';
    }
    app.innerHTML = shell(content);
  }

  async function loadDashboard() {
    state.view = 'dashboard'; state.dashboard = null; setLoading();
    state.dashboard = await api('/dashboard');
    if (state.user.role === 'Aluno') state.collections = (state.dashboard.collections || []);
    render();
  }
  async function loadCollections() {
    const d = await api('/collections'); state.collections = d.collections; state.view = 'collections'; render();
  }
  async function loadCollection(id) {
    const d = await api(`/collections/${id}`); state.collection = d.collection; state.view = 'collection'; render();
  }
  async function loadExplore(kind = state.exploreKind) {
    state.exploreKind = kind; state.view = 'explore'; state.explore = null; render();
    const params = new URLSearchParams({kind, search:state.exploreSearch, area:state.exploreArea});
    state.explore = await api(`/explore?${params}`); render();
  }
  async function loadClass(id, date = '') {
    state.classId = Number(id); state.classDate = date; state.view = 'class'; state.classDetail = null; render();
    const suffix = date ? `?date=${encodeURIComponent(date)}` : '';
    state.classDetail = await api(`/classes/${id}${suffix}`);
    state.classTab = state.classDetail.role === 'Professor' ? 'students' : 'feed';
    render();
  }
  async function loadStudentDetail(userId) {
    state.view='student-detail'; state.studentDetail=null; render();
    state.studentDetail=await api(`/classes/${state.classId}/students/${encodeURIComponent(userId)}`);
    render();
  }
  function configureAssessment(buttonEl) {
    const trail=(state.classDetail?.trails || []).find(item=>Number(item.assignment_id)===Number(buttonEl.dataset.assignment));
    state.assessmentTarget={class_id:Number(buttonEl.dataset.class), assignment_id:Number(buttonEl.dataset.assignment),
      trail_name:buttonEl.dataset.name || trail?.name || 'Trilha', assessment:trail?.assessment || null};
    state.view='assessment-config'; render();
  }
  async function startAssessment(classId, assignmentId) {
    state.classId=Number(classId); state.assessmentAnswer=null; state.assessmentResult=null;
    const d=await api(`/classes/${classId}/trails/${assignmentId}/assessment/sessions`,{method:'POST',body:{}});
    state.assessmentSession=d; state.assessmentIndex=0; state.view='assessment'; render();
  }
  async function loadSources() {
    state.sources = await api('/sources');
  }
  async function startPractice(game, source, config = {}) {
    state.practiceGame = game; state.practiceSource = source; state.classId = source.class_id || null; state.view = 'game'; state.gameSession = null; state.gameFeedback = null; render();
    const payload = {game, source_type:source.type, source_id:source.id, area:source.area, class_id:source.class_id, question_count:Number(config.question_count || 10), mode:config.mode || 'termo_definicao'};
    const d = await api('/games/sessions', {method:'POST', body:payload});
    state.gameSession = d; state.gameIndex = 0; state.gameFeedback = null; state.memoryPairs = []; state.memoryMatched = new Set(); state.memorySelected = []; state.memoryAttempts=0; state.memoryStartedAt=Date.now(); state.flashRevealed = false; render();
  }

  function chooseGameForSource(game) {
    state.practiceGame = game;
    state.view = 'game-config';
    render();
  }

  async function openTerm(id, from = state.view) {
    state.detailBack = from;
    state.detail = await api(`/explore/terms/${id}`);
    state.detailType = 'term'; state.view = 'detail'; render();
  }
  async function openRadical(id, from = state.view) {
    state.detailBack = from;
    state.detail = await api(`/explore/radicals/${id}`);
    state.detailType = 'radical'; state.view = 'detail'; render();
  }
  async function loadTrail(id, assignmentId) {
    const d = await api(`/trails/${id}?assignment_id=${assignmentId}`);
    state.collection = d.trail; state.classId = d.trail.class_id; state.view = 'trail'; render();
  }

  async function createCollectionScreen() {
    const [catalog, meta, collections] = await Promise.all([api('/catalog/terms'), api('/meta'), api('/collections')]);
    state.trailCatalog = catalog; state.trailAreas = meta.areas; state.collections = collections.collections; state.view = 'collection-create'; render();
  }
  async function createTrailScreen() {
    const [catalog, meta, dash] = await Promise.all([api('/catalog/terms'), api('/meta'), api('/dashboard')]);
    state.trailCatalog = catalog; state.trailAreas = meta.areas; state.dashboard = dash; state.view = 'trail-create'; render();
  }
  async function createTermScreen(student) {
    if (student) {
      const [catalog, meta, collections] = await Promise.all([api('/catalog/radicals'), api('/meta'), api('/collections')]);
      state.trailCatalog = catalog; state.trailAreas = meta.areas; state.collections = collections.collections; state.view = 'student-term';
    } else {
      state.dashboard = await api('/dashboard'); state.view = 'teacher-term';
    }
    render();
  }

  async function navigate(view) {
    if (view === 'dashboard') return loadDashboard();
    if (view === 'explore') return loadExplore('both');
    if (view === 'favorites') return loadExplore('favorites');
    if (view === 'collections') return loadCollections();
    if (view === 'games') { state.practiceGame=''; state.practiceSource=null; state.view='games'; return render(); }
  }

  async function submitGameAnswer(form) {
    const question = state.gameSession.questions[state.gameIndex];
    const data = new FormData(form);
    let body = {question_id:question.id};
    if (state.gameSession.game === 'familia_palavras') body.answer = data.getAll('answer');
    else body.answer = data.get('answer');
    const answer = await api(`/games/sessions/${state.gameSession.session_id}/answer`, {method:'POST', body});
    state.gameFeedback = answer; render();
  }

  async function nextQuestion() {
    if (state.gameIndex + 1 < state.gameSession.questions.length) {
      state.gameIndex++; state.gameFeedback=null; state.memoryPairs=[]; state.memoryMatched=new Set(); state.memorySelected=[]; state.memoryAttempts=0; state.memoryStartedAt=Date.now(); state.flashRevealed=false; render(); return;
    }
    const result = await api(`/games/sessions/${state.gameSession.session_id}/finish`, {method:'POST', body:{}});
    state.result = result; state.view='result'; render();
  }

  async function handleClick(event) {
    const buttonEl = event.target.closest('[data-action]');
    if (!buttonEl) return;
    if (buttonEl.tagName === 'A') event.preventDefault();
    const action = buttonEl.dataset.action;
    try {
      if (action === 'auth-mode') { state.authMode=buttonEl.dataset.mode; renderAuth(); }
      else if (action === 'navigate') await navigate(buttonEl.dataset.view);
      else if (action === 'go-dashboard') await loadDashboard();
      else if (action === 'toggle-sidebar') { state.sidebarCollapsed=!state.sidebarCollapsed; localStorage.setItem('lise_sidebar_collapsed',String(state.sidebarCollapsed)); render(); }
      else if (action === 'logout') { await api('/auth/logout',{method:'POST',body:{}}).catch(()=>{}); localStorage.removeItem('lise_access_token'); state.token=''; state.user=null; state.authMode='login'; renderAuth(); }
      else if (action === 'new-class') { state.view='new-class'; render(); }
      else if (action === 'join-class') { state.view='join-class'; render(); }
      else if (action === 'new-trail') await createTrailScreen();
      else if (action === 'new-teacher-term') await createTermScreen(false);
      else if (action === 'new-student-term') await createTermScreen(true);
      else if (action === 'new-collection') await createCollectionScreen();
      else if (action === 'open-class') await loadClass(buttonEl.dataset.id);
      else if (action === 'open-student') await loadStudentDetail(buttonEl.dataset.id);
      else if (action === 'open-term') await openTerm(buttonEl.dataset.id);
      else if (action === 'open-radical') await openRadical(buttonEl.dataset.id);
      else if (action === 'detail-back') { state.view=state.detailBack; render(); }
      else if (action === 'toggle-sort') { state.sort=state.sort==='asc'?'desc':'asc'; render(); }
      else if (action === 'toggle-favorite') {
        const type=buttonEl.dataset.type, id=buttonEl.dataset.id;
        if (buttonEl.dataset.favorite === 'true') await api(`/favorites/${type}/${id}`,{method:'DELETE'});
        else await api('/favorites',{method:'POST',body:{type,id:Number(id)}});
        if (state.view==='detail') state.detail=state.detailType==='term'?await api(`/explore/terms/${id}`):await api(`/explore/radicals/${id}`);
        else if (state.view==='explore') state.explore=await api(`/explore?${new URLSearchParams({kind:state.exploreKind,search:state.exploreSearch,area:state.exploreArea})}`);
        else if (state.view==='trail' && state.collection) state.collection=(await api(`/trails/${state.collection.id}?assignment_id=${state.collection.assignment_id}`)).trail;
        render(); toast('Favoritos atualizados.');
      }
      else if (action === 'toggle-game-favorite') {
        const type=buttonEl.dataset.type, id=Number(buttonEl.dataset.id);
        const itemList=type==='term'?state.gameFeedback.feedback.favorite_terms:state.gameFeedback.feedback.favorite_radicals;
        const item=itemList.find(x=>x.id===id);
        if (!item) return;
        if (item.favorite) await api(`/favorites/${type}/${id}`,{method:'DELETE'});
        else await api('/favorites',{method:'POST',body:{type,id}});
        item.favorite=!item.favorite; render();
      }
      else if (action === 'delete-trail') {
        if (!confirm('Apagar esta trilha? O vínculo dela com as turmas também será removido.')) return;
        await api(`/trails/${buttonEl.dataset.id}`,{method:'DELETE'}); await loadDashboard(); toast('Trilha apagada.');
      }
      else if (action === 'delete-collection') {
        if (!confirm('Apagar esta coleção? Os termos do catálogo não serão apagados.')) return;
        await api(`/collections/${buttonEl.dataset.id}`,{method:'DELETE'}); await loadCollections(); toast('Coleção apagada.');
      }
      else if (action === 'open-collection') await loadCollection(buttonEl.dataset.id);
      else if (action === 'remove-collection-term') {
        await api(`/collections/${buttonEl.dataset.collection}/terms/${buttonEl.dataset.term}`,{method:'DELETE'}); await loadCollection(buttonEl.dataset.collection); toast('Termo removido.');
      }
      else if (action === 'practice-collection') {
        state.practiceSource={type:'collection',id:Number(buttonEl.dataset.id),name:buttonEl.dataset.name}; state.practiceGame=''; state.view='choose-game'; render();
      }
      else if (action === 'practice-favorites') {
        state.practiceSource={type:'favorites',name:'Seus favoritos'}; state.practiceGame=''; state.view='choose-game'; render();
      }
      else if (action === 'class-tab') { state.classTab=buttonEl.dataset.tab; render(); }
      else if (action === 'configure-assessment') configureAssessment(buttonEl);
      else if (action === 'start-assessment') await startAssessment(buttonEl.dataset.class,buttonEl.dataset.assignment);
      else if (action === 'unassign-trail') {
        if (!confirm('Remover esta trilha somente desta turma?')) return;
        const classId=buttonEl.dataset.class;
        await api(`/classes/${classId}/trails/${buttonEl.dataset.id}`,{method:'DELETE'});
        await loadClass(classId); state.classTab='trails'; render(); toast('Trilha removida desta turma.');
      }
      else if (action === 'practice-trail') {
        state.practiceSource={type:'trail',id:Number(buttonEl.dataset.assignment),class_id:Number(buttonEl.dataset.class),name:buttonEl.dataset.name};
        state.practiceGame=''; state.view='choose-game'; render();
      }
      else if (action === 'open-trail') await loadTrail(buttonEl.dataset.id,buttonEl.dataset.assignment);
      else if (action === 'back-to-class') await loadClass(state.classId);
      else if (action === 'select-game') { state.practiceGame=buttonEl.dataset.game; await loadSources(); state.view='sources'; render(); }
      else if (action === 'choose-source') {
        state.practiceSource={type:buttonEl.dataset.type,id:buttonEl.dataset.id?Number(buttonEl.dataset.id):undefined,area:buttonEl.dataset.type==='area'?buttonEl.dataset.name:undefined,name:buttonEl.dataset.name,class_id:buttonEl.dataset.class?Number(buttonEl.dataset.class):undefined};
        if (state.practiceGame) state.view='game-config'; else state.view='choose-game'; render();
      }
      else if (action === 'configure-game') chooseGameForSource(buttonEl.dataset.game);
      else if (action === 'games-back') { state.view='games'; render(); }
      else if (action === 'practice-back') { state.view=state.practiceSource?.type==='trail'?'class':state.practiceSource?.type==='collection'?'collection':'games'; render(); }
      else if (action === 'choose-game-back') { state.view='choose-game'; render(); }
      else if (action === 'nav-games') { state.view='games'; state.gameSession=null; render(); }
      else if (action === 'reveal-flashcard') { state.flashRevealed=true; render(); }
      else if (action === 'flash-answer') {
        const q=state.gameSession.questions[state.gameIndex];
        state.gameFeedback=await api(`/games/sessions/${state.gameSession.session_id}/answer`,{method:'POST',body:{question_id:q.id,remembered:buttonEl.dataset.remembered==='true'}}); render();
      }
      else if (action === 'next-question') await nextQuestion();
      else if (action === 'assessment-next') {
        if (state.assessmentIndex + 1 < state.assessmentSession.total) {
          state.assessmentIndex++; state.assessmentAnswer=null; render();
        } else {
          state.assessmentResult=await api(`/assessment/sessions/${state.assessmentSession.session_id}/finish`,{method:'POST',body:{}});
          state.view='assessment-result'; render();
        }
      }
      else if (action === 'again-game') { state.view='game-config'; state.result=null; render(); }
      else if (action === 'memory-card') await memoryCard(buttonEl.dataset.card);
      else if (action === 'add-to-collection') { /* submitted by the form handler */ }
    } catch (error) { toast(error.message); }
  }

  async function memoryCard(cardId) {
    if (state.memoryMatched.has(cardId) || state.memorySelected.includes(cardId)) return;
    state.memorySelected.push(cardId); render();
    if (state.memorySelected.length < 2) return;
    const q=state.gameSession.questions[state.gameIndex], pair=[...state.memorySelected];
    const check=await api(`/games/sessions/${state.gameSession.session_id}/match`,{method:'POST',body:{question_id:q.id,pair}});
    state.memoryAttempts=check.attempts || state.memoryAttempts+1;
    if (check.match) {
      state.memoryPairs.push(pair); pair.forEach(id=>state.memoryMatched.add(id)); state.memorySelected=[]; render();
      if (state.memoryMatched.size === q.cards.length) {
        const answer=await api(`/games/sessions/${state.gameSession.session_id}/answer`,{method:'POST',body:{question_id:q.id,answer:state.memoryPairs}});
        state.gameFeedback=answer; render();
      }
    } else {
      setTimeout(()=>{state.memorySelected=[];render();},750);
    }
  }

  async function handleSubmit(event) {
    const form = event.target.closest('form[data-form]');
    if (!form) return;
    event.preventDefault();
    const kind=form.dataset.form, data=new FormData(form);
    try {
      if (kind === 'login') {
        const d=await api('/auth/login',{method:'POST',body:{email:data.get('email'),password:data.get('password'),remember:data.has('remember')}});
        state.token=d.access_token; state.user=d.user; localStorage.setItem('lise_access_token',state.token); await loadDashboard(); toast(`Olá, ${state.user.name.split(' ')[0]}!`);
      } else if (kind === 'register') {
        const d=await api('/auth/register',{method:'POST',body:{name:data.get('name'),email:data.get('email'),password:data.get('password'),role:data.get('role'),teacher_code:data.get('teacher_code')}}); toast(d.message); state.authMode='login'; renderAuth();
      } else if (kind === 'recovery') {
        const d=await api('/auth/recovery',{method:'POST',body:{email:data.get('email')}}); toast(d.message); state.authMode='login'; renderAuth();
      } else if (kind === 'new-class') {
        await api('/classes',{method:'POST',body:{name:data.get('name')}}); await loadDashboard(); toast('Turma criada.');
      } else if (kind === 'join-class') {
        await api('/classes/join',{method:'POST',body:{code:data.get('code')}}); await loadDashboard(); toast('Você entrou na turma.');
      } else if (kind === 'explore-filter') {
        state.exploreKind=data.get('kind'); state.exploreSearch=data.get('search'); state.exploreArea=data.get('area'); await loadExplore(state.exploreKind);
      } else if (kind === 'collection-create') {
        const body={name:data.get('name'),term_ids:data.getAll('term_ids').map(Number)};
        const d=await api('/collections',{method:'POST',body}); state.collections=[...(state.collections||[]),d.collection]; await loadCollections(); toast('Coleção criada.');
      } else if (kind === 'add-to-collection') {
        await api(`/collections/${data.get('collection_id')}/terms`,{method:'POST',body:{term_id:Number(data.get('term_id'))}}); toast('Termo adicionado à coleção.');
      } else if (kind === 'trail-create') {
        const body={name:data.get('name'),description:data.get('description'),area:data.get('area'),term_ids:data.getAll('term_ids').map(Number),class_ids:data.getAll('class_ids').map(Number),due_date:data.get('due_date') || null};
        await api('/trails',{method:'POST',body}); await loadDashboard(); toast('Trilha criada.');
      } else if (kind === 'assign-trail') {
        await api(`/classes/${state.classId}/trails`,{method:'POST',body:{trail_id:Number(data.get('trail_id')),due_date:data.get('due_date') || null}}); await loadClass(state.classId); state.classTab='trails'; render(); toast('Trilha atribuída à turma.');
      } else if (kind === 'assessment-config') {
        const target=state.assessmentTarget;
        await api(`/classes/${target.class_id}/trails/${target.assignment_id}/assessment`,{method:'POST',body:{title:data.get('title'),question_count:Number(data.get('question_count')),pass_score:Number(data.get('pass_score')),content:data.get('content'),mode:data.get('mode')}});
        await loadClass(target.class_id); state.classTab='trails'; render(); toast('Avaliação salva.');
      } else if (kind === 'teacher-term') {
        const radicals=String(data.get('radicals')).split('\n').map(line=>line.split('|').map(v=>v.trim())).filter(parts=>parts.some(Boolean)).map(parts=>({name:parts[0],meaning:parts[1],classification:parts[2]}));
        await api('/terms',{method:'POST',body:{name:data.get('name'),definition:data.get('definition'),area_id:Number(data.get('area_id')),class_ids:data.getAll('class_ids').map(Number),trail_ids:data.getAll('trail_ids').map(Number),radicals}}); await loadDashboard(); toast('Termo compartilhado com os destinos selecionados.');
      } else if (kind === 'student-term') {
        const collection=data.get('collection_id');
        await api('/me/terms',{method:'POST',body:{name:data.get('name'),definition:data.get('definition'),area_id:data.get('area_id')?Number(data.get('area_id')):null,radical_ids:data.getAll('radical_ids').map(Number),collection_id:collection?Number(collection):null}}); await loadDashboard(); toast('Palavra privada criada.');
      } else if (kind === 'game-config') {
        await startPractice(state.practiceGame,state.practiceSource,{question_count:data.get('question_count'),mode:data.get('mode')});
      } else if (kind === 'game-answer') await submitGameAnswer(form);
      else if (kind === 'assessment-answer') {
        const question=state.assessmentSession.questions[state.assessmentIndex];
        const choice=data.get('answer');
        if (!choice) return toast('Selecione uma alternativa.');
        state.assessmentAnswer=await api(`/assessment/sessions/${state.assessmentSession.session_id}/answer`,{method:'POST',body:{question_id:question.id,answer:choice}}); render();
      }
    } catch (error) { toast(error.message); }
  }

  function handleChange(event) {
    const target=event.target;
    if (target.matches('#auth-role')) {
      const field=document.querySelector('[data-teacher-code]');
      if (field) { field.hidden=target.value!=='PROFESSOR'; const input=field.querySelector('input'); if (input) input.required=target.value==='PROFESSOR'; }
    }
    if (target.matches('[data-role="class-date"]')) {
      const active=state.classTab; loadClass(state.classId,target.value).then(()=>{state.classTab=active;render();}).catch(e=>toast(e.message));
    }
    if (target.matches('[data-role="trail-area"]') || target.matches('[data-role="collection-area"]')) filterCatalog();
    if (target.name==='term_ids' || target.name==='class_ids') updateSelectedCount();
  }

  function handleInput(event) {
    if (event.target.matches('[data-role="trail-search"]') || event.target.matches('[data-role="trail-area"]')) filterCatalog();
    if (event.target.matches('[data-role="collection-search"]') || event.target.matches('[data-role="collection-area"]')) filterCatalog();
    if (event.target.matches('[data-role="radical-search"]')) {
      const q=event.target.value.toLocaleLowerCase();
      document.querySelectorAll('.radical-choice').forEach(row=>row.hidden=!row.dataset.search.includes(q));
    }
  }

  function filterCatalog() {
    const trailSearch=document.querySelector('[data-role="trail-search"]');
    const trailArea=document.querySelector('[data-role="trail-area"]');
    const collectionSearch=document.querySelector('[data-role="collection-search"]');
    const collectionArea=document.querySelector('[data-role="collection-area"]');
    const q=(trailSearch?.value || collectionSearch?.value || '').toLocaleLowerCase();
    const area=trailArea?.value || collectionArea?.value || '';
    document.querySelectorAll('.term-choice').forEach(row=>{row.hidden=!(row.dataset.name.includes(q) && (!area || row.dataset.area===area));});
    document.querySelectorAll('[data-list-group] .check-row').forEach(row=>{
      const name=(row.textContent||'').toLocaleLowerCase(), rowArea=row.textContent||'';
      row.hidden=!(name.includes(q) && (!area || rowArea.includes(area)));
    });
  }

  function updateSelectedCount() {
    const count=document.querySelectorAll('input[name="term_ids"]:checked').length;
    document.querySelectorAll('[data-role="selected-count"]').forEach(el=>el.textContent=String(count));
  }

  async function init() {
    if (!API_BASE) { renderAuth(); toast('Configure o endereço da API em config.js para conectar o LISE.'); return; }
    const params=new URLSearchParams(location.search);
    if (params.get('confirmed')==='1') toast('E-mail confirmado. Agora você pode entrar.');
    if (params.get('mode')==='recovery') {
      const tokenHash=params.get('token_hash');
      if (tokenHash) {
        app.innerHTML=`<div class="auth-page"><section class="auth-aside"><div class="brand"><span class="brand-mark">L</span> LISE</div><div><h1 class="auth-title">Crie uma nova senha.</h1><p class="auth-copy">Escolha uma senha segura para voltar aos seus estudos.</p></div></section><section class="auth-main"><form class="auth-card card" data-form="password-reset"><h2>Nova senha</h2><div class="field"><label>Nova senha</label><input name="password" type="password" minlength="8" required></div><div class="field"><label>Repita a nova senha</label><input name="confirm" type="password" minlength="8" required></div><button class="btn btn-primary btn-block">Atualizar senha</button></form></section></div>`;
        state.recovery={tokenHash};
        history.replaceState({},'',`${location.pathname}?mode=recovery`);
        return;
      }
      toast('Abra o link de recuperação mais recente enviado para seu e-mail.');
    }
    if (!state.token) { renderAuth(); return; }
    try { const d=await api('/auth/me'); state.user=d.user; await loadDashboard(); }
    catch (_error) { state.token=''; localStorage.removeItem('lise_access_token'); renderAuth(); }
  }

  app.addEventListener('click', event=>handleClick(event));
  app.addEventListener('submit', event=>handleSubmit(event));
  app.addEventListener('change', handleChange);
  app.addEventListener('input', handleInput);
  app.addEventListener('submit', async event=>{
    if (event.target.dataset.form==='password-reset') {
      event.preventDefault(); const data=new FormData(event.target);
      if (data.get('password')!==data.get('confirm')) return toast('As senhas não são iguais.');
      try { const result=await api('/auth/password',{method:'POST',body:{password:data.get('password'),token_hash:state.recovery.tokenHash}}); history.replaceState({},'',location.pathname); toast(result.message); state.authMode='login'; renderAuth(); }
      catch(error){toast(error.message);}
    }
  });
  init().catch(error=>{renderAuth();toast(error.message);});
})();
