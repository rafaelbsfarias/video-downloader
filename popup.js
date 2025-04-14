document.getElementById("downloadBtn").addEventListener("click", async () => {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    const url = tab.url;
  
    if (!url.includes("youtube.com/watch")) {
      document.getElementById("status").innerText = "Não é uma página de vídeo.";
      return;
    }
  
    document.getElementById("status").innerText = "Enviando requisição...";
  
    fetch("http://localhost:5000/download", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url })
    })
      .then(res => res.json())
      .then(data => {
        if (data.status === "sucesso") {
          document.getElementById("status").innerText = "Download iniciado.";
        } else {
          document.getElementById("status").innerText = "Erro: " + data.error;
        }
      })
      .catch(err => {
        document.getElementById("status").innerText = "Falha na conexão com servidor.";
      });
  });
  