# LISE front end estático

Configure esta pasta como Root Directory de um projeto Vercel com **Framework Preset: Other**, Build Command vazio e Output Directory `.`. `vercel.json` envia caminhos para `index.html` e aplica cabeçalhos de segurança. O site não precisa de Node nem de chave Supabase.

Depois de publicar o backend, edite `config.js` com a origem da API, sem `/api/v1` e sem barra no final, faça push e aguarde a nova publicação.

Localmente, configure a API como `http://127.0.0.1:5000`, rode `python app.py` dentro de `backend_service/` e, em outro terminal, `python -m http.server 5500` dentro desta pasta.
