document.getElementById("downloadBtn").addEventListener("click", async () => {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    const url = tab.url;
  
    if (!url.includes("youtube.com/watch")) {
      document.getElementById("status").innerText = "Não é uma página de vídeo.";
      return;
    }
  
    const format = document.getElementById("format").value;
    const quality = document.getElementById("quality").value;
  
    document.getElementById("status").innerText = "Enviando requisição...";
    document.getElementById("progressBar").value = 0;
  
    fetch("http://localhost:5000/download", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url, format, quality })
    })
      .then(res => res.json())
      .then(data => {
        if (data.status === "sucesso") {
          document.getElementById("status").innerText = "Download iniciado...";
  
          const eventSource = new EventSource("http://localhost:5000/progress");
  
          eventSource.onmessage = function (event) {
            try {
              const data = JSON.parse(event.data);
              const progress = Math.round(data.progress);
  
              document.getElementById("progressBar").value = progress;
              document.getElementById("status").innerText = `Progresso: ${progress}%`;
  
              if (progress >= 100) {
                eventSource.close();
                document.getElementById("status").innerText = "✅ Download concluído!";
              }
            } catch (e) {
              console.error("Erro ao processar evento:", e);
            }
          };
  
          eventSource.onerror = function () {
            eventSource.close();
            document.getElementById("status").innerText += "\n⚠️ Conexão encerrada.";
          };
  
        } else {
          document.getElementById("status").innerText = "Erro: " + data.error;
        }
      })
      .catch(err => {
        document.getElementById("status").innerText = "Erro na requisição: " + err.message;
      });
  });
  