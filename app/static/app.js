const form = document.querySelector('#posterForm');
const imageInput = document.querySelector('#images');
const assetGrid = document.querySelector('#assetGrid');
const assetCount = document.querySelector('#assetCount');
const dropzone = document.querySelector('#dropzone');
const overlayMode = document.querySelector('#overlayMode');
const logoField = document.querySelector('#logoField');
const merchantLogo = document.querySelector('#merchantLogo');
const merchantName = document.querySelector('#merchantName');
const merchantNameHint = document.querySelector('#merchantNameHint');
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
const MERCHANT_NAME_MAX_CHARS = 10;
const roles = [
  ['product', '真实产品'], ['style_reference', '风格参考']
];

function validateMerchantName() {
  const count = Array.from(merchantName.value).length;
  const overflow = count > MERCHANT_NAME_MAX_CHARS;
  merchantName.setCustomValidity(overflow ? `商家名称最多填写 ${MERCHANT_NAME_MAX_CHARS} 个字符。` : '');
  merchantName.classList.toggle('invalid', overflow);
  merchantNameHint.textContent = overflow
    ? `已输入 ${count} 个字符，请删减至 ${MERCHANT_NAME_MAX_CHARS} 个以内`
    : `${count} / ${MERCHANT_NAME_MAX_CHARS} 个字符`;
  merchantNameHint.classList.toggle('field-error', overflow);
  return !overflow;
}

merchantName.addEventListener('input', validateMerchantName);
validateMerchantName();

async function checkHealth() {
  try {
    const response = await fetch('/api/health', {cache: 'no-store'});
    const data = await response.json();
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
  assetGrid.innerHTML = '';
  assets.forEach((asset, index) => {
    const card = document.createElement('div');
    card.className = 'asset-card';
    const options = roles.map(([value, label]) => `<option value="${value}" ${asset.role === value ? 'selected' : ''}>${label}</option>`).join('');
    card.innerHTML = `<img src="${asset.url}" alt="素材 ${index + 1}"><button type="button" aria-label="删除素材 ${index + 1}">×</button><select aria-label="素材 ${index + 1} 的用途">${options}</select>`;
    card.querySelector('button').addEventListener('click', () => {
      URL.revokeObjectURL(asset.url); assets.splice(index, 1); renderAssets();
    });
    card.querySelector('select').addEventListener('change', event => { asset.role = event.target.value; });
    assetGrid.append(card);
  });
  assetCount.textContent = `${assets.length} / 9`;
  imageInput.value = '';
}

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
  if (assets.length < 1) { dropzone.classList.add('invalid'); showError('请至少上传 1 张真实产品或参考图片。'); return; }
  if (overlayMode.value === 'co_brand' && !merchantLogo.files[0]) { merchantLogo.classList.add('invalid'); showError('联名模式需要上传真实商家 Logo。'); return; }

  const data = new FormData(form);
  const progressId = crypto.randomUUID();
  data.set('progress_id', progressId);
  data.delete('images');
  assets.forEach(asset => data.append('images', asset.file, asset.file.name));
  data.set('image_roles', JSON.stringify(assets.map(asset => asset.role)));
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

