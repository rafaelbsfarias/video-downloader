# Video Downloader Pessoal & Remoto

Este projeto é uma ferramenta pessoal para download de vídeos e playlists do YouTube, composta por uma **Extensão para Google Chrome** e um **Servidor Backend em Python/Flask** hospedado remotamente (VPS Orion via Tailscale).

A extensão captura a URL do vídeo/playlist atual no navegador, envia para o servidor backend processar com `yt-dlp` e, ao concluir, transfere o arquivo automaticamente para a máquina local com opção de escolher o diretório de destino (**Salvar Como**).

## 🚀 Funcionalidades

- **Download Remoto & Transferência Local:** O processamento pesado e downloads ocorrem no servidor VPS remoto (`orion` via Tailscale) e, ao finalizar, os arquivos são transferidos automaticamente para a máquina local via API do Chrome Downloads.
- **Opção "Salvar Como" na Máquina Local:** Checkbox na extensão permitindo escolher se o arquivo deve abrir o seletor nativo do sistema operacional para escolher a pasta de destino ou salvar direto no diretório padrão de downloads.
- **Suporte a Vídeos Individuais e Playlists:** Detecção automática de playlists com opção de baixar todos os itens sequencialmente com tratamento de falhas por item.
- **Formatos Suportados:**
  - **MP4:** Vídeo mesclado com áudio na melhor qualidade ou em resoluções selecionadas (1080p, 720p, 480p, 360p).
  - **MP3:** Conversão automática de áudio com capa embutida.
  - **Apenas Thumbnail (.jpg):** Extração da capa em alta resolução.
- **Bypass de Desafios BotGuard / PO Token:** Servidor configurado com `bgutil-ytdlp-pot-provider` e runtime `deno` para contornar restrições anti-bot do YouTube em faixas de IP de datacenter/cloud.
- **Observabilidade em Tempo Real:** Terminal de logs integrado na extensão via Server-Sent Events (SSE) para acompanhamento transparente do progresso e diagnósticos de erros.
- **Hardening de Segurança:** Servidor remoto com UFW fechando todas as portas públicas, acesso restrito exclusivamente à VPN Tailscale, SSH por chave pública e atualizações automáticas de segurança ativas.

## 📋 Arquitetura

```
[ Chrome Extension (Local) ]
       │
       │ HTTP / SSE (Tailscale: 100.98.54.48:5000)
       ▼
[ Servidor Backend Flask (VPS Orion) ]
  ├── yt-dlp + ffmpeg
  ├── bgutil-pot (Deno PO Token Provider na porta 4416)
  └── /downloads/ (Armazenamento temporário)
       │
       │ HTTP GET /files/<filename>
       ▼
[ Chrome Downloads API (Local) ] ──> [ Pasta Local Escolhida pelo Usuário ]
```

## 🔧 Configuração e Uso

### 1. Servidor Backend Remoto (`orion`)
O backend roda como serviço systemd no servidor `orion`:
- Serviço Flask: `sudo systemctl status video-downloader.service`
- Serviço PO Token: `sudo systemctl status bgutil-pot.service`
- Porta: `5000` (acessível exclusivamente pela interface `tailscale0`)

### 2. Extensão do Chrome

1. Abra o Google Chrome e acesse `chrome://extensions/`.
2. Ative o **Modo do desenvolvedor** no canto superior direito.
3. Se já instalada, clique no botão de recarregar (ícone de rotação 🔄) da extensão **Video Downloader Pessoal**.
   - Caso esteja instalando do zero, clique em **Carregar sem compactação** e selecione a pasta raiz deste repositório.
4. Navegue até um vídeo ou playlist do YouTube (ex: `youtube.com/watch?v=...`).
5. Clique no ícone da extensão na barra de ferramentas.
6. Configure as opções:
   - Formato (MP4, MP3, Thumbnail).
   - Qualidade desejada.
   - Marque ou desmarque **Escolher onde salvar na máquina local (Salvar Como)** conforme sua preferência.
7. Clique em **Baixar**.
8. O servidor processará o download e a extensão iniciará a transferência para sua máquina local.

## 📁 Estrutura do Projeto

- `server.py`: Servidor Flask com endpoints de controle, SSE `/progress` e download de arquivos `/files/<path:filename>`.
- `manifest.json`: Manifesto da extensão Chrome (v3) com permissões `downloads` e `storage`.
- `popup.html`: Interface com visualizador de thumbnail, seletor de formato, opção "Salvar Como" e terminal de logs.
- `popup.js`: Lógica de comunicação com o backend, eventos SSE e disparo do `chrome.downloads.download`.

## ⚖️ Licença

Este projeto é para fins educacionais e de uso pessoal.
