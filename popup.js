const SERVER_URL = "http://100.98.54.48:5000";

const statusEl = document.getElementById("status");
const playlistInfoEl = document.getElementById("playlistInfo");
const progressBarEl = document.getElementById("progressBar");
const playlistContainer = document.getElementById("playlistOptionContainer");
const playlistToggle = document.getElementById("playlistToggle");
const saveThumbGroup = document.getElementById("saveThumbGroup");
const saveThumbToggle = document.getElementById("saveThumbToggle");
const saveAsToggle = document.getElementById("saveAsToggle");
const localFilesContainer = document.getElementById("localFilesContainer");
const formatSelect = document.getElementById("format");
const qualityGroup = document.getElementById("qualityGroup");
const downloadBtn = document.getElementById("downloadBtn");
const thumbContainer = document.getElementById("thumbContainer");
const thumbImg = document.getElementById("thumbImg");
const videoTitleEl = document.getElementById("videoTitle");
const logConsole = document.getElementById("logConsole");
const logDetails = document.getElementById("logDetails");

let currentTabUrl = "";

function deleteRemoteFile(filePath) {
  const encodedPath = filePath.split("/").map(encodeURIComponent).join("/");
  const fileNameOnly = filePath.split("/").pop() || filePath;
  fetch(`${SERVER_URL}/files/${encodedPath}`, { method: "DELETE" })
    .then(res => res.json())
    .then(data => {
      if (data.status === "sucesso") {
        appendLog(`🗑️ Limpeza: ${fileNameOnly} removido do servidor remoto.`);
      }
    })
    .catch(err => {
      console.warn("Erro ao remover do remoto:", err);
    });
}

function watchLocalDownloadAndCleanup(downloadId, filePath) {
  const fileNameOnly = filePath.split("/").pop() || filePath;
  const listener = function (delta) {
    if (delta.id === downloadId) {
      if (delta.state && delta.state.current === "complete") {
        chrome.downloads.onChanged.removeListener(listener);
        appendLog(`✅ Salvo na máquina local: ${fileNameOnly}`);
        deleteRemoteFile(filePath);
      } else if (delta.state && delta.state.current === "interrupted") {
        chrome.downloads.onChanged.removeListener(listener);
        appendLog(`⚠️ Download local interrompido: ${delta.error?.current || ""}`);
      }
    }
  };
  chrome.downloads.onChanged.addListener(listener);
}

function appendLog(text, timeStr) {
  if (!text) return;
  const line = document.createElement("div");
  const prefix = timeStr ? `[${timeStr}] ` : "";
  line.textContent = prefix + text;

  if (text.includes("❌") || text.includes("ERROR:")) {
    line.className = "log-err";
    logDetails.open = true;
  } else if (text.includes("⚠️") || text.includes("WARNING:")) {
    line.className = "log-warn";
  } else if (text.startsWith("$") || text.includes("🎬") || text.includes("📋") || text.includes("💾") || text.includes("📦") || text.includes("🗑️") || text.includes("✅")) {
    line.className = "log-info";
  }

  logConsole.appendChild(line);
  logConsole.scrollTop = logConsole.scrollHeight;
}

function extractVideoId(url) {
  try {
    const parsed = new URL(url);
    if (parsed.hostname.includes("youtube.com")) {
      if (parsed.pathname === "/watch") {
        return parsed.searchParams.get("v");
      }
      if (parsed.pathname.startsWith("/shorts/")) {
        return parsed.pathname.split("/shorts/")[1]?.split("/")[0];
      }
    }
  } catch (_) {}
  return null;
}

function showThumbnail(videoId, titleText) {
  if (!videoId) return;
  thumbImg.src = `https://i.ytimg.com/vi/${videoId}/hqdefault.jpg`;
  if (titleText) {
    videoTitleEl.innerText = titleText.replace(/\s*-\s*YouTube$/i, "");
  }
  thumbContainer.style.display = "block";
}

async function initPopup() {
  if (saveAsToggle) {
    const savedSaveAs = localStorage.getItem("saveAsPreference");
    if (savedSaveAs !== null) {
      saveAsToggle.checked = savedSaveAs === "true";
    }
    saveAsToggle.addEventListener("change", () => {
      localStorage.setItem("saveAsPreference", saveAsToggle.checked);
    });
  }

  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  currentTabUrl = tab?.url || "";
  const tabTitle = tab?.title || "";

  const isWatchPage = currentTabUrl.includes("youtube.com/watch") || currentTabUrl.includes("youtube.com/shorts/");
  const isPlaylistPage = currentTabUrl.includes("youtube.com/playlist");
  const hasListParam = currentTabUrl.includes("list=");

  if (!isWatchPage && !isPlaylistPage) {
    statusEl.innerText = "Abra um vídeo ou playlist do YouTube.";
    downloadBtn.disabled = true;
    return;
  }

  const videoId = extractVideoId(currentTabUrl);
  if (videoId) {
    showThumbnail(videoId, tabTitle);
  } else if (isPlaylistPage) {
    fetch(`${SERVER_URL}/info?url=${encodeURIComponent(currentTabUrl)}`)
      .then(res => res.json())
      .then(info => {
        if (info.thumbnail) {
          thumbImg.src = info.thumbnail;
          videoTitleEl.innerText = info.title || tabTitle.replace(/\s*-\s*YouTube$/i, "");
          thumbContainer.style.display = "block";
        }
      })
      .catch(() => {});
  }

  if (isPlaylistPage) {
    playlistContainer.style.display = "flex";
    playlistToggle.checked = true;
    playlistToggle.disabled = true;
  } else if (hasListParam) {
    playlistContainer.style.display = "flex";
    playlistToggle.checked = false;
    playlistToggle.disabled = false;
  } else {
    playlistContainer.style.display = "none";
    playlistToggle.checked = false;
  }

  updateUI();
}

function updateUI() {
  const format = formatSelect.value;
  const isOnlyThumb = format === "thumb";

  qualityGroup.style.display = format === "mp4" ? "block" : "none";
  saveThumbGroup.style.display = isOnlyThumb ? "none" : "flex";

  if (playlistToggle.checked) {
    downloadBtn.innerText = isOnlyThumb ? "Baixar thumbs da playlist" : "Baixar playlist completa";
  } else {
    downloadBtn.innerText = isOnlyThumb ? "Baixar thumbnail" : "Baixar vídeo atual";
  }
}

playlistToggle.addEventListener("change", updateUI);
formatSelect.addEventListener("change", updateUI);

downloadBtn.addEventListener("click", () => {
  const format = formatSelect.value;
  const quality = document.getElementById("quality").value;
  const isPlaylist = playlistToggle.checked;
  const saveThumb = saveThumbToggle.checked;

  statusEl.innerText = "Enviando requisição...";
  playlistInfoEl.style.display = "none";
  if (localFilesContainer) {
    localFilesContainer.innerHTML = "";
    localFilesContainer.style.display = "none";
  }
  progressBarEl.value = 0;
  logConsole.innerHTML = "";
  downloadBtn.disabled = true;

  fetch(`${SERVER_URL}/download`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      url: currentTabUrl,
      format,
      quality,
      playlist: isPlaylist,
      save_thumb: saveThumb
    })
  })
    .then(res => res.json())
    .then(data => {
      if (data.status === "sucesso") {
        statusEl.innerText = "Iniciando download no servidor...";

        const eventSource = new EventSource(`${SERVER_URL}/progress`);

        eventSource.onmessage = function (event) {
          try {
            const payload = JSON.parse(event.data);

            if (payload.log) {
              appendLog(payload.log, payload.timestamp);
            }

            if (payload.current_item && payload.total_items) {
              const failBadge = payload.failed_count ? ` (${payload.failed_count} falha)` : "";
              playlistInfoEl.style.display = "block";
              playlistInfoEl.innerText = `📋 Item ${payload.current_item} de ${payload.total_items}${failBadge}`;
            }

            if (payload.video_id) {
              showThumbnail(payload.video_id, payload.title || "");
            } else if (payload.title) {
              videoTitleEl.innerText = payload.title;
            }

            if (typeof payload.progress === "number") {
              const progress = Math.round(payload.progress);
              progressBarEl.value = progress;
              statusEl.innerText = payload.title
                ? `${payload.title}\nProgresso: ${progress}%`
                : `Progresso: ${progress}%`;
            }

            if (payload.error) {
              eventSource.close();
              downloadBtn.disabled = false;
              statusEl.innerText = `❌ Erro: ${payload.error}`;
              logDetails.open = true;
              return;
            }

            if (payload.done) {
              eventSource.close();
              downloadBtn.disabled = false;
              progressBarEl.value = 100;
              if (payload.partial_warning) {
                statusEl.innerText = `⚠️ ${payload.partial_warning}`;
                logDetails.open = true;
              } else {
                statusEl.innerText = "✅ Download concluído no servidor!";
              }

              if (payload.files && payload.files.length > 0) {
                const saveAs = saveAsToggle ? saveAsToggle.checked : true;
                appendLog(`📦 ${payload.files.length} arquivo(s) concluído(s). Iniciando transferência local...`);

                if (localFilesContainer) {
                  localFilesContainer.innerHTML = "<strong>Arquivos:</strong><br/>";
                  localFilesContainer.style.display = "block";
                }

                payload.files.forEach((filePath) => {
                  const encodedPath = filePath.split("/").map(encodeURIComponent).join("/");
                  const fileUrl = `${SERVER_URL}/files/${encodedPath}`;
                  const fileNameOnly = filePath.split("/").pop() || filePath;

                  if (localFilesContainer) {
                    const link = document.createElement("a");
                    link.href = fileUrl;
                    link.download = fileNameOnly;
                    link.textContent = `📥 ${fileNameOnly}`;
                    link.style.display = "block";
                    link.style.marginTop = "4px";
                    link.style.color = "#2563eb";
                    link.target = "_blank";
                    link.addEventListener("click", () => {
                      setTimeout(() => deleteRemoteFile(filePath), 10000);
                    });
                    localFilesContainer.appendChild(link);
                  }

                  if (chrome.downloads && chrome.downloads.download) {
                    chrome.downloads.download({
                      url: fileUrl,
                      filename: fileNameOnly,
                      saveAs: saveAs
                    }, (downloadId) => {
                      if (chrome.runtime.lastError) {
                        appendLog(`❌ Erro no download local (${fileNameOnly}): ${chrome.runtime.lastError.message}`);
                      } else {
                        appendLog(`💾 Salvando localmente: ${fileNameOnly} (ID: ${downloadId})`);
                        watchLocalDownloadAndCleanup(downloadId, filePath);
                      }
                    });
                  }
                });
              }
            }
          } catch (e) {
            console.error("Erro ao processar evento:", e);
          }
        };

        eventSource.onerror = function () {
          eventSource.close();
          downloadBtn.disabled = false;
          statusEl.innerText += "\n⚠️ Conexão de eventos encerrada.";
        };
      } else {
        downloadBtn.disabled = false;
        statusEl.innerText = "Erro: " + data.error;
      }
    })
    .catch(err => {
      downloadBtn.disabled = false;
      statusEl.innerText = "Erro na requisição: " + err.message;
    });
});

initPopup();
