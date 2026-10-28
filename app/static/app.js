const form = document.querySelector('#posterForm');
const imageInput = document.querySelector('#images');
const assetGrid = document.querySelector('#assetGrid');
const assetCount = document.querySelector('#assetCount');
const dropzone = document.querySelector('#dropzone');
const dropzoneTitle = document.querySelector('#dropzoneTitle');
const overlayMode = document.querySelector('#overlayMode');
const logoField = document.querySelector('#logoField');
const merchantLogo = document.querySelector('#merchantLogo');
const merchantName = document.querySelector('#merchantName');
const merchantNameHint = document.querySelector('#merchantNameHint');
const workbenchMode = document.querySelector('#workbenchMode');
const modeTabs = [...document.querySelectorAll('.mode-tab[data-mode]')];
const standardFields = document.querySelector('#standardFields');
const freeFields = document.querySelector('#freeFields');
const creationMethodField = document.querySelector('#creationMethodField');
const introCopy = document.querySelector('#introCopy');
const assetHelp = document.querySelector('#assetHelp');
const freeMerchantName = form.elements.free_merchant_name;
const freeHeadline = form.elements.free_headline;
const freeSubtitle = form.elements.free_subtitle;
const additionalNotes = document.querySelector('#additionalNotes');
const apiState = document.querySelector('#apiState');
const button = document.querySelector('#generateButton');
const emptyPreview = document.querySelector('#emptyPreview');
const workingState = document.querySelector('#workingState');
const workingTitle = document.querySelector('#workingTitle');
const workingDetail = document.querySelector('#workingDetail');
const generationStages = [...document.querySelectorAll('.generation-stages li')];
const resultImage = document.querySelector('#resultImage');
const resultActions = document.querySelector('#resultActions');
const downloadButton = document.querySelector('#downloadButton');
const resultStatusTitle = document.querySelector('#resultStatusTitle');
const resultStatusNote = document.querySelector('#resultStatusNote');
const errorBox = document.querySelector('#errorBox');
const apiKeyDialog = document.querySelector('#apiKeyDialog');
const apiKeyForm = document.querySelector('#apiKeyForm');
const apiKeyInput = document.querySelector('#apiKeyInput');
const keyMessage = document.querySelector('#keyMessage');
const clearKey = document.querySelector('#clearKey');
const closeKeyDialog = document.querySelector('#closeKeyDialog');

let assets = [];
let freeCreationBackendReady = false;
const MERCHANT_NAME_MAX_CHARS = 10;
const roles = [
  ['product', '真实产品'], ['style_reference', '风格参考']
];

function validateMerchantName() {
  const activeName = workbenchMode.value === 'free_creation' ? freeMerchantName : merchantName;
  const activeHint = workbenchMode.value === 'free_creation' ? document.querySelector('#freeMerchantNameHint') : merchantNameHint;
  const count = Array.from(activeName.value).length;
  const overflow = count > MERCHANT_NAME_MAX_CHARS;
  activeName.setCustomValidity(overflow ? `商家名称最多填写 ${MERCHANT_NAME_MAX_CHARS} 个字符。` : '');
  activeName.classList.toggle('invalid', overflow);
  activeHint.textContent = overflow
    ? `已输入 ${count} 个字符，请删减至 ${MERCHANT_NAME_MAX_CHARS} 个以内`
    : `${count} / ${MERCHANT_NAME_MAX_CHARS} 个字符`;
  activeHint.classList.toggle('field-error', overflow);
  return !overflow;
}

merchantName.addEventListener('input', validateMerchantName);
freeMerchantName.addEventListener('input', validateMerchantName);
validateMerchantName();

function syncWorkbenchMode(mode) {
  if (mode === 'size_adaptation') return;
  const free = mode === 'free_creation';
  workbenchMode.value = mode;
  standardFields.hidden = free;
  freeFields.hidden = !free;
  standardFields.querySelectorAll('input,select,textarea').forEach(control => { control.disabled = free; });
  freeFields.querySelectorAll('input,select,textarea').forEach(control => { control.disabled = !free; });
  creationMethodField.hidden = !free;
  merchantName.required = !free;
  form.elements.recruitment_type.required = !free;
  freeMerchantName.required = free;
  freeHeadline.required = free;
  introCopy.textContent = free
    ? '输入标题并按需上传产品或视觉参考，系统会自由设计主视觉并自动合成饭团固定信息条。'
    : '上传素材、填写活动信息，系统会生成主视觉，并自动合成饭团固定信息条。';
  assetHelp.textContent = free
    ? '产品素材选填；选择“视觉参考创作”时，必须至少上传并标记一张风格参考图。'
    : '上传菜品、饮品、环境或风格参考。商家 Logo 在下方单独上传。';
  modeTabs.forEach(tab => tab.classList.toggle('active', tab.dataset.mode === mode));
  syncAssetMode();
  validateMerchantName();
}
modeTabs.forEach(tab => tab.addEventListener('click', () => syncWorkbenchMode(tab.dataset.mode)));
syncWorkbenchMode('standard');

async function checkHealth() {
  try {
    const response = await fetch('/api/health', {cache: 'no-store'});
    const data = await response.json();
    freeCreationBackendReady = Boolean(data.free_creation_prompt_version);
    if (data.api_configured && data.skill_assets_ready) {
      apiState.className = 'api-state ready';
      apiState.innerHTML = '<span></span>生成服务已就绪';
    } else {
      apiState.className = 'api-state warning';
      apiState.innerHTML = '<span></span>待配置 API Key';
    }
  } catch {
    apiState.className = 'api-state warning';
    apiState.innerHTML = '<span></span>服务未连接';
  }
}

apiState.addEventListener('click', () => {
  keyMessage.hidden = true;
  apiKeyInput.value = '';
  apiKeyDialog.showModal();
  apiKeyInput.focus();
});
closeKeyDialog.addEventListener('click', () => apiKeyDialog.close());
apiKeyDialog.addEventListener('click', event => { if (event.target === apiKeyDialog) apiKeyDialog.close(); });

async function updateApiKey(apiKey) {
  keyMessage.hidden = true;
  const response = await fetch('/api/settings/api-key', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({api_key: apiKey})
  });
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.message || '无法保存 API Key。');
  await checkHealth();
  return payload;
}

apiKeyForm.addEventListener('submit', async event => {
  event.preventDefault();
  const key = apiKeyInput.value.trim();
  if (!key) { keyMessage.textContent = '请输入 API Key。'; keyMessage.hidden = false; return; }
  try { await updateApiKey(key); apiKeyInput.value = ''; apiKeyDialog.close(); }
  catch (error) { keyMessage.textContent = error.message; keyMessage.hidden = false; }
});
clearKey.addEventListener('click', async () => {
  try { await updateApiKey(''); apiKeyInput.value = ''; apiKeyDialog.close(); }
  catch (error) { keyMessage.textContent = error.message; keyMessage.hidden = false; }
});

function addFiles(fileList) {
  const incoming = [...fileList].filter(file => ['image/png', 'image/jpeg', 'image/webp'].includes(file.type));
  const available = 9 - assets.length;
  incoming.slice(0, available).forEach(file => assets.push({file, role: 'product', url: URL.createObjectURL(file)}));
  renderAssets();
}

function renderAssets() {
  const aiFreestyle = workbenchMode.value === 'free_creation' && form.elements.creation_method.value === 'ai_free';
  assetGrid.innerHTML = '';
  assets.forEach((asset, index) => {
    if (aiFreestyle) asset.role = 'product';
    const card = document.createElement('div');
    card.className = 'asset-card';
    const options = roles.map(([value, label]) => `<option value="${value}" ${asset.role === value ? 'selected' : ''}>${label}</option>`).join('');
    const roleControl = aiFreestyle
      ? '<span class="asset-fixed-role">真实产品</span>'
      : `<select aria-label="素材 ${index + 1} 的用途">${options}</select>`;
    card.innerHTML = `<img src="${asset.url}" alt="素材 ${index + 1}"><button type="button" aria-label="删除素材 ${index + 1}">×</button>${roleControl}`;
    card.querySelector('button').addEventListener('click', () => {
      URL.revokeObjectURL(asset.url); assets.splice(index, 1); renderAssets();
    });
    const roleSelect = card.querySelector('select');
    if (roleSelect) roleSelect.addEventListener('change', event => { asset.role = event.target.value; });
    assetGrid.append(card);
  });
  assetCount.textContent = `${assets.length} / 9`;
  imageInput.value = '';
}

function syncAssetMode() {
  const free = workbenchMode.value === 'free_creation';
  const aiFreestyle = free && form.elements.creation_method.value === 'ai_free';
  if (aiFreestyle) assets.forEach(asset => { asset.role = 'product'; });
  dropzoneTitle.textContent = aiFreestyle ? '上传产品图' : '选择或拖入图片';
  assetHelp.textContent = aiFreestyle
    ? '产品图片选填；上传后全部作为真实产品素材，不使用视觉参考图。无图时 AI 将根据文字自主生成产品视觉。'
    : free
      ? '每张图片可标记为真实产品或风格参考；至少需要一张风格参考图，产品图片选填。'
      : '上传菜品、饮品、环境或风格参考。商家 Logo 在下方单独上传。';
  additionalNotes.placeholder = free
    ? '可填写产品名称、希望展示的信息或视觉要求，例如：突出新品、年轻活泼、夏日氛围等。不填写视觉要求时，AI 将自主设计。'
    : '例如：产品一主两辅；时间先留空';
  renderAssets();
}

document.querySelectorAll('input[name="creation_method"]').forEach(input => {
  input.addEventListener('change', syncAssetMode);
});

imageInput.addEventListener('change', event => addFiles(event.target.files));
['dragenter', 'dragover'].forEach(name => dropzone.addEventListener(name, event => {event.preventDefault(); dropzone.classList.add('drag');}));
['dragleave', 'drop'].forEach(name => dropzone.addEventListener(name, event => {event.preventDefault(); dropzone.classList.remove('drag');}));
dropzone.addEventListener('drop', event => addFiles(event.dataTransfer.files));

function syncLogoMode() {
  const required = overlayMode.value === 'co_brand';
  logoField.hidden = !required;
  logoField.setAttribute('aria-hidden', String(!required));
  merchantLogo.required = required;
  merchantLogo.setAttribute('aria-required', String(required));
  if (!required) merchantLogo.value = '';
}
overlayMode.addEventListener('change', syncLogoMode);
syncLogoMode();

const stageCopy = {
  creative: ['创意生成', '正在生成中央完整创意…'],
  outpaint: ['背景扩展', '中央创意已生成，正在连续扩展上下环境背景…'],
  compose: ['品牌合成', '背景扩展已完成，正在合成固定品牌信息条…'],
  completed: ['品牌合成', '三阶段均已完成，正在载入最终海报…']
};

function showGenerationStage(stage) {
  const [title, detail] = stageCopy[stage] || stageCopy.creative;
  workingTitle.textContent = title;
  workingDetail.textContent = detail;
  const names = ['creative', 'outpaint', 'compose'];
  const activeIndex = stage === 'completed' ? generationStages.length : Math.max(0, names.indexOf(stage));
  generationStages.forEach((item, index) => {
    item.classList.toggle('done', index < activeIndex);
    item.classList.toggle('active', index === activeIndex);
  });
}

async function trackGenerationProgress(progressId, signal) {
  while (!signal.aborted) {
    try {
      const response = await fetch(`/api/progress/${progressId}`, {cache: 'no-store', signal});
      if (response.ok) {
        const payload = await response.json();
        showGenerationStage(payload.stage);
        if (payload.stage === 'completed' || payload.stage === 'failed') return;
      }
    } catch (error) {
      if (error.name === 'AbortError') return;
    }
    await new Promise(resolve => setTimeout(resolve, 800));
  }
}

function setWorking(active) {
  button.disabled = active;
  button.querySelector('span').textContent = active ? '正在创建…' : '开始创建';
  emptyPreview.hidden = active || !resultImage.hidden;
  workingState.hidden = !active;
  if (active) { resultImage.hidden = true; resultActions.hidden = true; errorBox.hidden = true; }
}

function showError(message) {
  setWorking(false);
  emptyPreview.hidden = false;
  resultImage.hidden = true;
  resultActions.hidden = true;
  errorBox.hidden = false;
  errorBox.querySelector('p').textContent = message;
}

form.addEventListener('submit', async event => {
  event.preventDefault();
  document.querySelectorAll('.invalid').forEach(el => el.classList.remove('invalid'));
  validateMerchantName();
  if (!form.checkValidity()) { form.reportValidity(); return; }
  const free = workbenchMode.value === 'free_creation';
  const creationMethod = form.elements.creation_method.value;
  if (free && !freeCreationBackendReady) {
    showError('当前后端尚未加载自由创作 V1。请重启本地工作台后再试，本次未发起图片 API 调用。');
    return;
  }
  if (!free && assets.length < 1) { dropzone.classList.add('invalid'); showError('请至少上传 1 张真实产品或参考图片。'); return; }
  if (free && creationMethod === 'style_reference' && !assets.some(asset => asset.role === 'style_reference')) {
    dropzone.classList.add('invalid'); showError('视觉参考创作需要至少一张标记为“风格参考”的图片。'); return;
  }
  if (overlayMode.value === 'co_brand' && !merchantLogo.files[0]) { merchantLogo.classList.add('invalid'); showError('联名模式需要上传真实商家 Logo。'); return; }

  const data = new FormData(form);
  if (free) {
    data.set('merchant_name', freeMerchantName.value);
    data.set('headline', freeHeadline.value);
    data.set('subtitle', freeSubtitle.value);
  }
  const progressId = crypto.randomUUID();
  data.set('progress_id', progressId);
  data.delete('images');
  assets.forEach(asset => data.append('images', asset.file, asset.file.name));
  const submittedRoles = free && creationMethod === 'ai_free'
    ? assets.map(() => 'product')
    : assets.map(asset => asset.role);
  data.set('image_roles', JSON.stringify(submittedRoles));
  setWorking(true);
  showGenerationStage('creative');
  const progressController = new AbortController();
  const progressTracker = trackGenerationProgress(progressId, progressController.signal);
  try {
    const response = await fetch('/api/generate', {method: 'POST', body: data});
    const payload = await response.json();
    if (!response.ok) {
      const detail = payload.detail ? payload.detail.replace(/^(?:OPENAI|KIE)_[A-Z_]+:\d*:?/, '').trim() : '';
      throw new Error(detail || payload.message || '生成失败。');
    }
    showGenerationStage('completed');
    const cacheBuster = `?v=${Date.now()}`;
    resultImage.src = payload.result.image_url + cacheBuster;
    await resultImage.decode();
    setWorking(false);
    emptyPreview.hidden = true;
    resultImage.hidden = false;
    resultActions.hidden = false;
    downloadButton.href = payload.result.download_url;
    resultStatusTitle.textContent = '机械验证通过';
    resultStatusNote.textContent = '尺寸与固定模板像素已核对；视觉仍需人工确认。';
    downloadButton.textContent = '下载 PNG';
    errorBox.hidden = true;
  } catch (error) {
    showError(error.message || '生成失败，请检查服务状态。');
  } finally {
    progressController.abort();
    await progressTracker;
  }
});

checkHealth();

