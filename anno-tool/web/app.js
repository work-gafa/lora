/* 行李物品标注与识别平台 —— 前端（Vue3 + Element Plus，无构建） */
const { createApp, ref, reactive, computed, watch, onMounted, nextTick } = Vue

/* ---------------- 通用请求 ---------------- */
async function req(url, options = {}) {
  let res
  try {
    res = await fetch(url, options)
  } catch (_) {
    throw new Error('无法连接后端服务，请确认已启动（端口 8004）')
  }
  if (!res.ok) {
    let detail = `HTTP ${res.status}`
    try {
      const d = await res.json()
      if (d && d.detail) detail = d.detail
    } catch (_) { /* 非 JSON */ }
    throw new Error(detail)
  }
  return res.json()
}

const postJSON = (url, body, method = 'POST') =>
  req(url, {
    method,
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })

/* 给一批名字查「会归到哪个规范名」（null = 归不进去，导出时会被丢弃） */
const classifyNames = (names) => postJSON('/api/classify', { names })

/* 场景列表 + 每场景的清单项 + 每张图所属场景 */
const fetchScenarios = () => req('/api/scenarios')

/* 设置某张图的场景（旅行 / 上学） */
const setImageScenario = (name, scenario) =>
  postJSON('/api/image-scenarios', { image_scenarios: { [name]: scenario } }, 'PUT')

/* ================= 数据集（我的标注） ================= */
const DatasetPanel = {
  props: {
    images: Array, annotations: Object, stats: Object,
    scenarios: Object, imageScenarios: Object,
    canon: Array, taxonItems: Array,
  },
  emits: ['open', 'changed'],
  setup(props, { emit }) {
    const keyword = ref('')
    const scenFilter = ref('')
    const scenOptions = computed(() =>
      Object.entries(props.scenarios || {}).map(([k, v]) => ({ value: k, label: v })))
    const scenLabel = (k) => (props.scenarios || {})[k] || k
    // 只勾选「能看到具体名」的情况，数字才有指导意义
    const refinable = computed(() => new Set(
      (props.taxonItems || []).filter((it) => (it.aliases || []).length).map((it) => it.name)))
    function coarseCount(name) {
      const boxes = props.annotations[name] || []
      return boxes.filter((b) => refinable.value.has((b.name || '').trim())).length
    }
    const filtered = computed(() => {
      const k = keyword.value.trim()
      return props.images.filter((i) =>
        (!k || i.name.includes(k)) && (!scenFilter.value || i.scenario === scenFilter.value))
    })
    const imgUrl = (n) => `/api/image/${encodeURIComponent(n)}`

    async function switchScenario(img, scen) {
      if (img.scenario === scen) return
      try {
        await setImageScenario(img.name, scen)
        img.scenario = scen
        ElementPlus.ElMessage.success(`已设为「${scenLabel(scen)}」`)
        emit('changed')
      } catch (e) { ElementPlus.ElMessage.error(e.message) }
    }

    // 删除一张图（连标注一起）。文件是移到 _trash\ 而不是真删，可找回。
    async function removeImage(img) {
      const n = img.boxes || 0
      try {
        await ElementPlus.ElMessageBox.confirm(
          `确定删除「${img.name}」？\n` +
          (n ? `它上面有 ${n} 个标注框，会一并删掉。\n` : '') +
          '\n文件不会彻底删除，而是移到 data\\labeled\\_trash\\ 里，需要时可以从资源管理器找回。',
          '删除确认',
          { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消',
            confirmButtonClass: 'el-button--danger' })
      } catch (_) { return }
      try {
        const d = await req(`/api/images/${encodeURIComponent(img.name)}`, { method: 'DELETE' })
        ElementPlus.ElMessage.success(
          d.removed_boxes ? `已删除（连同 ${d.removed_boxes} 个框）` : '已删除')
        emit('changed')
      } catch (e) { ElementPlus.ElMessage.error(e.message) }
    }
    return { keyword, scenFilter, scenOptions, scenLabel, filtered, imgUrl, emit, switchScenario,
      coarseCount, removeImage }
  },
  template: `
  <div>
    <div class="stat-row">
      <div class="stat-card"><div class="v">{{ stats.images || 0 }}</div><div class="l">图片总数</div></div>
      <div class="stat-card"><div class="v">{{ stats.annotated || 0 }}</div><div class="l">已标注图片</div></div>
      <div class="stat-card"><div class="v">{{ stats.boxes || 0 }}</div><div class="l">标注框总数</div></div>
      <div class="stat-card"><div class="v">{{ stats.items || 0 }}</div><div class="l">清单项数</div></div>
    </div>

    <el-card shadow="never">
      <template #header>
        <div style="display:flex;align-items:center;justify-content:space-between;gap:8px;flex-wrap:wrap">
          <span>我的图片</span>
          <span style="display:flex;gap:8px">
            <el-select v-model="scenFilter" size="small" clearable placeholder="全部场景" style="width:150px">
              <el-option v-for="o in scenOptions" :key="o.value" :label="o.label" :value="o.value" />
            </el-select>
            <el-input v-model="keyword" size="small" placeholder="搜索文件名" style="width:180px" clearable />
          </span>
        </div>
      </template>

      <el-empty v-if="!filtered.length" description="暂无图片，可在「方框标注」页上传" />

      <div class="img-grid">
        <div v-for="img in filtered" :key="img.name" class="img-card">
          <img :src="imgUrl(img.name)" :alt="img.name" loading="lazy" @click="emit('open', img.name)" />
          <div class="meta">
            <div class="nm" :title="img.name">
              <a href="javascript:;" @click="emit('open', img.name)">{{ img.name }}</a>
            </div>
            <div class="tags">
              <el-tag size="small" :type="img.scenario === 'school' ? 'warning' : 'primary'">
                {{ scenLabel(img.scenario) }}
              </el-tag>
              <el-tag size="small" :type="img.boxes > 0 ? 'success' : 'info'">
                {{ img.boxes > 0 ? img.boxes + ' 个框' : '未标注' }}
              </el-tag>
              <el-tag v-if="coarseCount(img.name)" size="small" type="info">
                {{ coarseCount(img.name) }} 个大类名
              </el-tag>
            </div>
            <div class="tags" style="margin-top:6px;justify-content:space-between">
              <el-radio-group :model-value="img.scenario" size="small" @change="switchScenario(img, $event)">
                <el-radio-button v-for="o in scenOptions" :key="o.value" :value="o.value">
                  {{ o.label.split(' / ')[0] }}
                </el-radio-button>
              </el-radio-group>
              <el-button size="small" type="danger" text @click="removeImage(img)">删除</el-button>
            </div>
          </div>
        </div>
      </div>
    </el-card>
  </div>
  `,
}

/* ================= 方框标注 ================= */
const AnnotatePanel = {
  props: {
    current: String, canon: Array, annotations: Object,
    scenarios: Object, imageScenarios: Object, taxonItems: Array,
  },
  emits: ['saved'],
  setup(props, { emit }) {
    const cv = ref(null)
    const boxes = ref([])
    const selectedId = ref(null)
    const imgName = ref('')
    const imgEl = ref(null)
    const loading = ref(false)
    const detecting = ref(false)
    const recognizing = ref(false)
    const recognizeResult = ref(null)
    const showResult = ref(false)
    const hasChange = ref(false)
    const canonMap = ref({})      // 输入的名字 -> 会归到的规范名（null = 归不进去）
    let classifyTimer = null

    // 当前这张图属于哪个场景 → 只显示该场景的清单项
    const scenario = computed(() =>
      (props.imageScenarios || {})[imgName.value] || 'travel')
    const scenLabel = computed(() => (props.scenarios || {})[scenario.value] || scenario.value)
    const canonOptions = computed(() => {
      const inSet = new Set(
        (props.taxonItems || [])
          .filter((it) => (it.scenarios || []).includes(scenario.value))
          .map((it) => it.name))
      return inSet.size ? props.canon.filter((c) => inSet.has(c)) : props.canon
    })
    // 框里写了不属于当前场景的物品（导出时不会写进答案）
    const offScenario = computed(() =>
      boxes.value.filter((b) => b.name && !canonOptions.value.includes(b.name)))

    // ---- 具体名（细名）支持 ----
    // 下拉按「大类」分组，组内列出该项的全部具体名（别名）。
    // 例：组「娱乐用品」下有 玩具/玩偶/娃娃/公仔/扑克牌/音箱/拼豆…
    // 选了「玩偶」→ 框里存"玩偶"，导出时自动归到「娱乐用品」。
    const fineGroups = computed(() => {
      const scen = scenario.value
      return (props.taxonItems || [])
        .filter((it) => (it.scenarios || []).includes(scen))
        .map((it) => ({
          label: it.name,
          // 大类名本身也放进去（有些东西确实就叫这个）
          options: [...new Set([it.name, ...(it.aliases || [])])],
        }))
    })
    // 能被细化的大类（有具体名可选的）
    const refinable = computed(() => new Set(
      (props.taxonItems || [])
        .filter((it) => (it.aliases || []).length)
        .map((it) => it.name)))
    // 用大类名写的框 —— 看不出来具体是什么，建议改细
    const coarseBoxes = computed(() =>
      boxes.value.filter((b) => b.name && canonOptions.value.includes(b.name)
        && refinable.value.has(b.name)))
    function isCoarse(name) {
      return !!name && canonOptions.value.includes(name) && refinable.value.has(name)
    }

    // 框里写的名字能不能归进清单；不能的会在导出时被丢弃，这里提前红字提醒
    const unclassified = computed(() =>
      boxes.value.filter((b) => b.name && canonMap.value[b.name] === null)
    )
    function mappingOf(name) {
      const v = canonMap.value[name]
      if (v === undefined) return null
      return v
    }
    async function refreshClassify() {
      const names = [...new Set(boxes.value.map((b) => (b.name || '').trim()).filter(Boolean))]
      if (!names.length) { canonMap.value = {}; return }
      try {
        const d = await classifyNames(names)
        canonMap.value = d.results || {}
      } catch (_) { /* 归类查询失败不打断标注 */ }
    }
    function scheduleClassify() {
      clearTimeout(classifyTimer)
      classifyTimer = setTimeout(refreshClassify, 350)
    }

    let mode = null          // 'draw' | 'move' | 'resize'
    let start = null         // {x,y}
    let handleIdx = -1
    let boxAtStart = null
    const HSIZE = 9
    const HANDLES = [[0,0],[0.5,0],[1,0],[1,0.5],[1,1],[0.5,1],[0,1],[0,0.5]]
    const COLORS = ['#e24b4a','#378add','#1d9e75','#ba7517','#7f77dd','#d4537e','#0f8b8b','#639922']

    const ctx = () => cv.value.getContext('2d')

    function uid() { return Date.now().toString(36) + Math.random().toString(36).slice(2, 6) }
    function colorFor(i) { return COLORS[i % COLORS.length] }

    /* ---------- 画布尺寸 ---------- */
    function fitSize() {
      const maxW = Math.max(360, (cv.value.parentElement.clientWidth || 900) - 24)
      const r = imgEl.value.width / imgEl.value.height
      let w = Math.min(maxW, imgEl.value.width)
      let h = w / r
      const maxH = 560
      if (h > maxH) { h = maxH; w = h * r }
      return { w: Math.round(w), h: Math.round(h) }
    }

    function drawAll(preview) {
      const c = cv.value
      if (!c || !imgEl.value) return
      const { w, h } = fitSize()
      const dpr = window.devicePixelRatio || 1
      if (c.width !== w * dpr || c.height !== h * dpr) {
        c.width = w * dpr
        c.height = h * dpr
        c.style.width = w + 'px'
        c.style.height = h + 'px'
      }
      const g = ctx()
      g.setTransform(dpr, 0, 0, dpr, 0, 0)
      g.clearRect(0, 0, w, h)
      g.drawImage(imgEl.value, 0, 0, w, h)

      boxes.value.forEach((b) => {
        const x = b.bbox[0] * w, y = b.bbox[1] * h
        const bw = (b.bbox[2] - b.bbox[0]) * w, bh = (b.bbox[3] - b.bbox[1]) * h
        const sel = b.id === selectedId.value
        g.lineWidth = sel ? 3 : 2
        g.strokeStyle = b.color
        g.setLineDash(sel ? [7, 4] : [])
        g.strokeRect(x, y, bw, bh)
        g.setLineDash([])
        const label = b.name || '未命名'
        g.font = "13px 'Microsoft YaHei', sans-serif"
        const tw = g.measureText(label).width + 12
        const ly = y > 20 ? y - 18 : y
        g.fillStyle = b.color
        g.fillRect(x, ly, tw, 18)
        g.fillStyle = '#fff'
        g.fillText(label, x + 6, ly + 13)
        if (sel) {
          g.fillStyle = '#fff'
          g.strokeStyle = '#0f8b8b'
          g.lineWidth = 1.5
          HANDLES.forEach(([fx, fy]) => {
            const hx = (b.bbox[0] + fx * (b.bbox[2] - b.bbox[0])) * w
            const hy = (b.bbox[1] + fy * (b.bbox[3] - b.bbox[1])) * h
            g.fillRect(hx - HSIZE / 2, hy - HSIZE / 2, HSIZE, HSIZE)
            g.strokeRect(hx - HSIZE / 2, hy - HSIZE / 2, HSIZE, HSIZE)
          })
        }
      })

      if (preview) {
        g.strokeStyle = '#0f8b8b'
        g.lineWidth = 2
        g.setLineDash([6, 4])
        g.strokeRect(Math.min(start.x, preview.x), Math.min(start.y, preview.y),
          Math.abs(preview.x - start.x), Math.abs(preview.y - start.y))
        g.setLineDash([])
      }
    }

    /* ---------- 命中测试 ---------- */
    function pos(e) {
      const r = cv.value.getBoundingClientRect()
      return {
        x: (e.clientX - r.left) * (cv.value.width / (window.devicePixelRatio || 1) / r.width),
        y: (e.clientY - r.top) * (cv.value.height / (window.devicePixelRatio || 1) / r.height),
      }
    }
    function toNorm(p) {
      const w = cv.value.width / (window.devicePixelRatio || 1)
      const h = cv.value.height / (window.devicePixelRatio || 1)
      return { x: p.x / w, y: p.y / h }
    }
    function hitHandle(n) {
      const w = cv.value.width / (window.devicePixelRatio || 1)
      const h = cv.value.height / (window.devicePixelRatio || 1)
      const b = boxes.value.find((x) => x.id === selectedId.value)
      if (!b) return -1
      for (let i = 0; i < HANDLES.length; i++) {
        const [fx, fy] = HANDLES[i]
        const hx = (b.bbox[0] + fx * (b.bbox[2] - b.bbox[0])) * w
        const hy = (b.bbox[1] + fy * (b.bbox[3] - b.bbox[1])) * h
        if (Math.abs(n.x * w - hx) <= HSIZE && Math.abs(n.y * h - hy) <= HSIZE) return i
      }
      return -1
    }
    function hitBox(n) {
      for (let i = boxes.value.length - 1; i >= 0; i--) {
        const b = boxes.value[i].bbox
        if (n.x >= b[0] && n.x <= b[2] && n.y >= b[1] && n.y <= b[3]) return boxes.value[i].id
      }
      return null
    }
    const clamp = (v) => Math.max(0, Math.min(1, v))

    /* ---------- 鼠标事件 ---------- */
    function onDown(e) {
      if (!imgEl.value) return
      const p = toNorm(pos(e))
      const hi = hitHandle(p)
      if (hi >= 0) {
        mode = 'resize'; handleIdx = hi
        boxAtStart = [...boxes.value.find((x) => x.id === selectedId.value).bbox]
        start = p
        return
      }
      const id = hitBox(p)
      if (id) {
        selectedId.value = id
        mode = 'move'
        boxAtStart = [...boxes.value.find((x) => x.id === id).bbox]
        start = p
        drawAll(null)
        return
      }
      mode = 'draw'
      start = p
      selectedId.value = null
    }
    function onMove(e) {
      if (!mode || !imgEl.value) return
      const p = toNorm(pos(e))
      if (mode === 'draw') { drawAll({ x: p.x * cv.value.width / (window.devicePixelRatio || 1), y: p.y * cv.value.height / (window.devicePixelRatio || 1) }); return }
      const b = boxes.value.find((x) => x.id === selectedId.value)
      if (!b) return
      if (mode === 'move') {
        const dx = p.x - start.x, dy = p.y - start.y
        const w = boxAtStart[2] - boxAtStart[0], h = boxAtStart[3] - boxAtStart[1]
        let x1 = clamp(boxAtStart[0] + dx), y1 = clamp(boxAtStart[1] + dy)
        if (x1 + w > 1) x1 = 1 - w
        if (y1 + h > 1) y1 = 1 - h
        b.bbox = [x1, y1, x1 + w, y1 + h]
      } else if (mode === 'resize') {
        const [fx, fy] = HANDLES[handleIdx]
        let [x1, y1, x2, y2] = [...boxAtStart]
        if (fx === 0) x1 = clamp(Math.min(p.x, x2 - 0.01))
        if (fx === 1) x2 = clamp(Math.max(p.x, x1 + 0.01))
        if (fy === 0) y1 = clamp(Math.min(p.y, y2 - 0.01))
        if (fy === 1) y2 = clamp(Math.max(p.y, y1 + 0.01))
        b.bbox = [x1, y1, x2, y2]
      }
      hasChange.value = true
      drawAll(null)
    }
    function onUp(e) {
      if (mode === 'draw' && start) {
        const p = toNorm(pos(e))
        const x1 = Math.min(start.x, p.x), y1 = Math.min(start.y, p.y)
        const x2 = Math.max(start.x, p.x), y2 = Math.max(start.y, p.y)
        if ((x2 - x1) > 0.01 && (y2 - y1) > 0.01) {
          const nb = {
            id: uid(), name: props.canon[0] || '', bbox: [x1, y1, x2, y2],
            color: colorFor(boxes.value.length),
          }
          boxes.value.push(nb)
          selectedId.value = nb.id
          hasChange.value = true
        }
      }
      mode = null; start = null; handleIdx = -1
      drawAll(null)
    }

    /* ---------- 加载图片 ---------- */
    async function loadImage(name) {
      if (!name) return
      loading.value = true
      recognizeResult.value = null
      try {
        const img = new Image()
        img.src = `/api/image/${encodeURIComponent(name)}`
        await new Promise((res, rej) => { img.onload = res; img.onerror = rej })
        imgEl.value = img
        imgName.value = name
        const saved = props.annotations[name] || []
        boxes.value = saved.map((b, i) => ({
          id: uid() + i, name: b.name || '', bbox: b.bbox ? [...b.bbox] : [0, 0, 0, 0],
          color: colorFor(i),
        }))
        selectedId.value = null
        hasChange.value = false
        await nextTick()
        drawAll(null)
        refreshClassify()
      } catch (_) {
        ElementPlus.ElMessage.error('图片加载失败')
      } finally {
        loading.value = false
      }
    }

    /* ---------- 操作 ---------- */
    function selectBox(id) { selectedId.value = id; drawAll(null) }
    function delBox(id) {
      boxes.value = boxes.value.filter((b) => b.id !== id)
      if (selectedId.value === id) selectedId.value = null
      hasChange.value = true
      drawAll(null)
      scheduleClassify()
    }
    async function save() {
      if (!imgName.value) return
      const payload = {}
      payload[imgName.value] = boxes.value.map((b) => ({
        name: b.name, bbox: b.bbox.map((v) => Math.round(v * 10000) / 10000),
      }))
      try {
        await req('/api/annotations', {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ annotations: payload }),
        })
        hasChange.value = false
        ElementPlus.ElMessage.success('已保存')
        emit('saved')
      } catch (e) { ElementPlus.ElMessage.error(e.message) }
    }
    async function autodetect() {
      if (!imgName.value) return
      detecting.value = true
      try {
        const d = await req(`/api/autodetect/${encodeURIComponent(imgName.value)}`, { method: 'POST' })
        const [W, H] = d.size
        boxes.value = (d.boxes || []).map((b, i) => ({
          id: uid() + i, name: b.name,
          bbox: [b.bbox_px[0] / W, b.bbox_px[1] / H, b.bbox_px[2] / W, b.bbox_px[3] / H],
          color: colorFor(i),
        }))
        selectedId.value = null
        hasChange.value = true
        drawAll(null)
        refreshClassify()
        ElementPlus.ElMessage.success(`AI 预标出 ${boxes.value.length} 个框`)
      } catch (e) { ElementPlus.ElMessage.error(e.message) }
      finally { detecting.value = false }
    }
    async function recognize() {
      if (!imgName.value) return
      recognizing.value = true
      try {
        recognizeResult.value = await req(`/api/recognize/${encodeURIComponent(imgName.value)}`, { method: 'POST' })
        showResult.value = true
      } catch (e) { ElementPlus.ElMessage.error(e.message) }
      finally { recognizing.value = false }
    }
    async function exportData() {
      try {
        const d = await postJSON('/api/export', {})
        const dropKeys = Object.keys(d.dropped || {})
        let msg = `已导出 ${d.images} 条训练数据，其中正样本 ${d.present} 个。\n清单 ${d.items} 项。`
        if (dropKeys.length) {
          msg += `\n\n⚠️ 有 ${dropKeys.length} 个名字归不进清单，已被丢弃：\n` +
            dropKeys.map((k) => `　${k}（${d.dropped[k]} 个框）`).join('\n') +
            '\n\n建议：去「物品清单」把它们加进去，或改选一个规范名。'
        }
        ElementPlus.ElMessageBox.alert(msg, dropKeys.length ? '导出完成（有丢弃）' : '导出成功',
          { confirmButtonText: '好的' })
        emit('saved')
      } catch (e) { ElementPlus.ElMessage.error(e.message) }
    }
    const doUpload = async (file) => {
      const fd = new FormData()
      fd.append('file', file)
      try {
        const d = await req('/api/upload', { method: 'POST', body: fd })
        ElementPlus.ElMessage.success('上传成功')
        await emit('saved')
        await loadImage(d.name)
      } catch (e) { ElementPlus.ElMessage.error(e.message) }
      return false
    }

    watch(() => props.current, (v) => { if (v && v !== imgName.value) loadImage(v) })
    onMounted(() => { if (props.current) loadImage(props.current) })

    return {
      cv, boxes, selectedId, imgName, loading, detecting, recognizing,
      recognizeResult, showResult, hasChange, unclassified, mappingOf, scheduleClassify,
      scenario, scenLabel, canonOptions, offScenario,
      fineGroups, coarseBoxes, isCoarse,
      onDown, onMove, onUp, selectBox, delBox, save, autodetect, recognize,
      exportData, doUpload,
    }
  },
  template: `
  <el-row :gutter="16">
    <el-col :xs="24" :lg="15">
      <el-card shadow="never" v-loading="loading">
        <template #header>
          <div style="display:flex;align-items:center;justify-content:space-between;gap:8px;flex-wrap:wrap">
            <span>
              画框标注
              <span v-if="imgName" style="color:#909399;font-weight:400"> · {{ imgName }}</span>
              <el-tag v-if="imgName" size="small" :type="scenario === 'school' ? 'warning' : 'primary'" style="margin-left:6px">
                {{ scenLabel }}
              </el-tag>
            </span>
            <span>
              <el-upload :show-file-list="false" :before-upload="doUpload" accept=".jpg,.jpeg,.png,.webp,.bmp" style="display:inline-block">
                <el-button size="small">上传新图</el-button>
              </el-upload>
              <el-button size="small" :loading="detecting" :disabled="!imgName" @click="autodetect">AI 自动标注</el-button>
              <el-button size="small" :loading="recognizing" :disabled="!imgName" @click="recognize">LoRA 识别</el-button>
              <el-button size="small" type="primary" :disabled="!imgName" @click="save">保存标注</el-button>
              <el-button size="small" @click="exportData">导出训练数据</el-button>
            </span>
          </div>
        </template>

        <div class="canvas-wrap">
          <canvas ref="cv" @mousedown="onDown" @mousemove="onMove" @mouseup="onUp"></canvas>
        </div>
        <div class="hint" style="margin-top:8px">
          空白处拖拽 = 新画框　·　点框 = 选中　·　拖框内 = 移动　·　拖角点 = 缩放　·　右侧改名/删除<br />
          <span style="color:#0f8b8b">名字尽量写具体（玩偶、双肩包、吹风机…），下拉里每个大类都列出了具体名；训练时会自动归到大类。</span>
        </div>
      </el-card>
    </el-col>

    <el-col :xs="24" :lg="9">
      <el-card shadow="never">
        <template #header>
          <div style="display:flex;align-items:center;justify-content:space-between">
            <span>框列表（{{ boxes.length }}）</span>
            <el-tag size="small" :type="hasChange ? 'warning' : 'success'">
              {{ hasChange ? '有未保存改动' : '已保存' }}
            </el-tag>
          </div>
        </template>

        <el-empty v-if="!boxes.length" description="还没有框，在图上拖一下试试" />

        <el-alert
          v-if="coarseBoxes.length"
          type="info" :closable="false" show-icon style="margin-bottom:10px"
          :title="'有 ' + coarseBoxes.length + ' 个框写的是大类名，以后回看会认不出具体是什么'"
          description="下拉里每个大类下面都列了具体名（如 娱乐用品 → 玩偶 / 音箱 / 扑克牌），换成具体名即可；训练时仍然自动归到这个大类。"
        />

        <el-alert
          v-if="offScenario.length"
          type="warning" :closable="false" show-icon style="margin-bottom:10px"
          :title="'有 ' + offScenario.length + ' 个框不属于「' + scenLabel + '」场景，导出时不会写入'"
          description="如果这张图场景标错了，去「数据集」页改；如果确实要标这个物品，去「物品清单」页把它加到当前场景。"
        />

        <el-alert
          v-if="unclassified.length"
          type="warning" :closable="false" show-icon style="margin-bottom:10px"
          :title="'有 ' + unclassified.length + ' 个框的名字归不进清单，导出时会被丢弃'"
          description="可以从下拉里选一个规范名，或到「物品清单」页把新名字加进去。"
        />

        <div v-for="b in boxes" :key="b.id" class="box-item" :class="{sel: b.id===selectedId}" @click="selectBox(b.id)">
          <div class="swatch" :style="{background:b.color}"></div>
          <el-select
            v-model="b.name"
            size="small"
            filterable
            allow-create
            default-first-option
            clearable
            placeholder="选具体名（如 玩偶 / 双肩包），或直接输入"
            style="flex:1;min-width:0"
            @change="hasChange = true; scheduleClassify()"
          >
            <el-option-group v-for="g in fineGroups" :key="g.label" :label="g.label">
              <el-option v-for="c in g.options" :key="c" :label="c" :value="c" />
            </el-option-group>
          </el-select>

          <el-tag v-if="b.name && mappingOf(b.name) === null" size="small" type="danger">无法归类</el-tag>
          <el-tag v-else-if="b.name && mappingOf(b.name) && mappingOf(b.name) !== b.name" size="small" type="success">
            → {{ mappingOf(b.name) }}
          </el-tag>
          <el-tag v-else-if="b.name && !canonOptions.includes(b.name)" size="small" type="warning">非本场景</el-tag>
          <el-tag v-else-if="isCoarse(b.name)" size="small" type="info">建议写具体名</el-tag>

          <el-button size="small" type="danger" text @click.stop="delBox(b.id)">删除</el-button>
        </div>
      </el-card>

      <el-dialog v-model="showResult" title="LoRA 识别结果" width="520px">
        <div v-if="recognizeResult">
          <div style="margin-bottom:10px;color:#909399;font-size:12px">
            {{ recognizeResult.image }} · 耗时 {{ recognizeResult.elapsed }}s
          </div>
          <el-divider content-position="left">已带（{{ recognizeResult.present.length }}）</el-divider>
          <el-tag v-for="p in recognizeResult.present" :key="p.name" type="success" class="chip">
            {{ p.name }}<span v-if="p.location" style="opacity:.7"> · {{ p.location }}</span>
          </el-tag>
          <el-divider content-position="left">未带（{{ recognizeResult.missing.length }}）</el-divider>
          <el-tag v-for="m in recognizeResult.missing" :key="m" type="info" size="small" class="chip">{{ m }}</el-tag>
        </div>
      </el-dialog>
    </el-col>
  </el-row>
  `,
}

/* ================= VLM 识别 ================= */
const RecognizePanel = {
  props: { canon: Array, scenarios: Object, taxonItems: Array },
  setup(props) {
    const file = ref(null)
    const running = ref(false)
    const result = ref(null)
    const error = ref('')
    // 用户先说清楚是旅行还是上学，再识别 —— 只有该场景的清单项会被检查
    const scenario = ref('travel')
    const scenOptions = computed(() =>
      Object.entries(props.scenarios || {}).map(([k, v]) => ({ value: k, label: v })))
    const scenLabel = computed(() => (props.scenarios || {})[scenario.value] || scenario.value)
    const scenarioItems = computed(() =>
      (props.taxonItems || []).filter((it) => (it.scenarios || []).includes(scenario.value)))

    // ---- 只读方框预览（面向用户，不可编辑）----
    const cvRef = ref(null)
    const imgKey = ref('')            // 上传后的图片名
    const imgUrl = ref('')            // 预览图地址（带时间戳防缓存）
    const previewBoxes = ref([])      // [{name, bbox:[x1,y1,x2,y2] 归一化, inList}]
    const showBoxes = ref(true)
    const spotting = ref(false)       // 正在定位方框

    async function onPick(f) {
      file.value = f
      result.value = null
      error.value = ''
      await run(f)
      return false
    }
    async function run(f) {
      running.value = true
      previewBoxes.value = []
      try {
        const fd = new FormData()
        fd.append('file', f)
        const up = await req('/api/upload', { method: 'POST', body: fd })
        imgKey.value = up.name
        imgUrl.value = `/api/image/${encodeURIComponent(up.name)}?t=${Date.now()}`
        result.value = await req(
          `/api/recognize/${encodeURIComponent(up.name)}?scenario=${encodeURIComponent(scenario.value)}`,
          { method: 'POST' })
        await loadBoxes(up.name)      // 识别完再补方框，失败不影响识别结果
      } catch (e) { error.value = e.message }
      finally { running.value = false }
    }

    // 用检测模型把「已带」的物品在图上框出来（仅供展示，不可编辑）
    async function loadBoxes(name) {
      if (!result.value) return
      spotting.value = true
      try {
        const d = await req(`/api/autodetect/${encodeURIComponent(name)}`, { method: 'POST' })
        const [W, H] = d.size
        const on = new Set((result.value.present || []).map((p) => p.name))
        previewBoxes.value = (d.boxes || []).map((b) => {
          const [x1, y1, x2, y2] = b.bbox_px
          return {
            name: b.name,
            bbox: [x1 / W, y1 / H, x2 / W, y2 / H],
            inList: on.has(b.name),   // true = 模型也判为「已带」
          }
        })
      } catch (_) {
        previewBoxes.value = []      // 定位失败不影响识别结论
      } finally {
        spotting.value = false
        await nextTick()
        drawPreview()                // 无论如何都把图片画出来
      }
    }

    const KEY = '#3B6D11'      // 已带
    const OTHER = '#B0B0AA'    // 检测到但模型判为未带

    function drawPreview() {
      const cv = cvRef.value
      if (!cv || !imgUrl.value) return
      const img = new Image()
      img.onload = () => {
        const W = 1000
        const H = Math.max(1, Math.round(W * img.height / img.width))
        cv.width = W
        cv.height = H
        const ctx = cv.getContext('2d')
        ctx.drawImage(img, 0, 0, W, H)
        if (!showBoxes.value) return
        for (const b of previewBoxes.value) {
          const [x1, y1, x2, y2] = b.bbox
          const color = b.inList ? KEY : OTHER
          ctx.lineWidth = b.inList ? 3 : 2
          ctx.strokeStyle = color
          ctx.strokeRect(x1 * W, y1 * H, (x2 - x1) * W, (y2 - y1) * H)
          const text = b.name + (b.inList ? '' : '（模型判为未带）')
          ctx.font = 'bold 15px sans-serif'
          const tw = ctx.measureText(text).width + 12
          const ty = Math.max(0, y1 * H - 21)
          ctx.fillStyle = color
          ctx.fillRect(x1 * W, ty, tw, 21)
          ctx.fillStyle = '#FFFFFF'
          ctx.fillText(text, x1 * W + 6, ty + 16)
        }
      }
      img.src = imgUrl.value
    }
    watch(showBoxes, () => { drawPreview() })
    watch(cvRef, () => { if (cvRef.value) drawPreview() })

    return { file, running, result, error, onPick, scenario, scenOptions, scenLabel, scenarioItems,
      cvRef, imgKey, imgUrl, previewBoxes, showBoxes, spotting, drawPreview }
  },
  template: `
  <el-row :gutter="16">
    <el-col :xs="24" :lg="10">
      <el-card shadow="never">
        <template #header>
          <div style="display:flex;align-items:center;justify-content:space-between;gap:8px">
            <span>① 先选场景</span>
            <el-radio-group v-model="scenario" size="small">
              <el-radio-button v-for="o in scenOptions" :key="o.value" :value="o.value">
                {{ o.label }}
              </el-radio-button>
            </el-radio-group>
          </div>
        </template>

        <el-alert type="info" :closable="false" show-icon
          :title="'本次只检查「' + scenLabel + '」的 ' + scenarioItems.length + ' 项清单'"
          description="其他场景专属的物品不会出现在结果里。" style="margin-bottom:12px" />

        <el-upload drag :show-file-list="false" :before-upload="onPick" accept=".jpg,.jpeg,.png,.webp,.bmp">
          <div style="padding:26px 12px">
            <div style="font-size:14px;color:#606266">② 拖入照片，或点击选择</div>
            <div style="margin-top:6px;font-size:12px;color:#909399">上传后自动识别，首次需加载模型约 1~2 分钟</div>
          </div>
        </el-upload>
        <el-alert v-if="running" type="info" :closable="false" show-icon title="识别中，请耐心等待…" style="margin-top:12px" />
        <el-alert v-if="error" type="error" :closable="false" show-icon :title="error" style="margin-top:12px" />
      </el-card>
    </el-col>

    <el-col :xs="24" :lg="14">
      <el-card shadow="never">
        <template #header>
          <div style="display:flex;justify-content:space-between;align-items:center">
            <span>识别结果</span>
            <span style="display:flex;gap:8px;align-items:center">
              <el-tag v-if="result" size="small" :type="result.scenario === 'school' ? 'warning' : 'primary'">
                {{ (scenarios || {})[result.scenario] || result.scenario }}
              </el-tag>
              <span v-if="result" style="font-size:12px;color:#909399">耗时 {{ result.elapsed }}s</span>
            </span>
          </div>
        </template>
        <el-empty v-if="!result && !running" description="上传照片后自动识别" />
        <template v-if="result">
          <el-statistic title="已带" :value="result.present.length" />
          <el-divider content-position="left">已带（{{ result.present.length }}）</el-divider>
          <el-tag v-for="p in result.present" :key="p.name" type="success" size="large" class="chip">
            {{ p.name }}<span v-if="p.location" style="opacity:.7"> · {{ p.location }}</span>
          </el-tag>
          <el-divider content-position="left">未带（{{ result.missing.length }}）</el-divider>
          <el-tag v-for="m in result.missing" :key="m" type="info" size="small" class="chip">{{ m }}</el-tag>
        </template>
      </el-card>
    </el-col>
  </el-row>

  <el-row v-if="result" style="margin-top:16px">
    <el-col :span="24">
      <el-card shadow="never">
        <template #header>
          <div style="display:flex;align-items:center;justify-content:space-between;gap:8px;flex-wrap:wrap">
            <span>识别预览<span style="color:#909399;font-weight:400;font-size:12px"> · 用户视图，仅供查看</span></span>
            <span style="display:flex;align-items:center;gap:12px">
              <el-switch v-model="showBoxes" size="small" active-text="显示方框" />
              <el-button size="small" :loading="spotting" @click="drawPreview()">重绘</el-button>
            </span>
          </div>
        </template>

        <el-alert v-if="spotting" type="info" :closable="false" show-icon
          title="正在图上定位方框…" style="margin-bottom:10px" />

        <el-alert v-else-if="!previewBoxes.length" type="warning" :closable="false" show-icon
          title="没能定位到方框" description="检测模型在图上没找到可框出的目标，文字结论仍然有效。"
          style="margin-bottom:10px" />

        <div class="preview-wrap">
          <canvas ref="cvRef"></canvas>
        </div>

        <div class="hint" style="margin-top:8px">
          <span style="display:inline-block;width:10px;height:10px;background:#3B6D11;border-radius:2px;vertical-align:middle"></span>
          深绿框 = 模型判为「已带」　
          <span style="display:inline-block;width:10px;height:10px;background:#B0B0AA;border-radius:2px;vertical-align:middle;margin-left:10px"></span>
          灰框 = 检测到了但模型判为「未带」（可能是误判，供你核对）
        </div>
      </el-card>
    </el-col>
  </el-row>
  `,
}

/* ================= 物品清单 ================= */
const TaxonomyPanel = {
  props: { taxonomy: Object, scenarios: Object },
  emits: ['changed'],
  setup(props, { emit }) {
    const kw = ref('')
    const dialog = ref(false)
    const editing = ref(null)          // null = 新增；否则是原规范名
    const form = reactive({
      name: '', en: '', category: '其他', aliasesText: '', scenarios: [],
    })
    const saving = ref(false)
    const scenOptions = computed(() =>
      Object.entries(props.scenarios || {}).map(([k, v]) => ({ value: k, label: v })))
    const scenLabel = (k) => (props.scenarios || {})[k] || k

    const items = computed(() => {
      const all = props.taxonomy.items || []
      const k = kw.value.trim()
      if (!k) return all
      return all.filter((i) =>
        i.name.includes(k) || (i.aliases || []).some((a) => a.includes(k)))
    })
    const categories = computed(() => {
      const s = new Set((props.taxonomy.items || []).map((i) => i.category))
      return [...s].filter(Boolean)
    })

    function openAdd() {
      editing.value = null
      Object.assign(form, {
        name: '', en: '', category: '其他', aliasesText: '',
        scenarios: scenOptions.value.map((o) => o.value),
      })
      dialog.value = true
    }
    function openEdit(row) {
      editing.value = row.name
      Object.assign(form, {
        name: row.name,
        en: row.en || '',
        category: row.category || '其他',
        aliasesText: (row.aliases || []).join('、'),
        scenarios: [...(row.scenarios || scenOptions.value.map((o) => o.value))],
      })
      dialog.value = true
    }
    function splitAliases(t) {
      return (t || '').split(/[、,，\s]+/).map((s) => s.trim()).filter(Boolean)
    }
    async function submit() {
      if (!form.name.trim()) return ElementPlus.ElMessage.warning('请填规范名')
      saving.value = true
      const body = {
        name: form.name.trim(),
        en: form.en.trim(),
        category: form.category.trim() || '其他',
        aliases: splitAliases(form.aliasesText),
        scenarios: form.scenarios,
      }
      try {
        if (editing.value) {
          const d = await postJSON(`/api/taxonomy/items/${encodeURIComponent(editing.value)}`, body, 'PUT')
          ElementPlus.ElMessage.success(
            d.renamed_boxes ? `已保存，同步更新了 ${d.renamed_boxes} 个标注框` : '已保存')
        } else {
          await postJSON('/api/taxonomy/items', body)
          ElementPlus.ElMessage.success('已新增')
        }
        dialog.value = false
        emit('changed')
      } catch (e) { ElementPlus.ElMessage.error(e.message) }
      finally { saving.value = false }
    }
    async function remove(row) {
      try {
        await ElementPlus.ElMessageBox.confirm(
          `确定删除「${row.name}」？\n删掉后训练数据的清单项会少这一项，已经画好的框如果用了它会被丢弃。`,
          '删除确认', { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' })
      } catch (_) { return }
      try {
        const d = await req(`/api/taxonomy/items/${encodeURIComponent(row.name)}`, { method: 'DELETE' })
        ElementPlus.ElMessage.success(
          d.used_boxes ? `已删除（有 ${d.used_boxes} 个框在用它，导出时会被丢弃）` : '已删除')
        emit('changed')
      } catch (e) { ElementPlus.ElMessage.error(e.message) }
    }

    return { kw, items, categories, dialog, editing, form, saving, openAdd, openEdit, submit,
      remove, scenOptions, scenLabel }
  },
  template: `
  <el-card shadow="never">
    <template #header>
      <div style="display:flex;align-items:center;justify-content:space-between;gap:10px;flex-wrap:wrap">
        <span>必备物品清单（{{ (taxonomy.items||[]).length }} 项）<span style="color:#909399;font-weight:400;font-size:12px"> · 改这里立即生效</span></span>
        <span style="display:flex;gap:8px">
          <el-input v-model="kw" size="small" placeholder="搜索名称或别名" style="width:200px" clearable />
          <el-button size="small" type="primary" @click="openAdd">新增物品</el-button>
        </span>
      </div>
    </template>

    <el-alert
      type="info" :closable="false" show-icon style="margin-bottom:10px"
      title="这张表就是全链路唯一的数据源"
      description="改完立刻对「方框标注」下拉、AI 自动标注、训练导出生效。别名用来把各种叫法（收纳包/双肩包）归到同一个规范名。"
    />

    <el-table :data="items" size="small" border max-height="520">
      <el-table-column prop="name" label="规范名" width="120" />
      <el-table-column label="适用场景" width="150">
        <template #default="{row}">
          <el-tag v-for="s in (row.scenarios||[])" :key="s" size="small"
                  :type="s === 'school' ? 'warning' : 'primary'" class="chip">
            {{ scenLabel(s).split(' / ')[0] }}
          </el-tag>
          <span v-if="!(row.scenarios||[]).length" style="color:#c0c4cc;font-size:12px">通用</span>
        </template>
      </el-table-column>
      <el-table-column prop="category" label="类别" width="110" />
      <el-table-column prop="en" label="英文提示词" width="160" />
      <el-table-column label="别名（自动归类到规范名）">
        <template #default="{row}">
          <el-tag v-for="a in row.aliases" :key="a" size="small" class="chip">{{ a }}</el-tag>
          <span v-if="!(row.aliases||[]).length" style="color:#c0c4cc;font-size:12px">无</span>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="130" fixed="right">
        <template #default="{row}">
          <el-button size="small" text @click="openEdit(row)">编辑</el-button>
          <el-button size="small" text type="danger" @click="remove(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog v-model="dialog" :title="editing ? '编辑物品' : '新增物品'" width="520px">
      <el-form label-width="90px">
        <el-form-item label="规范名" required>
          <el-input v-model="form.name" placeholder="例如：充电器" maxlength="20" show-word-limit />
        </el-form-item>
        <el-form-item label="类别">
          <el-select v-model="form.category" filterable allow-create default-first-option style="width:100%">
            <el-option v-for="c in categories" :key="c" :label="c" :value="c" />
          </el-select>
        </el-form-item>
        <el-form-item label="适用场景">
          <el-checkbox-group v-model="form.scenarios">
            <el-checkbox v-for="o in scenOptions" :key="o.value" :value="o.value">
              {{ o.label }}
            </el-checkbox>
          </el-checkbox-group>
          <div style="font-size:12px;color:#909399;line-height:1.5">
            全选 = 两个场景都检查；只勾一个 = 只有那个场景才检查它。
          </div>
        </el-form-item>
        <el-form-item label="英文提示词">
          <el-input v-model="form.en" placeholder="给 GroundingDINO 用，例如：charger / power adapter" />
        </el-form-item>
        <el-form-item label="别名">
          <el-input v-model="form.aliasesText" type="textarea" :rows="3"
            placeholder="多个别名用「、」或逗号分隔，例如：充电线、数据线、电源适配器" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialog = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="submit">保存</el-button>
      </template>
    </el-dialog>
  </el-card>
  `,
}

/* ================= 根组件 ================= */
const App = {
  components: { DatasetPanel, AnnotatePanel, RecognizePanel, TaxonomyPanel },
  setup() {
    const active = ref('dataset')
    const images = ref([])
    const annotations = ref({})
    const canon = ref([])
    const taxonomy = ref({})
    const stats = ref({})
    const current = ref('')
    const scenarios = ref({ travel: '出门旅行 / 旅游', school: '上学 / 回家' })
    const imageScenarios = ref({})

    async function loadAll() {
      try {
        const d = await req('/api/images')
        images.value = d.images
        annotations.value = d.annotations || {}
        imageScenarios.value = d.image_scenarios || {}
        if (d.scenarios) scenarios.value = d.scenarios
        const c = await req('/api/canon')
        canon.value = c.canon
        taxonomy.value = await req('/api/taxonomy')
        stats.value = await req('/api/stats')
      } catch (e) {
        ElementPlus.ElMessage.error(e.message)
      }
    }
    const taxonItems = computed(() => taxonomy.value.items || [])
    function open(name) {
      current.value = name
      active.value = 'annotate'
    }
    onMounted(loadAll)
    return { active, images, annotations, canon, taxonomy, stats, current, open, loadAll,
      scenarios, imageScenarios, taxonItems }
  },
  template: `
  <div>
    <header class="app-header">
      <span>行李物品标注与识别平台 <span class="ver">v2.0</span></span>
      <span class="sub">Qwen2.5-VL · QLoRA · 独立于 lora-webui</span>
    </header>
    <main class="app-main">
      <el-tabs v-model="active">
        <el-tab-pane label="数据集（我的标注）" name="dataset">
          <DatasetPanel :images="images" :annotations="annotations" :stats="stats"
            :scenarios="scenarios" :image-scenarios="imageScenarios"
            :canon="canon" :taxon-items="taxonItems"
            @open="open" @changed="loadAll" />
        </el-tab-pane>
        <el-tab-pane label="方框标注" name="annotate" lazy>
          <AnnotatePanel :current="current" :canon="canon" :annotations="annotations"
            :scenarios="scenarios" :image-scenarios="imageScenarios" :taxon-items="taxonItems"
            @saved="loadAll" />
        </el-tab-pane>
        <el-tab-pane label="VLM 识别" name="recognize" lazy>
          <RecognizePanel :canon="canon" :scenarios="scenarios" :taxon-items="taxonItems" />
        </el-tab-pane>
        <el-tab-pane label="物品清单" name="taxonomy" lazy>
          <TaxonomyPanel :taxonomy="taxonomy" :scenarios="scenarios" @changed="loadAll" />
        </el-tab-pane>
      </el-tabs>
    </main>
  </div>
  `,
}

createApp(App).use(ElementPlus).mount('#app')
