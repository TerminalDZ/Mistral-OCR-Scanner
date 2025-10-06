// frontend/main.js
const pdfjsLib = window["pdfjs-dist/build/pdf"];
pdfjsLib.GlobalWorkerOptions.workerSrc =
  "https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.6.172/pdf.worker.min.js";

$(function () {
  // Defensive dropzone init
  Dropzone.autoDiscover = false;
  if (window.Dropzone && Array.isArray(window.Dropzone.instances)) {
    window.Dropzone.instances.forEach((i) => {
      try {
        i.destroy();
      } catch (e) {}
    });
    window.Dropzone.instances.length = 0;
  }

  let currentJob = null;
  let pollInterval = null;

  const dz = new Dropzone("#dzForm", {
    url: "/api/upload",
    paramName: "file",
    maxFilesize: 200,
    acceptedFiles: "application/pdf,image/*",
    autoProcessQueue: true,
    uploadMultiple: false,
    init: function () {
      this.on("sending", function (file, xhr, formData) {
        formData.append("do_qna", $("#doQna").is(":checked"));
        const schema = $("#annotationSchema").val().trim();
        if (schema) formData.append("annotation_schema", schema);
        $("#jobId").text("Uploading...");
      });
      this.on("success", function (file, res) {
        try {
          if (typeof res === "string") res = JSON.parse(res);
        } catch (e) {}
        if (res && res.job_id) {
          currentJob = res.job_id;
          $("#jobId").text(currentJob);
          loadHistory();
          startPolling(currentJob);
          Swal.fire({
            icon: "success",
            title: "Uploaded",
            text: "Job created",
          });
        } else {
          Swal.fire({
            icon: "error",
            title: "Upload failed",
            text: JSON.stringify(res),
          });
        }
      });
      this.on("error", function (file, err, xhr) {
        Swal.fire({
          icon: "error",
          title: "Upload error",
          text: xhr && xhr.responseText ? xhr.responseText : String(err),
        });
        $("#jobId").text("-");
      });
      this.on("addedfile", function (file) {
        renderPreview(file);
      });
    },
  });

  // preview
  function renderPreview(file) {
    const canvas = document.getElementById("pdfCanvas");
    const ctx = canvas.getContext("2d");
    const blob = file._file || file;
    if (!blob) return;
    if (blob.type === "application/pdf") {
      const reader = new FileReader();
      reader.onload = function () {
        const typed = new Uint8Array(this.result);
        pdfjsLib
          .getDocument({ data: typed })
          .promise.then((pdf) => pdf.getPage(1))
          .then((page) => {
            const viewport = page.getViewport({ scale: 1 });
            const scale = Math.min(
              1.3,
              (canvas.clientWidth || 600) / viewport.width
            );
            const sv = page.getViewport({ scale });
            canvas.width = Math.floor(sv.width);
            canvas.height = Math.floor(sv.height);
            page.render({ canvasContext: ctx, viewport: sv });
          })
          .catch((e) => console.warn("preview err", e));
      };
      reader.readAsArrayBuffer(blob);
    } else if (blob.type && blob.type.startsWith("image/")) {
      const reader = new FileReader();
      reader.onload = function () {
        const img = new Image();
        img.onload = function () {
          const maxW = 800;
          const w = Math.min(img.width, maxW);
          const h = img.height * (w / img.width);
          canvas.width = w;
          canvas.height = h;
          ctx.drawImage(img, 0, 0, w, h);
        };
        img.src = reader.result;
      };
      reader.readAsDataURL(blob);
    }
  }

  // polling
  function startPolling(jobId) {
    if (pollInterval) clearInterval(pollInterval);
    pollInterval = setInterval(async () => {
      try {
        const r = await fetch("/api/status/" + jobId);
        if (!r.ok) return;
        const j = await r.json();
        $("#jobId").text(j.job_id + " (" + j.status + ")");
        if (j.status === "completed" || j.status === "failed") {
          clearInterval(pollInterval);
          pollInterval = null;
          fetchResult(jobId);
          loadHistory();
        }
      } catch (e) {
        console.warn(e);
      }
    }, 2000);
  }

  // fetch result and render markdown
  async function fetchResult(jobId) {
    try {
      const r = await fetch("/api/result/" + jobId);
      if (!r.ok) {
        $("#ocrRendered").html(
          '<div class="text-sm text-red-500">Could not load result</div>'
        );
        return;
      }
      const txt = await r.text();
      let obj = null;
      try {
        obj = JSON.parse(txt);
      } catch (e) {
        obj = null;
      }
      if (obj) {
        const md =
          obj.full_markdown ||
          obj.qna_summary ||
          (obj.ocr &&
            obj.ocr.pages &&
            obj.ocr.pages[0] &&
            obj.ocr.pages[0].markdown) ||
          null;
        if (md) {
          const truncated =
            md.length > 300_000
              ? md.slice(0, 300_000) + "\n\n... (truncated)"
              : md;
          $("#ocrRendered").html(marked.parse(truncated));
        } else {
          $("#ocrRendered").html(
            '<div class="text-sm text-gray-500">No Markdown available for this document.</div>'
          );
        }
      } else {
        $("#ocrRendered").html(
          '<div class="text-sm text-gray-500">No result JSON.</div>'
        );
      }
    } catch (e) {
      console.warn(e);
      $("#ocrRendered").html(
        '<div class="text-sm text-red-500">Error loading result</div>'
      );
    }
  }

  $("#checkBtn").on("click", function () {
    const id = $("#jobId").text().split(" ")[0];
    if (!id || id === "-")
      return Swal.fire({ icon: "info", title: "No job selected" });
    fetchResult(id);
  });

  // download md/docx
  $("#downloadMdBtn").on("click", function () {
    const id = $("#jobId").text().split(" ")[0];
    if (!id || id === "-")
      return Swal.fire({ icon: "info", title: "No job selected" });
    window.location = "/api/download/" + id + "?format=md";
  });
  $("#downloadDocxBtn").on("click", function () {
    const id = $("#jobId").text().split(" ")[0];
    if (!id || id === "-")
      return Swal.fire({ icon: "info", title: "No job selected" });
    window.location = "/api/download/" + id + "?format=docx";
  });

  // ---- QnA: improved Markdown rendering ----
  function normalizeAnswer(ans) {
    // Try common Mistral response shapes and fallback to stringification
    try {
      if (!ans && ans !== 0) return "";
      if (typeof ans === "string") return ans;
      // Mistral Chat response: { choices: [ { message: { content: "..." } } ] }
      if (ans.choices && Array.isArray(ans.choices) && ans.choices.length) {
        const c = ans.choices[0];
        if (c.message && typeof c.message.content === "string")
          return c.message.content;
        if (c.message && Array.isArray(c.message.content))
          return c.message.content
            .map((x) => (typeof x === "string" ? x : JSON.stringify(x)))
            .join("\n\n");
      }
      // direct message shape: { message: { content: "..." } }
      if (ans.message && typeof ans.message.content === "string")
        return ans.message.content;
      if (Array.isArray(ans)) {
        // array of strings or objects
        return ans
          .map((it) =>
            typeof it === "string"
              ? it
              : it.message?.content || JSON.stringify(it)
          )
          .join("\n\n");
      }
      // object with 'answer' or 'text'
      if (ans.answer && typeof ans.answer === "string") return ans.answer;
      if (ans.text && typeof ans.text === "string") return ans.text;
      // fallback stringify
      return JSON.stringify(ans, null, 2);
    } catch (e) {
      return String(ans);
    }
  }

  function renderQnAAsMarkdown(answerObj) {
    const raw = normalizeAnswer(answerObj);
    // If string contains escaped newlines, unescape them
    const md = raw.replace(/\\n/g, "\n");
    // Render with marked and wrap into styled container
    const html = marked.parse(md);
    const wrapper = `
      <div class="markdown-body p-3 bg-white rounded border">
        ${html}
      </div>
    `;
    $("#qnaAnswer").html(wrapper);
    // optional: scroll into view
    $("#qnaAnswer")[0].scrollIntoView({ behavior: "smooth", block: "center" });
  }

  // QnA ask
  $("#askBtn").on("click", async function () {
    const id = $("#jobId").text().split(" ")[0];
    const q = $("#qnaQuestion").val().trim();
    if (!id || id === "-")
      return Swal.fire({ icon: "info", title: "No job selected" });
    if (!q) return Swal.fire({ icon: "info", title: "Enter a question" });
    try {
      // show spinner/message
      $("#qnaAnswer").html(
        '<div class="text-sm text-gray-500">Processing question…</div>'
      );
      const resp = await fetch("/api/qna", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ job_id: id, question: q }),
      });
      if (!resp.ok) {
        const t = await resp.text();
        $("#qnaAnswer").html(
          '<div class="text-sm text-red-500">QnA failed: ' +
            escapeHtml(t) +
            "</div>"
        );
        return Swal.fire({ icon: "error", title: "QnA failed", text: t });
      }
      const j = await resp.json();
      // render markdown answer nicely
      renderQnAAsMarkdown(j.answer);
      // re-load result to reflect qna_history
      fetchResult(id);
      loadHistory();
    } catch (e) {
      Swal.fire({ icon: "error", title: "Network error", text: e.message });
      $("#qnaAnswer").html(
        '<div class="text-sm text-red-500">Network error: ' +
          escapeHtml(e.message) +
          "</div>"
      );
    }
  });

  // history
  async function loadHistory() {
    try {
      const resp = await fetch("/api/jobs");
      if (!resp.ok) return;
      const data = await resp.json();
      const rows = data.jobs || [];
      const $h = $("#history");
      $h.empty();
      if (rows.length === 0) {
        $h.text("No jobs yet");
        return;
      }
      rows.slice(0, 50).forEach((r) => {
        const title = r.title || r.filename || "(untitled)";
        const status = r.status || "pending";
        const created = r.created_at
          ? new Date(r.created_at).toLocaleString()
          : "";
        const el = $(`
          <div class="border-b py-2">
            <div class="flex justify-between items-start gap-2">
              <div>
                <div class="font-semibold text-sm">${escapeHtml(title)}</div>
                <div class="text-xs text-gray-500">${escapeHtml(
                  r.filename || ""
                )}</div>
              </div>
              <div class="text-right">
                <div class="text-xs">${escapeHtml(status)}</div>
                <div class="text-xs text-gray-400">${created}</div>
                <div class="mt-1 flex gap-1 justify-end">
                  <button class="viewBtn px-2 py-1 text-xs border rounded" data-id="${
                    r.job_id
                  }">View</button>
                  <a class="px-2 py-1 text-xs text-indigo-600" href="/api/result/${
                    r.job_id
                  }" target="_blank">Raw</a>
                </div>
              </div>
            </div>
          </div>
        `);
        $h.append(el);
      });
      // bind view buttons
      $(".viewBtn")
        .off("click")
        .on("click", function () {
          const id = $(this).data("id");
          $("#jobId").text(id);
          fetchResult(id);
        });
    } catch (e) {
      console.warn("history err", e);
    }
  }

  function escapeHtml(s) {
    return String(s || "").replace(/[&<>"']/g, function (m) {
      return {
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        '"': "&quot;",
        "'": "&#39;",
      }[m];
    });
  }

  // initial
  loadHistory();
});
