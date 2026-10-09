# LISE — front end e API separados

Projeto preparado para publicar a interface estática e a API Flask em **dois projetos da Vercel**, ligados ao mesmo repositório. O front não acessa o banco diretamente: autenticação, jogos, avaliações e dados passam pela API.

## Pastas para o deploy

| Pasta | Uso na Vercel |
|---|---|
| `frontend_spa/` | Site estático. Não requer Node, build ou chave do Supabase. |
| `backend_service/` | API Flask e função Python da Vercel. |
| `supabase/migrations/` | SQL aditivo para atualizar o banco LISE. Aplicar no SQL Editor do Supabase. |

## Funcionalidades desta versão

- Games separados das avaliações: Família de palavras, Memória, Decifrador e Flashcards. Montagem foi removido. Nenhum jogo permite praticar um termo isolado.
- Memória permite 6, 8 ou 10 pares, registra tentativas e mostra o tempo de jogo. Família de palavras oculta o radical até a resposta e separa acertos marcados, termos esquecidos e seleções incorretas.
- Professor configura uma avaliação para cada trilha atribuída à turma. O aluno só pode iniciar depois de praticar todos os termos da trilha; a trilha só fica concluída quando também é aprovado.
- Trilhas aceitam quantos termos cadastrados forem necessários, com busca/área, data limite, exclusão e remoção de uma turma.
- Professor vê por aluno o status agregado das trilhas daquela turma, XP diário, último acesso e notas. Ao abrir um aluno, os detalhes continuam limitados à turma selecionada. O aluno vê o ranking de XP da própria turma.
- Feed limitado às 15 atividades mais recentes e solicitado ao backend somente quando o aluno abre a turma.
- Aluno cria coleções e termos privados, favorita termos e radicais, e pratica por área, trilha atribuída, coleção ou favoritos.
- Explorador mostra termos, radicais ou ambos, com busca, área, ordem alfabética, termos relacionados e favoritos. A página de detalhes não oferece prática individual.
- Cadastro de professor exige um código de convite definido no backend. A aplicação não exibe conquistas.

## Publicar na Vercel

O processo usa o mesmo repositório para dois projetos. A Vercel permite configurar um Root Directory diferente em cada projeto e publicar os diretórios de um monorepo separadamente. A API Flask é executada como uma Vercel Function Python; o site estático não tem etapa de build. Consulte a documentação da [Vercel para monorepos](https://vercel.com/docs/monorepos) e para [Flask no runtime Python](https://vercel.com/docs/frameworks/backend/flask).

### 1. Envie o projeto ao GitHub

1. Baixe e descompacte o arquivo do projeto.
2. Envie o conteúdo da pasta do projeto para um repositório GitHub. A raiz do repositório precisa conter `frontend_spa/`, `backend_service/` e `supabase/`.
3. Não envie arquivo `.env` com credenciais. O pacote tem somente `.env.example`, com espaços para preencher.

### 2. Aplique as migrações do banco

No Supabase, confirme que está no projeto **LISE** e abra **SQL Editor**. Execute uma vez, nesta ordem:

1. `supabase/migrations/20260918171455_lise_flask_integrado.sql` somente se a base Flask ainda não foi instalada nesse projeto.
2. `supabase/migrations/20261002140000_lise_frontend_api.sql` se essa atualização ainda não foi aplicada.
3. `supabase/migrations/20261002160000_lise_assessments_and_deadlines.sql`.

A última migração adiciona prazos, progresso de termos praticados e tabelas de avaliações. Ela preserva os acertos registrados e converte partidas antigas respondidas em prática por termo, sem contar o antigo BioQuiz. Não apaga termos, radicais, contas, turmas ou trilhas existentes. O backend não cria tabelas automaticamente: aplique o SQL antes de usar as novas funções.

### 3. Publique o site estático primeiro

1. Na Vercel, selecione **Add New → Project** e importe o repositório.
2. Em **Root Directory**, escolha `frontend_spa`.
3. Em **Framework Preset**, escolha **Other**.
4. Deixe **Build Command** vazio e use `.` como **Output Directory**.
5. Publique. Copie a URL de produção, por exemplo `https://lise-web.vercel.app`.

O site pode mostrar uma mensagem pedindo o endereço da API até concluir o passo 5.

### 4. Publique a API separadamente

1. Crie outro projeto na Vercel e importe o mesmo repositório.
2. Em **Root Directory**, escolha `backend_service`.
3. Deixe a Vercel detectar Flask/Python. Não configure comando de inicialização Gunicorn. O `pyproject.toml` aponta para `vercel_app:app` e `vercel.json` configura a função.
4. Antes de publicar, abra **Settings → Environment Variables** e adicione as variáveis abaixo para **Production**. Se também usar previews, cadastre a origem exata do front em `FRONTEND_ORIGINS`, configure `FRONTEND_URL` para o front de preview no ambiente **Preview** e permita essa URL em Redirect URLs do Supabase.
5. Publique e copie a URL de produção da API, por exemplo `https://lise-api.vercel.app`.

| Variável na Vercel | Valor e onde obter |
|---|---|
| `DATABASE_URL` | No Supabase LISE, clique **Connect → Transaction pooler** e copie a connection string. Reaproveite a URL/senha já configurada no backend atual, se tiver. Se esqueceu a senha, abra **Project Settings → Database** e redefina a senha do banco; depois substitua o marcador na connection string. A porta de transaction é `6543`, adequada para funções curtas. Se a senha tiver `@`, `#`, `/` ou espaço, codifique esses caracteres na URL. [Documentação do Supabase sobre conexões](https://supabase.com/docs/guides/database/connecting-to-postgres). |
| `SUPABASE_URL` | Reaproveite a URL do projeto LISE. Encontre no painel **Connect** ou em **Project Settings → API Keys**. Ex.: `https://SEU-PROJETO.supabase.co`. |
| `SUPABASE_PUBLISHABLE_KEY` | Copie a chave `publishable` em **Settings → API Keys**. Uma chave `anon` antiga também funciona enquanto estiver habilitada. Não use `secret` nem `service_role`. [Tipos de chave do Supabase](https://supabase.com/docs/guides/api/api-keys). |
| `SECRET_KEY` | Reaproveite a chave do backend atual se tiver pelo menos 32 caracteres. Se não existir ou for menor, gere uma nova, diferente da chave Supabase, com `python -c "import secrets; print(secrets.token_urlsafe(48))"`. |
| `FRONTEND_URL` | A URL de produção copiada no passo 3, sem barra no final. |
| `FRONTEND_ORIGINS` | A mesma origem exata do site, sem barra no final. Ex.: `https://lise-web.vercel.app`. Se usar domínio próprio, adicione-o também. |
| `TEACHER_INVITE_CODE` | Crie um código privado para autorizar cadastro de professor. Compartilhe somente com professores autorizados. Sem essa variável, ninguém consegue cadastrar perfil de professor. |
| `DEMO_MODE` | Defina `false`. |

O código ajusta o pool local para uma conexão por instância, desativa prepared statements e exige SSL para funcionar com transaction pooler/serverless. Não coloque `DATABASE_URL`, `SECRET_KEY`, chave `secret` ou `service_role` no front end.

### 5. Ligue o front à API

1. Abra `frontend_spa/config.js` no repositório.
2. Troque o valor vazio por somente a origem pública da API, **sem `/api/v1` e sem `/` no final**:

   ```js
   window.LISE_CONFIG = {
     API_BASE_URL: "https://lise-api.vercel.app"
   };
   ```

3. Faça commit e push. A Vercel publica a atualização do projeto `frontend_spa`.

O navegador passa a chamar `https://lise-api.vercel.app/api/v1/...`. Esse endereço da API é público; nenhuma chave secreta deve ir nele.

### 6. Configure o Auth do Supabase

No Supabase LISE, abra **Authentication → URL Configuration**:

- **Site URL**: URL de produção do front, por exemplo `https://lise-web.vercel.app`.
- **Redirect URLs**: adicione `https://lise-web.vercel.app/**`. Para previews, adicione os endereços exatos que a Vercel mostrar; evite liberar genericamente todos os domínios `vercel.app`. Adicione `http://localhost:5500/**` somente se for testar localmente.
- Se usar recuperação de senha, abra **Authentication → Email Templates → Reset Password** e cole o HTML de `supabase/email_recuperacao.html`.

A URL do site e os redirects permitidos controlam para onde confirmação de e-mail e recuperação de senha retornam. [Configuração de URLs do Supabase Auth](https://supabase.com/docs/guides/auth/redirect-urls).

### 7. Confira a publicação

1. Abra `https://SUA-API.vercel.app/api/v1/healthz`. Deve retornar `{"status":"ok","service":"lise-api"}`.
2. Abra a URL do site e teste cadastro/login de aluno.
3. Cadastre um professor usando o valor de `TEACHER_INVITE_CODE` e crie uma turma.
4. Crie uma trilha, atribua uma data limite e configure uma avaliação.
5. Entre como aluno, pratique todos os termos da trilha, faça a avaliação e confirme o status/nota na conta do professor.
6. Confira a aba de ranking do aluno, os 15 itens do feed e a aba de resultados do professor.

## Testes locais

A interface estática pode ser servida sem build. Use Python 3.12; dentro de `backend_service/`, instale `requirements-dev.txt`, copie `.env.example` para `.env` e preencha os valores. Rode `python app.py` para iniciar a API local e `pytest` para os testes. Em outro terminal, dentro de `frontend_spa/`, rode `python -m http.server 5500`. Configure `frontend_spa/config.js` para apontar a `http://127.0.0.1:5000`.

## Desempenho e dados existentes

O front é servido pela CDN estática da Vercel e o backend escala como função separada; chamadas de turma agregam progresso por consulta agrupada para evitar uma consulta por aluno/trilha. O banco continua sendo o Supabase e a região da função deve ficar próxima da região do projeto LISE. A separação reduz trabalho na entrega das telas, mas a latência também depende da região e das consultas do banco.

As migrações não reescrevem definições científicas existentes. Termos curtos não são necessariamente incompletos, então não alterei conteúdo biológico sem validação de uma pessoa especialista.

## Segurança

- O navegador chama somente a API LISE; `DATABASE_URL`, `SECRET_KEY` e `TEACHER_INVITE_CODE` ficam nas variáveis do projeto backend da Vercel.
- A API verifica autenticação, papel de professor/aluno, vínculo com a turma e propriedade de trilhas e coleções antes de ler ou alterar esses dados.
- CORS fica limitado às origens informadas, o corpo das requisições tem limite e as respostas aplicam cabeçalhos de segurança. O cadastro de professor exige o código de convite do backend.
- A migração das avaliações ativa RLS e revoga acesso direto das chaves `anon`/`authenticated` às tabelas novas. O backend acessa o banco pelo pooler com a credencial de conexão guardada na Vercel.
- A interface não recebe chave `secret`, `service_role`, senha do banco ou segredo de assinatura. Não publique um `.env` no GitHub.
