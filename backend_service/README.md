# LISE API na Vercel

Esta pasta contém a API Flask que será publicada como projeto independente da Vercel. Configure `backend_service` como Root Directory e mantenha `frontend_spa` em um segundo projeto estático no mesmo repositório.

## Variáveis de ambiente

Defina no painel da Vercel, em **Settings → Environment Variables**:

- `DATABASE_URL`: connection string do **Transaction Pooler** do Supabase LISE (porta 6543).
- `SUPABASE_URL`: URL do projeto LISE.
- `SUPABASE_PUBLISHABLE_KEY`: chave publishable atual ou `anon` legada que ainda esteja habilitada.
- `SECRET_KEY`: valor aleatório com pelo menos 32 caracteres.
- `FRONTEND_URL`: origem de produção do site estático, sem barra final.
- `FRONTEND_ORIGINS`: origens liberadas para CORS, separadas por vírgula.
- `TEACHER_INVITE_CODE`: código privado para permitir cadastro de perfil Professor.
- `DEMO_MODE=false`.

`DATABASE_URL`, `SECRET_KEY` e o código de convite devem permanecer somente no backend. Não há uso de `service_role`.

## Vercel

O arquivo `pyproject.toml` aponta o runtime para `vercel_app:app`. A função Python e o limite de execução estão em `vercel.json`; dependências estão em `requirements.txt`. O health check é `/api/v1/healthz`.

## Supabase

Execute as migrações na ordem descrita no README da raiz, no SQL Editor do projeto LISE. Para obter o endereço do banco, use **Connect → Transaction pooler**; para o Project URL e publishable key, use **Connect** ou **Settings → API Keys**. A conexão desativa prepared statements e mantém o pool da função em uma conexão.

## Local

Copie `.env.example` para `.env`, substitua os valores e rode `python app.py` nesta pasta. O `vercel_app.py` instancia a aplicação para o deploy; ele exige que as variáveis estejam configuradas.
