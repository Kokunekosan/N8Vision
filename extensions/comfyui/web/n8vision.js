import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";

const N8VISION = "http://127.0.0.1:8189";
let activePromptId = null;

function historyImages(doc, promptId) {
  const entry = doc?.[promptId] || doc?.[String(promptId)] || null;
  const rows = [];
  for (const out of Object.values(entry?.outputs || {})) {
    for (const key of ["images", "gifs"]) {
      for (const x of (out?.[key] || [])) if (x?.filename) rows.push({filename:x.filename, subfolder:x.subfolder || "", type:x.type || "output"});
    }
  }
  return rows;
}

async function bellRecovery(recoveryId, promptId) {
  if (!promptId) { console.warn("[N8Vision] Bell rang without an active prompt:", recoveryId); return; }
  console.log("[N8Vision] Bellringer: bing!", recoveryId, "prompt", promptId);
  // Bellringer is upstream of the user's saver. Wait until Comfy history says downstream output nodes finished,
  // then use Comfy's own output descriptors rather than guessing a filesystem location.
  for (let attempt=0; attempt<40; attempt++) {
    try {
      const r = await api.fetchApi(`/history/${promptId}`);
      if (r.ok) {
        const doc = await r.json();
        const outputs = historyImages(doc, promptId);
        if (outputs.length) {
          await pingOutputReady({prompt_id:promptId, output:{images:outputs}});
          return;
        }
      }
    } catch (_) {}
    await new Promise(resolve => setTimeout(resolve, 250));
  }
  console.warn("[N8Vision] Bell rang, but Comfy history reported no saved image output:", recoveryId, promptId);
}

function outputImages(detail) {
  const out = detail?.output || {};
  const rows = [];
  for (const key of ["images", "gifs"]) {
    for (const x of (out[key] || [])) if (x?.filename) rows.push({filename:x.filename, subfolder:x.subfolder || "", type:x.type || "output"});
  }
  return rows;
}


async function pingTextStream(detail, final=false) {
  const promptId = detail?.prompt_id || detail?.promptId || null;
  const requestId = detail?.request_id || null;
  const text = detail?.text ?? "";
  try {
    await fetch(`${N8VISION}/api/comfy/text-stream`, {
      method:"POST", headers:{"Content-Type":"application/json"},
      body:JSON.stringify({environment_id:"comfyui", prompt_id:promptId, request_id:requestId, node_id:String(detail?.nodeId ?? detail?.node_id ?? ""), text, final})
    });
  } catch (err) { console.warn("[N8Vision] Text-stream bicycle lane failed:", err); }
}

async function pingOutputReady(detail) {
  const promptId = detail?.prompt_id;
  if (!promptId) return;
  try {
    const outputs=[];
    for (const out of outputImages(detail)) {
      try {
        const q=new URLSearchParams({filename:out.filename,subfolder:out.subfolder||"",type:out.type||"output"});
        const r=await fetch(`/n8vision/output-target?${q}`);
        const resolved=await r.json(); outputs.push({...out,target:resolved.target||null});
      } catch (_) { outputs.push(out); }
    }
    await fetch(`${N8VISION}/api/comfy/output-ready`, {
      method: "POST", headers: {"Content-Type":"application/json"},
      body: JSON.stringify({environment_id:"comfyui", prompt_id:promptId, outputs})
    });
  } catch (err) { console.warn("[N8Vision] Output-ready ping failed:", err); }
}

app.registerExtension({
  name: "N8Vision.Bridge",
  setup() {
    api.addEventListener("n8vision.load_workflow", async (event) => {
      const detail = event?.detail || {};
      if (!detail.workflow) return;
      try { await app.loadGraphData(detail.workflow); console.log("[N8Vision] Staged workflow on canvas (not queued):", detail.path || "<memory>"); }
      catch (err) { console.error("[N8Vision] Failed to stage workflow:", err); }
    });
    // Track Comfy's currently executing prompt so the graph-local Bellringer can correlate its intentionally tiny event.
    api.addEventListener("execution_start", (event) => { const d=event?.detail || {}; activePromptId=d.prompt_id || d.promptId || activePromptId; });
    api.addEventListener("execution_success", (event) => { const d=event?.detail || {}; const pid=d.prompt_id || d.promptId; if (pid && pid===activePromptId) activePromptId=null; });
    api.addEventListener("n8vision.bell", (event) => { const d=event?.detail || {}; bellRecovery(d.recovery_id || "", activePromptId); });
    // Native TextGenerate emits progress_text while decoding. Forward it unchanged; N8Vision filters to prompt IDs it owns.
    api.addEventListener("progress_text", (event) => { const d=event?.detail || {}; if (d.text) pingTextStream(d, false); });
    // The graph-local return node supplies the authoritative final STRING and request ID.
    api.addEventListener("n8vision.text_result", (event) => { const d=event?.detail || {}; pingTextStream(d, true); });
    // SaveImage emits an `executed` event containing its output assets. N8Vision only acts on prompt IDs it owns.
    api.addEventListener("executed", (event) => { const d=event?.detail || {}; if (outputImages(d).length) pingOutputReady(d); });
  },
});
