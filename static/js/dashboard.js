// Apply Saved Theme immediately to avoid visual flash
const savedTheme = localStorage.getItem('app-theme') || 'purple';
if (savedTheme === 'orange') {
    document.body.classList.add('theme-orange');
}

// Global State
let chartMensal = null;
let chartAnual = null;
let chartModal = null;

let currentPage = 1;
const limit = 100;
let searchTimeout = null;
let activeProfileName = "Default";
let pollingInterval = null;

// DOM Elements - Views
const viewDashboard = document.getElementById('viewDashboard');
const viewSettings = document.getElementById('viewSettings');

// DOM Elements - Header & Actions
const btnSyncStart = document.getElementById('btnSyncStart');
const btnSyncPause = document.getElementById('btnSyncPause');
const btnSyncStop = document.getElementById('btnSyncStop');
const btnSyncRestart = document.getElementById('btnSyncRestart');
const lblLastSync = document.getElementById('lblLastSync');
const btnGoToSettings = document.getElementById('btnGoToSettings');
const btnBackToDash = document.getElementById('btnBackToDash');
const lblActiveProfileName = document.getElementById('lblActiveProfileName');

// DOM Elements - Sync Progress Card
const syncProgressCard = document.getElementById('syncProgressCard');
const progressLabel = document.getElementById('progressLabel');
const progressPercent = document.getElementById('progressPercent');
const progressBarFill = document.getElementById('progressBarFill');
const progressSubInfo = document.getElementById('progressSubInfo');

// DOM Elements - Auth Alert Overlay
const authAlertOverlay = document.getElementById('authAlertOverlay');
const lnkAuthGoogle = document.getElementById('lnkAuthGoogle');
const btnAuthCancel = document.getElementById('btnAuthCancel');

// DOM Elements - Filters
const filterSearch = document.getElementById('filterSearch');
const filterAno = document.getElementById('filterAno');
const filterDataInicio = document.getElementById('filterDataInicio');
const filterDataFim = document.getElementById('filterDataFim');
const filterOrdem = document.getElementById('filterOrdem');
const btnExport = document.getElementById('btnExport');
const btnExportHTML = document.getElementById('btnExportHTML');

const rankingTableBody = document.getElementById('rankingTableBody');
const paginationInfo = document.getElementById('paginationInfo');
const paginationPages = document.getElementById('paginationPages');

// DOM Elements - Settings
const formAddProfile = document.getElementById('formAddProfile');
const txtProfileName = document.getElementById('txtProfileName');
const txtProfileFolder = document.getElementById('txtProfileFolder');
const profilesListContainer = document.getElementById('profilesListContainer');

// Modal Elements
const detailsModal = document.getElementById('detailsModal');
const btnModalClose = document.getElementById('btnModalClose');
const modalTitle = document.getElementById('modalTitle');
const modalTotal = document.getElementById('modalTotal');
const modalScore = document.getElementById('modalScore');
const modalPrimeiro = document.getElementById('modalPrimeiro');
const modalUltimo = document.getElementById('modalUltimo');
const modalOccurrenceContainer = document.getElementById('modalOccurrenceContainer');

// Init
document.addEventListener('DOMContentLoaded', () => {
    lucide.createIcons();
    initCharts();
    console.log("Dashboard iniciado. Configurando UI de Importação...");

    // Garante que a área de Importação seja criada logo no início
    setupImportUI();

    // Configura e carrega perfis primeiro
    loadProfiles().then(() => {
        checkSyncStatus();
        loadDashboardData();
    });

    // Event Listeners - Navigation
    btnGoToSettings.addEventListener('click', showSettingsView);
    btnBackToDash.addEventListener('click', showDashboardView);

    // Event Listeners - Sync Controls
    btnSyncStart.addEventListener('click', handleStartClick);
    btnSyncPause.addEventListener('click', triggerPauseSync);
    btnSyncStop.addEventListener('click', triggerStopSync);
    btnSyncRestart.addEventListener('click', triggerRestartSync);

    // Event Listeners - Auth Overlay
    btnAuthCancel.addEventListener('click', () => authAlertOverlay.style.display = 'none');
    lnkAuthGoogle.addEventListener('click', () => {
        authAlertOverlay.style.display = 'none';
        // Polling para checar quando o login for feito
        startAuthStatusPolling();
    });

    // Event Listeners - Table operations
    filterSearch.addEventListener('input', handleSearchInput);
    filterAno.addEventListener('change', () => { currentPage = 1; loadRanking(); });
    if (filterDataInicio) filterDataInicio.addEventListener('change', () => { currentPage = 1; loadRanking(); });
    if (filterDataFim) filterDataFim.addEventListener('change', () => { currentPage = 1; loadRanking(); });
    filterOrdem.addEventListener('change', () => { currentPage = 1; loadRanking(); });
    btnExport.addEventListener('click', exportCSV);
    if (btnExportHTML) {
        btnExportHTML.addEventListener('click', () => {
            const activeTheme = localStorage.getItem('app-theme') || 'purple';
            window.location.href = `/api/export-html?tema=${activeTheme}`;
        });
    }
    btnModalClose.addEventListener('click', closeModal);
    formAddProfile.addEventListener('submit', handleAddProfile);

    // Event Listener - Copy Modal Title
    const btnCopyTitle = document.getElementById('btnCopyTitle');
    if (btnCopyTitle) {
        btnCopyTitle.addEventListener('click', () => {
            const titleText = document.getElementById('modalTitle').textContent;
            
            // Função robusta de cópia com fallback para HTTP sem HTTPS (acesso por IP de outro PC)
            const realizarCopia = () => {
                if (navigator.clipboard && window.isSecureContext) {
                    return navigator.clipboard.writeText(titleText);
                } else {
                    return new Promise((resolve, reject) => {
                        try {
                            const textArea = document.createElement("textarea");
                            textArea.value = titleText;
                            textArea.style.position = "fixed";
                            textArea.style.top = "0";
                            textArea.style.left = "0";
                            textArea.style.opacity = "0";
                            document.body.appendChild(textArea);
                            textArea.focus();
                            textArea.select();
                            const successful = document.execCommand("copy");
                            document.body.removeChild(textArea);
                            if (successful) resolve();
                            else reject(new Error("Falha no comando de cópia fallback"));
                        } catch (err) {
                            reject(err);
                        }
                    });
                }
            };

            realizarCopia().then(() => {
                btnCopyTitle.innerHTML = '<i data-lucide="check" style="width: 13px; height: 13px; color: #10b981;"></i> Copiado!';
                btnCopyTitle.style.borderColor = '#10b981';
                btnCopyTitle.style.color = '#fff';
                lucide.createIcons();
                
                setTimeout(() => {
                    btnCopyTitle.innerHTML = '<i data-lucide="copy" style="width: 13px; height: 13px;"></i> Copiar';
                    btnCopyTitle.style.borderColor = 'rgba(255, 255, 255, 0.1)';
                    btnCopyTitle.style.color = '#9ca3af';
                    lucide.createIcons();
                }, 1500);
            }).catch(err => {
                console.error("Erro ao copiar texto: ", err);
                alert("Não foi possível copiar automaticamente. Selecione e copie manualmente.");
            });
        });
    }

    // Theme Switcher Buttons
    const btnThemePurple = document.getElementById('btnThemePurple');
    const btnThemeOrange = document.getElementById('btnThemeOrange');

    const updateThemeButtons = (theme) => {
        if (!btnThemePurple || !btnThemeOrange) return;
        if (theme === 'orange') {
            btnThemeOrange.classList.add('active');
            btnThemePurple.classList.remove('active');
            btnThemeOrange.style.borderColor = '';
            btnThemeOrange.style.background = '';
            btnThemePurple.style.borderColor = '';
            btnThemePurple.style.background = '';
        } else {
            btnThemePurple.classList.add('active');
            btnThemeOrange.classList.remove('active');
            btnThemeOrange.style.borderColor = '';
            btnThemeOrange.style.background = '';
            btnThemePurple.style.borderColor = '';
            btnThemePurple.style.background = '';
        }
    };

    if (btnThemePurple && btnThemeOrange) {
        updateThemeButtons(savedTheme);

        btnThemePurple.addEventListener('click', () => {
            document.body.classList.remove('theme-orange');
            localStorage.setItem('app-theme', 'purple');
            updateThemeButtons('purple');
            loadChartsData();
        });

        btnThemeOrange.addEventListener('click', () => {
            document.body.classList.add('theme-orange');
            localStorage.setItem('app-theme', 'orange');
            updateThemeButtons('orange');
            loadChartsData();
        });
    }

    // Close modal on background click
    detailsModal.addEventListener('click', (e) => {
        if (e.target === detailsModal) closeModal();
    });
});

// View Navigation SPA
function showSettingsView() {
    viewDashboard.style.display = 'none';
    viewSettings.style.display = 'block';
    loadProfiles();
}

function showDashboardView() {
    viewSettings.style.display = 'none';
    viewDashboard.style.display = 'block';
    loadProfiles().then(() => {
        loadDashboardData();
    });
}
// Setup Import UI - Auto-upload on file selection
function setupImportUI() {
    console.log("setupImportUI: Inicializando...");
    var dropArea = document.getElementById('uploadDropArea');
    var fileInput = document.getElementById('inputUploadFile');
    var statusArea = document.getElementById('uploadStatusArea');
    var statusText = document.getElementById('uploadStatusText');

    if (!dropArea || !fileInput) {
        console.error('setupImportUI: Elementos do DOM não localizados!', { dropArea, fileInput });
        return;
    }

    // CLICK: abrir o seletor de arquivos
    dropArea.onclick = function(e) {
        console.log("setupImportUI: DropArea clicada. Abrindo seletor...");
        fileInput.value = ''; // reset para garantir evento change
        fileInput.click();
    };

    // SELEÇÃO DE ARQUIVO: upload automático
    fileInput.onchange = function(e) {
        console.log("setupImportUI: fileInput.onchange disparado!");
        if (fileInput.files && fileInput.files.length > 0) {
            var file = fileInput.files[0];
            console.log("setupImportUI: Arquivo selecionado:", file.name, file.size, file.type);
            processUpload(file);
        } else {
            console.warn("setupImportUI: Nenhum arquivo no fileInput.files");
        }
    };

    // DRAG OVER: visual feedback
    dropArea.ondragover = function(e) {
        e.preventDefault();
        e.stopPropagation();
        dropArea.classList.add('dragover');
    };

    // DRAG LEAVE: reset visual
    dropArea.ondragleave = function(e) {
        e.preventDefault();
        e.stopPropagation();
        dropArea.classList.remove('dragover');
    };

    // DROP: capturar arquivo + upload
    dropArea.ondrop = function(e) {
        e.preventDefault();
        e.stopPropagation();
        dropArea.classList.remove('dragover');

        console.log("setupImportUI: Arquivo arrastado/solto!");
        if (e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files.length > 0) {
            var file = e.dataTransfer.files[0];
            console.log("setupImportUI: Arquivo dropado:", file.name, file.size, file.type);
            processUpload(file);
        } else {
            console.warn("setupImportUI: Nenhum arquivo no dataTransfer");
        }
    };

    // Impedir comportamento padrão do navegador para arrastar/soltar fora do dropArea
    document.body.ondragover = function(e) { e.preventDefault(); };
    document.body.ondrop = function(e) { e.preventDefault(); };

    // Função de upload robusta
    async function processUpload(file) {
        console.log("processUpload: Iniciando envio do arquivo:", file.name);
        
        // Exibir status imediatamente
        statusArea.style.display = 'block';
        statusText.textContent = '⏳ Enviando "' + file.name + '"... Aguarde.';
        statusText.style.color = '#fbbf24';
        dropArea.style.opacity = '0.5';
        dropArea.style.pointerEvents = 'none';

        var formData = new FormData();
        formData.append('file', file);

        try {
            console.log("processUpload: Fazendo requisição POST para /api/upload-data...");
            var res = await fetch('/api/upload-data', {
                method: 'POST',
                body: formData
            });
            
            console.log("processUpload: Resposta recebida da API. Status:", res.status);
            var data = await res.json();
            console.log("processUpload: Dados decodificados:", data);

            if (data.status === 'success') {
                statusText.textContent = '✅ ' + data.message;
                statusText.style.color = '#34d399';
                
                // Alertar sucesso de forma limpa
                console.log("processUpload: Sucesso! Recarregando dashboard em 1.5s...");
                setTimeout(function() {
                    statusArea.style.display = 'none';
                    dropArea.style.opacity = '1';
                    dropArea.style.pointerEvents = 'auto';
                    showDashboardView();
                }, 1500);
            } else {
                var errMsg = data.detail || data.message || 'Falha desconhecida';
                console.error("processUpload: Servidor retornou erro:", errMsg);
                statusText.textContent = '❌ Erro: ' + errMsg;
                statusText.style.color = '#f87171';
                dropArea.style.opacity = '1';
                dropArea.style.pointerEvents = 'auto';
                alert('Erro na Importação: ' + errMsg);
            }
        } catch (err) {
            console.error("processUpload: Falha na requisição:", err);
            statusText.textContent = '❌ Erro de conexão: ' + err.message;
            statusText.style.color = '#f87171';
            dropArea.style.opacity = '1';
            dropArea.style.pointerEvents = 'auto';
            alert('Erro de Conexão com o servidor: ' + err.message);
        }
    }
}

// Handle File Upload (legacy, kept for compatibility but now unused)
async function handleFileUpload(file) {
    var formData = new FormData();
    formData.append('file', file);
    try {
        var res = await fetch('/api/upload-data', { method: 'POST', body: formData });
        var data = await res.json();
        if (data.status === 'success') {
            alert(data.message);
            showDashboardView();
        } else {
            alert("Erro: " + (data.detail || data.message));
        }
    } catch (e) {
        alert("Erro na conexão com o servidor: " + e.message);
    }
};

// Load Profiles
async function loadProfiles() {
    try {
        const res = await fetch('/api/profiles');
        const data = await res.json();

        activeProfileName = data.active_profile;
        lblActiveProfileName.textContent = activeProfileName;

        renderProfilesList(data.profiles, data.active_profile);
    } catch (e) {
        console.error("Erro ao carregar perfis:", e);
    }
}

function renderProfilesList(profiles, activeName) {
    profilesListContainer.innerHTML = '';

    if (!profiles || profiles.length === 0) {
        profilesListContainer.innerHTML = '<p class="no-data">Nenhum perfil cadastrado.</p>';
        return;
    }

    profiles.forEach(p => {
        const isActive = p.name === activeName;
        const div = document.createElement('div');
        div.className = `profile-item ${isActive ? 'active' : ''}`;

        div.innerHTML = `
            <div class="profile-info">
                <h4>
                    <i data-lucide="mail"></i> ${p.name}
                    ${isActive ? '<span class="profile-status-badge">Ativo</span>' : ''}
                </h4>
                <span>Pasta de credenciais: <code>${p.folder || 'Raiz do projeto'}</code></span>
            </div>
            <div class="profile-actions">
                ${!isActive ? `<button class="btn-activate" onclick="activateProfile('${p.name}')">Ativar</button>` : ''}
            </div>
        `;

        profilesListContainer.appendChild(div);
    });
    lucide.createIcons();
}

// Activate Profile
async function activateProfile(name) {
    try {
        const res = await fetch('/api/profiles/active', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name: name })
        });
        const data = await res.json();

        if (data.status === 'success') {
            stopPolling();
            setSyncingState("idle");
            await loadProfiles();
            checkSyncStatus();
            loadDashboardData();
        } else {
            alert("Erro ao ativar perfil: " + data.detail);
        }
    } catch (e) {
        alert("Erro ao conectar ao perfil: " + e.message);
    }
}

// Add Profile Form Handler
async function handleAddProfile(e) {
    e.preventDefault();
    const name = txtProfileName.value.trim();
    const folder = txtProfileFolder.value.trim();

    try {
        const res = await fetch('/api/profiles', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name, folder })
        });
        const data = await res.json();

        if (res.status === 200) {
            alert(`Perfil '${name}' criado! Lembre-se de criar a pasta '${folder}' e colocar o credentials.json nela.`);
            txtProfileName.value = '';
            txtProfileFolder.value = '';
            loadProfiles();
        } else {
            alert("Erro ao salvar perfil: " + data.detail);
        }
    } catch (e) {
        alert("Erro ao salvar perfil: " + e.message);
    }
}

// Handle File Upload
async function handleFileUpload(file) {
    const btnConfirm = document.getElementById('btnConfirmUpload');
    const originalText = btnConfirm.innerHTML;

    btnConfirm.disabled = true;
    btnConfirm.innerHTML = '<i class="spinner"></i> Processando...';

    const formData = new FormData();
    formData.append('file', file);

    try {
        const res = await fetch('/api/upload-data', {
            method: 'POST',
            body: formData
        });
        const data = await res.json();

        if (data.status === 'success') {
            alert(data.message);
            showDashboardView();
        } else {
            alert("Erro: " + data.message);
        }
    } catch (e) {
        alert("Erro na conexão com o servidor: " + e.message);
    } finally {
        btnConfirm.disabled = false;
        btnConfirm.innerHTML = originalText;
    }
}

// Check status on load to see if syncing is running in backend
async function checkSyncStatus() {
    try {
        const res = await fetch('/api/status');
        const data = await res.json();

        setSyncingState(data.status, data);

        if (data.status === "running") {
            startPolling();
        } else if (data.ultima_extracao) {
            lblLastSync.textContent = data.ultima_extracao;
        } else {
            lblLastSync.textContent = "Nunca sincronizado";
        }

        // Atualizar indicador de autorização
        await checkAuthStatus();
    } catch (e) {
        console.error("Erro ao verificar status da sincronização:", e);
    }
}

// Check and update auth status badge
async function checkAuthStatus() {
    try {
        const res = await fetch('/api/auth-status');
        const data = await res.json();
        const lblAuthStatus = document.getElementById('lblAuthStatus');

        if (data.authenticated) {
            lblAuthStatus.className = 'badge badge-success';
            lblAuthStatus.textContent = 'Autorização concedida';
        } else {
            lblAuthStatus.className = 'badge badge-danger';
            lblAuthStatus.textContent = data.status === 'no_credentials' ? 'Sem credentials.json' : 'Autorização pendente';
        }
    } catch (e) {
        console.error("Erro ao checar status de autenticação:", e);
    }
}

// Handle Click on Start Button (Checks Auth first)
async function handleStartClick() {
    try {
        const res = await fetch('/api/auth-url');
        const data = await res.json();

        if (data.error) {
            alert(data.error);
            return;
        }

        if (!data.authenticated && data.auth_url) {
            // Exibir popup de autenticação do Google
            lnkAuthGoogle.href = data.auth_url;
            authAlertOverlay.style.display = 'flex';
        } else {
            // Autenticado, inicia a sincronização
            triggerStartSync();
        }
    } catch (e) {
        alert("Erro ao checar credenciais: " + e.message);
    }
}

// Start polling authentication status
function startAuthStatusPolling() {
    const authInterval = setInterval(async () => {
        try {
            const res = await fetch('/api/auth-status');
            const data = await res.json();
            if (data.authenticated) {
                clearInterval(authInterval);
                alert("Login com Google efetuado com sucesso! Iniciando sincronização...");
                // Atualiza o cabeçalho imediatamente
                checkAuthStatus();
                triggerStartSync();
            }
        } catch (e) {
            clearInterval(authInterval);
        }
    }, 2000);
}

// Trigger Sync APIs
async function triggerStartSync() {
    try {
        const res = await fetch('/api/sync/start', { method: 'POST' });
        const data = await res.json();
        if (data.status === 'started' || data.status === 'already_running') {
            startPolling();
        }
    } catch (e) {
        alert("Erro ao iniciar sincronização: " + e.message);
    }
}

async function triggerPauseSync() {
    try {
        const res = await fetch('/api/sync/pause', { method: 'POST' });
        const data = await res.json();
        if (data.status === 'paused') {
            checkSyncStatus();
        }
    } catch (e) {
        alert("Erro ao pausar sincronização: " + e.message);
    }
}

async function triggerStopSync() {
    if (!confirm("Tem certeza que deseja interromper a extração atual? Todos os dados em processamento serão apagados.")) return;
    try {
        const res = await fetch('/api/sync/stop', { method: 'POST' });
        const data = await res.json();
        if (data.status === 'stopped') {
            stopPolling();
            await checkSyncStatus();
            loadDashboardData();
        }
    } catch (e) {
        alert("Erro ao parar sincronização: " + e.message);
    }
}

async function triggerRestartSync() {
    if (!confirm("Reiniciar extração do zero? Todos os dados atuais serão apagados e a leitura recomeçará.")) return;
    try {
        stopPolling();
        resetDashboardUI();
        const res = await fetch('/api/sync/restart', { method: 'POST' });
        const data = await res.json();
        if (data.status === 'restarted') {
            startPolling();
            // Carrega dados imediatamente (que virão zerados do banco limpo)
            loadDashboardData();
        }
    } catch (e) {
        alert("Erro ao reiniciar sincronização: " + e.message);
    }
}

// Zera visualmente todos os dados do dashboard
function resetDashboardUI() {
    document.getElementById('statAnalyzed').textContent = '0';
    document.getElementById('statForwards').textContent = '0';
    document.getElementById('statMostForwarded').textContent = '-';
    document.getElementById('statMostRelevant').textContent = '-';

    rankingTableBody.innerHTML = '<tr><td colspan="7" class="no-data">Aguardando novos dados...</td></tr>';

    if (chartMensal) { chartMensal.data.labels = []; chartMensal.data.datasets = []; chartMensal.update(); }
    if (chartAnual) { chartAnual.data.labels = []; chartAnual.data.datasets = []; chartAnual.update(); }

    progressBarFill.style.width = '0%';
    progressPercent.textContent = '0%';
    progressLabel.textContent = 'Reiniciando...';
}

// Control UI State
function setSyncingState(status, data = null) {
    // Buttons state
    const syncIcon = btnSyncStart.querySelector('i') || btnSyncStart.querySelector('svg');
    if (status === "running") {
        btnSyncStart.disabled = true;
        btnSyncPause.disabled = false;
        btnSyncStop.disabled = false;

        if (syncIcon) syncIcon.className.baseVal = 'spinner'; // Para SVG, usa baseVal ou classList
        syncProgressCard.style.display = 'block';
    } else if (status === "paused") {
        btnSyncStart.disabled = false;
        btnSyncPause.disabled = true;
        btnSyncStop.disabled = false;

        if (syncIcon) {
            syncIcon.removeAttribute('class');
            syncIcon.setAttribute('data-lucide', 'play');
        }
        syncProgressCard.style.display = 'block';
    } else {
        // idle, stopped, completed, error
        btnSyncStart.disabled = false;
        btnSyncPause.disabled = true;
        btnSyncStop.disabled = true;

        if (syncIcon) {
            syncIcon.removeAttribute('class');
            syncIcon.setAttribute('data-lucide', 'play');
        }
        syncProgressCard.style.display = 'none';
    }

    if (data) {
        updateProgressUI(status, data);
    }
    lucide.createIcons();
}

function updateProgressUI(status, data) {
    const progresso = data.progresso || 0;
    progressBarFill.style.width = `${progresso}%`;
    progressPercent.textContent = `${progresso}%`;

    if (status === "paused") {
        progressLabel.textContent = `Pausado: ${data.mensagens_processadas} de ${data.total_mensagens || '?'} e-mails`;
        progressSubInfo.textContent = "Clique em 'Iniciar' para retomar de onde parou.";
    } else {
        progressLabel.textContent = `Processando: ${data.mensagens_processadas} de ${data.total_mensagens || '?'} e-mails`;
        progressSubInfo.innerHTML = `Sinalizações de reenvios localizadas até o momento: <strong>${data.reenvios_detectados}</strong>`;
    }
}

// Polling Managers
function startPolling() {
    stopPolling();
    pollingInterval = setInterval(async () => {
        try {
            const res = await fetch('/api/status');
            const data = await res.json();

            setSyncingState(data.status, data);

            // Se estiver rodando, atualiza os números e o ranking periodicamente
            if (data.status === "running") {
                loadDashboardData();
            }

            if (data.status !== "running") {
                stopPolling();
                if (data.erro) {
                    alert("Erro durante a extração: " + data.erro);
                } else if (data.status === "completed" || data.status === "idle") {
                    lblLastSync.textContent = data.ultima_extracao || 'Concluído';
                    loadDashboardData();
                }
            }
        } catch (e) {
            console.error("Erro no polling de status:", e);
            stopPolling();
        }
    }, 1500);
}

function stopPolling() {
    if (pollingInterval) {
        clearInterval(pollingInterval);
        pollingInterval = null;
    }
}

// Fetch all dashboard components
function loadDashboardData() {
    const search = filterSearch.value;
    const ano = filterAno.value;
    const dataInicio = filterDataInicio ? filterDataInicio.value : "";
    const dataFim = filterDataFim ? filterDataFim.value : "";

    loadStats(search, ano, dataInicio, dataFim);
    loadChartsData(ano, dataInicio, dataFim);
    loadRanking();
}

async function loadStats(search = "", ano = "", dataInicio = "", dataFim = "") {
    try {
        const queryParams = new URLSearchParams({
            busca: search,
            ano: ano,
            data_inicio: dataInicio,
            data_fim: dataFim
        });
        const res = await fetch(`/api/stats?${queryParams.toString()}`);
        const data = await res.json();

        document.getElementById('statAnalyzed').textContent = data.total_analisados.toLocaleString();
        document.getElementById('statForwards').textContent = data.total_reenvios.toLocaleString();
        document.getElementById('statMostForwarded').textContent = data.mais_reenviado;
        document.getElementById('statMostRelevant').textContent = data.mais_relevante;
    } catch (e) {
        console.error("Erro ao carregar métricas:", e);
    }
}

// Debounced keyword search
function handleSearchInput() {
    clearTimeout(searchTimeout);
    searchTimeout = setTimeout(() => {
        currentPage = 1;
        loadRanking();
    }, 350);
}

// Fetch and render ranking list
async function loadRanking() {
    const search = filterSearch.value;
    const ano = filterAno.value;
    const dataInicio = filterDataInicio ? filterDataInicio.value : "";
    const dataFim = filterDataFim ? filterDataFim.value : "";
    const ordem = filterOrdem.value;

    rankingTableBody.innerHTML = `
        <tr>
            <td colspan="7">
                <div class="loading-overlay">
                    <i data-lucide="loader" class="spinner" style="width: 32px; height: 32px; color: var(--primary-color);"></i>
                    <span style="margin-top: 10px;">Carregando ranking...</span>
                </div>
            </td>
        </tr>
    `;
    lucide.createIcons();

    try {
        const queryParams = new URLSearchParams({
            page: currentPage,
            limit: limit,
            busca: search,
            ano: ano,
            data_inicio: dataInicio,
            data_fim: dataFim,
            ordenacao: ordem
        });

        const res = await fetch(`/api/ranking?${queryParams.toString()}`);
        const data = await res.json();

        renderTable(data);
        renderPagination(data);
    } catch (e) {
        rankingTableBody.innerHTML = `
            <tr>
                <td colspan="7" class="no-data">Erro ao carregar dados do ranking.</td>
            </tr>
        `;
    }
}

function renderTable(data) {
    if (!data.dados || data.dados.length === 0) {
        rankingTableBody.innerHTML = `
            <tr>
                <td colspan="7" class="no-data">Nenhum reenvio localizado com os filtros selecionados.</td>
            </tr>
        `;
        return;
    }

    rankingTableBody.innerHTML = '';

    data.dados.forEach((item, index) => {
        const globalIndex = (data.pagina_atual - 1) * data.limite + index + 1;
        const tr = document.createElement('tr');
        tr.innerHTML = `
            <td style="font-weight: 700; color: var(--text-muted);">${globalIndex}</td>
            <td style="font-weight: 600; color: #fff;">${item.titulo}</td>
            <td style="text-align: center;"><span class="count-badge">${item.total_reenvios}</span></td>
            <td>${formatDate(item.ultimo_reenvio)}</td>
            <td style="text-align: center;">${item.ano_maioria}</td>
            <td style="text-align: center;">${formatMonth(item.mes_maioria)}</td>
            <td style="text-align: center;"><span class="score-badge">${item.score}</span></td>
        `;

        tr.addEventListener('click', () => openDetails(item.id_email_reenviado));
        rankingTableBody.appendChild(tr);
    });
}

function renderPagination(data) {
    const total = data.total_registros;
    const pages = data.total_paginas;
    const current = data.pagina_atual;

    const startIdx = total === 0 ? 0 : (current - 1) * limit + 1;
    const endIdx = Math.min(current * limit, total);
    paginationInfo.textContent = `Mostrando ${startIdx} a ${endIdx} de ${total} registros`;

    paginationPages.innerHTML = '';
    if (pages <= 1) return;

    // Botão Anterior
    const prevBtn = document.createElement('button');
    prevBtn.className = 'page-btn';
    prevBtn.innerHTML = '&laquo;';
    prevBtn.disabled = current === 1;
    prevBtn.addEventListener('click', () => changePage(current - 1));
    paginationPages.appendChild(prevBtn);

    const range = 2;
    let showPages = [];

    for (let i = 1; i <= pages; i++) {
        if (i === 1 || i === pages || (i >= current - range && i <= current + range)) {
            showPages.push(i);
        }
    }

    let last = 0;
    showPages.forEach(p => {
        if (last) {
            if (p - last === 2) {
                const pageBtn = document.createElement('button');
                pageBtn.className = 'page-btn';
                pageBtn.textContent = last + 1;
                pageBtn.addEventListener('click', () => changePage(last + 1));
                paginationPages.appendChild(pageBtn);
            } else if (p - last > 2) {
                const ellipsis = document.createElement('span');
                ellipsis.className = 'page-ellipsis';
                ellipsis.textContent = '...';
                paginationPages.appendChild(ellipsis);
            }
        }

        const pageBtn = document.createElement('button');
        pageBtn.className = `page-btn ${p === current ? 'active' : ''}`;
        pageBtn.textContent = p;
        pageBtn.addEventListener('click', () => changePage(p));
        paginationPages.appendChild(pageBtn);
        last = p;
    });

    // Botão Próximo
    const nextBtn = document.createElement('button');
    nextBtn.className = 'page-btn';
    nextBtn.innerHTML = '&raquo;';
    nextBtn.disabled = current === pages;
    nextBtn.addEventListener('click', () => changePage(current + 1));
    paginationPages.appendChild(nextBtn);
}

function changePage(p) {
    currentPage = p;
    loadRanking();
}

// Chart Initializations
function initCharts() {
    const ctxMensal = document.getElementById('chartMensal').getContext('2d');
    chartMensal = new Chart(ctxMensal, {
        type: 'line',
        data: { labels: [], datasets: [] },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: { legend: { display: false } },
            scales: {
                x: { grid: { color: 'rgba(255, 255, 255, 0.05)' }, ticks: { color: '#9ca3af' } },
                y: { grid: { color: 'rgba(255, 255, 255, 0.05)' }, ticks: { color: '#9ca3af' } }
            }
        }
    });

    const ctxAnual = document.getElementById('chartAnual').getContext('2d');
    chartAnual = new Chart(ctxAnual, {
        type: 'bar',
        data: { labels: [], datasets: [] },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: { legend: { display: false } },
            scales: {
                x: { grid: { display: false }, ticks: { color: '#9ca3af' } },
                y: { grid: { color: 'rgba(255, 255, 255, 0.05)' }, ticks: { color: '#9ca3af' } }
            }
        }
    });
}

// Update charts
async function loadChartsData(ano = "", dataInicio = "", dataFim = "") {
    try {
        const queryParams = new URLSearchParams({
            ano: ano,
            data_inicio: dataInicio,
            data_fim: dataFim
        });
        const res = await fetch(`/api/chart-data?${queryParams.toString()}`);
        const data = await res.json();

        // Mensal
        const labelsMensal = data.mensal.map(item => formatMonth(item.mes_ano));
        const valuesMensal = data.mensal.map(item => item.qtd);

        // Ajusta dinamicamente a largura do contêiner do gráfico de acordo com o volume de dados
        const containerMensal = document.getElementById('chartMensalContainer');
        if (containerMensal) {
            const calculatedWidth = Math.max(1200, data.mensal.length * 45);
            containerMensal.style.minWidth = `${calculatedWidth}px`;
        }

        const activeTheme = localStorage.getItem('app-theme') || 'purple';
        const isOrange = activeTheme === 'orange';

        chartMensal.data = {
            labels: labelsMensal,
            datasets: [{
                label: 'Reenvios',
                data: valuesMensal,
                borderColor: isOrange ? '#ff9f1c' : '#6366f1',
                backgroundColor: isOrange ? 'rgba(255, 159, 28, 0.15)' : 'rgba(99, 102, 241, 0.15)',
                borderWidth: 3,
                fill: true,
                tension: 0.35,
                pointBackgroundColor: isOrange ? '#ff9f1c' : '#d946ef',
                pointBorderColor: '#fff',
                pointHoverRadius: 6
            }]
        };
        chartMensal.update();

        // Rola automaticamente para o mês mais recente (final do gráfico à direita)
        setTimeout(() => {
            const scrollWrapper = document.querySelector('.chart-scroll-wrapper');
            if (scrollWrapper) {
                scrollWrapper.scrollLeft = scrollWrapper.scrollWidth;
            }
        }, 150);

        // Anual
        const labelsAnual = data.anual.map(item => item.ano);
        const valuesAnual = data.anual.map(item => item.qtd);

        chartAnual.data = {
            labels: labelsAnual,
            datasets: [{
                label: 'Reenvios',
                data: valuesAnual,
                borderRadius: 6,
                backgroundColor: isOrange ? [
                    'rgba(255, 159, 28, 0.75)',
                    'rgba(247, 127, 0, 0.75)',
                    'rgba(252, 191, 73, 0.75)',
                    'rgba(214, 40, 40, 0.75)'
                ] : [
                    'rgba(99, 102, 241, 0.7)',
                    'rgba(217, 70, 239, 0.7)',
                    'rgba(16, 185, 129, 0.7)',
                    'rgba(245, 158, 11, 0.7)'
                ]
            }]
        };
        chartAnual.update();

    } catch (e) {
        console.error("Erro ao carregar dados de gráficos:", e);
    }
}

// Modal management
async function openDetails(id) {
    try {
        const ano = filterAno.value;
        const dataInicio = filterDataInicio ? filterDataInicio.value : "";
        const dataFim = filterDataFim ? filterDataFim.value : "";
        const queryParams = new URLSearchParams({
            ano: ano,
            data_inicio: dataInicio,
            data_fim: dataFim
        });
        const res = await fetch(`/api/detalhes/${encodeURIComponent(id)}?${queryParams.toString()}`);
        const data = await res.json();

        const grupo = data.grupo;
        modalTitle.textContent = grupo.titulo;
        modalTotal.textContent = grupo.total_reenvios;
        modalScore.textContent = grupo.score;
        modalPrimeiro.textContent = formatDate(grupo.primeiro_reenvio);
        modalUltimo.textContent = formatDate(grupo.ultimo_reenvio);

        modalOccurrenceContainer.innerHTML = '';
        data.ocorrencias.forEach(oc => {
            const div = document.createElement('div');
            div.className = 'occurrence-item';
            div.innerHTML = `
                <span class="occurrence-subject">${oc.assunto_original || 'Sem assunto'}</span>
                <span class="occurrence-date">${formatDate(oc.data_envio)}</span>
            `;
            modalOccurrenceContainer.appendChild(div);
        });

        const labels = data.distribuicao_mensal.map(item => formatMonth(item.mes_ano));
        const values = data.distribuicao_mensal.map(item => item.qtd);

        const activeTheme = localStorage.getItem('app-theme') || 'purple';
        const isOrange = activeTheme === 'orange';

        if (chartModal) chartModal.destroy();

        const ctxModal = document.getElementById('chartModalMensal').getContext('2d');
        chartModal = new Chart(ctxModal, {
            type: 'bar',
            data: {
                labels: labels,
                datasets: [{
                    label: 'Ocorrências',
                    data: values,
                    backgroundColor: isOrange ? 'rgba(255, 159, 28, 0.65)' : 'rgba(217, 70, 239, 0.65)',
                    borderColor: isOrange ? '#ff9f1c' : '#d946ef',
                    borderWidth: 1,
                    borderRadius: 4
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: { legend: { display: false } },
                scales: {
                    x: { grid: { display: false }, ticks: { color: '#9ca3af', font: { size: 9 } } },
                    y: { grid: { color: 'rgba(255, 255, 255, 0.05)' }, ticks: { color: '#9ca3af', stepSize: 1 } }
                }
            }
        });

        detailsModal.classList.add('active');
    } catch (e) {
        alert("Erro ao carregar detalhes: " + e.message);
    }
}

function closeModal() {
    detailsModal.classList.remove('active');
}

// Download CSV
function exportCSV() {
    const search = filterSearch.value;
    const ano = filterAno.value;
    const dataInicio = filterDataInicio ? filterDataInicio.value : "";
    const dataFim = filterDataFim ? filterDataFim.value : "";
    const ordem = filterOrdem.value;

    const queryParams = new URLSearchParams({
        busca: search,
        ano: ano,
        data_inicio: dataInicio,
        data_fim: dataFim,
        ordenacao: ordem
    });

    window.location.href = `/api/export-csv?${queryParams.toString()}`;
}

// Helper formatters
function formatDate(dateStr) {
    if (!dateStr) return '-';
    try {
        const dt = new Date(dateStr.replace(' ', 'T'));
        if (isNaN(dt.getTime())) return dateStr;
        return dt.toLocaleDateString('pt-BR') + ' ' + dt.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' });
    } catch (e) {
        return dateStr;
    }
}

function formatMonth(monthStr) {
    if (!monthStr) return '-';
    const parts = monthStr.split('-');
    if (parts.length === 2) {
        return `${parts[1]}/${parts[0]}`;
    }
    return monthStr;
}

window.activateProfile = activateProfile;
