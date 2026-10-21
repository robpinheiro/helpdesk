# Helpdesk - Sistema de Gestão de Chamados

Sistema de helpdesk completo com integração LDAP (Samba 4 / Active Directory), desenvolvido em **Django 5** + **PostgreSQL** + **Redis** + **Celery**, pronto para deploy on-premises via **Docker Compose** + **Portainer**.

## 🚀 Funcionalidades

### Core
- ✅ **Autenticação SSO via LDAP/AD** (Samba 4 compatível)
- ✅ **Configuração LDAP 100% via Admin** (sem editar .env ou reiniciar)
- ✅ **Navegador de OUs/Grupos** no Admin (clique para selecionar)
- ✅ **Atributo de login configurável** (sAMAccountName, userPrincipalName, mail)
- ✅ **Sync automático de técnicos** (grupo AD → perfil Técnico no sistema)

### Tickets
- ✅ Criação rápida (modal HTMX)
- ✅ Lista com filtros (status, prioridade, técnico, data, busca)
- ✅ Detalhe com timeline, anexos, comentários
- ✅ Upload de fotos/comprovantes (drag-drop, preview, validação)
- ✅ Cronômetro de tempo gasto
- ✅ Histórico completo (django-simple-history)
- ✅ Permissões por papel (solicitante, técnico, admin)

### Configurações (Admin)
- ✅ **LDAP Configuration** (singleton) - servidor, bind, OU usuários, grupo técnicos, filtro, atributo login
- ✅ **Email Configuration** (singleton) - SMTP, TLS/SSL, teste de envio
- ✅ **Backup Configuration** (singleton) - agendamento, retenção, destino (local/NFS/S3)

### Relatórios & Automação
- ✅ Dashboard com KPIs e gráficos (Chart.js)
- ✅ Relatório de tickets com export CSV/Excel
- ✅ Relatórios agendados por e-mail (PDF/CSV/Excel)
- ✅ Backup automático agendado (pg_dump + media + static)
- ✅ Notificações por e-mail assíncronas (Celery)

### Técnico
- ✅ Docker Compose multi-container (web, celery, beat, postgres, redis, nginx)
- ✅ Nginx com SSL, rate limiting, security headers
- ✅ Health check endpoint
- ✅ Logs estruturados
- ✅ Scripts de backup/restore manuais

## 📋 Pré-requisitos

### Servidor (Produção)
- Docker 24+ / Docker Compose 2+
- Portainer (opcional, recomendado para gestão)
- 2 GB RAM mínimo (4 GB recomendado)
- 10 GB disco livre
- Acesso de rede ao Samba 4 / AD (porta 389 ou 636)
- Servidor SMTP para notificações (opcional)

### Desenvolvimento Local
- Python 3.12+
- PostgreSQL 16+ (ou SQLite para testes rápidos)
- Redis 7+

## 🏗️ Arquitetura

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   Nginx     │────▶│   Django    │────▶│ PostgreSQL  │
│  (SSL,      │     │  (Gunicorn) │     │  (Dados)    │
│  Static,    │     │  3 workers  │     └─────────────┘
│  Rate Limit)│     └──────┬──────┘            ▲
└─────────────┘            │                   │
                           ▼                   │
                    ┌─────────────┐     ┌─────────────┐
                    │   Redis     │────▶│   Celery    │
                    │ (Cache/Queue)│     │ (Workers)   │
                    └─────────────┘     └──────┬──────┘
                                               │
                    ┌─────────────┐            │
                    │  Samba 4 /  │◀───────────┘
                    │  Active Dir │   (LDAP Auth + Sync)
                    └─────────────┘
```

## 🚀 Deploy Rápido (Portainer)

### 1. Preparar servidor alvo
```bash
# Instala Docker + Portainer
curl -fsSL https://get.docker.com | bash
docker volume create portainer_data
docker run -d -p 9443:9443 --name portainer --restart=always \
  -v /var/run/docker.sock:/var/run/docker.sock \
  -v portainer_data:/data portainer/portainer-ce:latest

# Cria rede externa para nginx (se usar proxy externo)
docker network create helpdesk_external || true
```

### 2. No Portainer
1. Acesse `https://SEU_IP:9443`
2. **Stacks → Add stack**
   - Name: `helpdesk`
   - **Repository** → URL do seu Git (GitHub/GitLab/Gitea)  
     *Ou* **Web editor** → Cole o conteúdo do `docker-compose.yml`
3. **Environment variables** → Preencha conforme `.env.example`
4. **Deploy the stack**

### 3. Primeira configuração (via Admin Django)
1. Acesse `https://seu-dominio/admin/`
2. Login com seu usuário AD (precisa estar no grupo `helpdesk_superadmins`)
3. **Core → LDAP Configuration** → Preencha + **Testar Conexão** + **Navegar** para selecionar OU/Grupo
4. **Core → Email Configuration** → Preencha SMTP + **Enviar teste**
5. **Core → Backup Configuration** → Defina frequência/destino

## ⚙️ Variáveis de Ambiente (`.env`)

```bash
# Build
REGISTRY=                    # Deixe vazio para build local
TAG=latest

# Django
DEBUG=0
SECRET_KEY=gere-com: python -c "import secrets; print(secrets.token_urlsafe(50))"
ALLOWED_HOSTS=helpdesk.empresa.local,192.168.1.50
CSRF_TRUSTED_ORIGINS=https://helpdesk.empresa.local

# Database
DB_USER=helpdesk
DB_PASSWORD=senha_forte_aqui

# LDAP (valores iniciais; configure via Admin depois)
LDAP_URI=ldap://samba4.interno:389
LDAP_BIND_DN=cn=helpdesk,ou=services,dc=empresa,dc=local
LDAP_BIND_PASSWORD=senha_service_account

# Email (opcional no 1º deploy)
SMTP_HOST=smtp.empresa.local
SMTP_PORT=587
SMTP_USER=helpdesk@empresa.local
SMTP_PASSWORD=senha_smtp
SMTP_FROM=Helpdesk <helpdesk@empresa.local>
```

## 🔐 Grupos AD Necessários

Crie no seu Samba 4 / AD:

| Grupo | Finalidade | DN Exemplo |
|-------|------------|------------|
| `helpdesk_superadmins` | Superusuários Django (acesso total admin) | `cn=helpdesk_superadmins,ou=groups,dc=empresa,dc=local` |
| `helpdesk_admins` | Staff Django (acesso admin limitado) | `cn=helpdesk_admins,ou=groups,dc=empresa,dc=local` |
| `helpdesk_tecnicos` | Técnicos do helpdesk (atendem tickets) | `cn=helpdesk_tecnicos,ou=groups,dc=empresa,dc=local` |

> **Dica**: O grupo de técnicos é selecionável via navegador no Admin LDAP Configuration.

## 📁 Estrutura do Projeto

```
helpdesk/
├── config/                 # Settings Django
│   ├── settings/
│   │   ├── base.py
│   │   ├── development.py
│   │   └── production.py
│   ├── urls.py
│   └── wsgi.py
├── apps/
│   ├── core/               # Configurações (LDAP, Email, Backup) + Admin + Tasks
│   ├── accounts/           # User model customizado + LDAP Backend dinâmico
│   ├── tickets/            # Ticket, Anexo, Comentário + Views HTMX
│   └── reports/            # Relatórios agendados + Export
├── templates/
│   ├── base.html
│   ├── tickets/
│   ├── accounts/
│   ├── reports/
│   └── admin/core/ldapconfig/change_form.html  # Tree Browser LDAP
├── static/                 # CSS/JS (Tailwind via CDN)
├── media/                  # Uploads (gitignored)
├── nginx/
│   ├── nginx.conf
│   └── certs/              # Certificados SSL (não versionar)
├── scripts/
│   ├── backup.sh
│   └── restore.sh
├── requirements/
│   ├── base.txt
│   ├── production.txt
│   └── development.txt
├── docker-compose.yml
├── Dockerfile
├── .env.example
└── pyproject.toml
```

## 🛠️ Desenvolvimento Local

```bash
# Clone
git clone <repo> helpdesk
cd helpdesk

# Cria .env local
cp .env.example .env
# Edite .env com suas configurações locais

# Sobe apenas DB + Redis (opcional: use docker-compose para tudo)
docker compose up -d postgres redis

# Ambiente virtual
python -m venv .venv
source .venv/bin/activate  # Linux/Mac
# .venv\Scripts\activate   # Windows

# Dependências
pip install -r requirements/development.txt

# Migrações
python manage.py migrate

# Cria superuser local (fallback se LDAP falhar)
python manage.py createsuperuser

# Roda servidor
python manage.py runserver 0.0.0.0:8000
```

## 📦 Comandos Úteis

```bash
# Sync manual LDAP → Técnicos
docker compose exec web python manage.py sync_ldap_users

# Backup manual
sudo ./scripts/backup.sh /mnt/backups/helpdesk

# Restore manual
sudo ./scripts/restore.sh /mnt/backups/helpdesk/helpdesk_backup_20241219_020000

# Logs
docker compose logs -f web
docker compose logs -f celery

# Shell Django
docker compose exec web python manage.py shell

# Collectstatic
docker compose exec web python manage.py collectstatic --noinput
```

## 🔧 Personalização

### Adicionar campos ao Ticket
1. Edite `apps/tickets/models.py`
2. `python manage.py makemigrations tickets`
3. `python manage.py migrate`

### Alterar tema/cores
- Edite `tailwind.config` em `templates/base.html`
- Ou crie `static/css/custom.css` e inclua no base.html

### Novos relatórios agendados
1. Admin → Reports → Relatórios Agendados → Add
2. Configure filtros, frequência, destinatários, formato

## 🔒 Segurança

- ✅ Senhas LDAP/DB/SMTP apenas em `.env` (não versionado)
- ✅ Nginx com TLS 1.2+, HSTS, security headers
- ✅ Rate limiting (login, API, admin)
- ✅ CSRF, XSS, clickjacking protection
- ✅ Cookies Secure/HttpOnly/SameSite
- ✅ Usuário não-root no container
- ✅ Rede interna isolada (postgres/redis não expostos)

## 📄 Licença

MIT License - veja [LICENSE](LICENSE) para detalhes.

## 🤝 Contribuição

1. Fork o projeto
2. Crie branch (`git checkout -b feature/nova-funcionalidade`)
3. Commit (`git commit -am 'Add nova funcionalidade'`)
4. Push (`git push origin feature/nova-funcionalidade`)
5. Abra Pull Request

## 📞 Suporte

- Issues: GitHub Issues do repositório
- Documentação técnica: `docs/DEPLOY.md`
- Logs: `docker compose logs -f <serviço>`

---

**Desenvolvido para equipes de TI que precisam de um helpdesk robusto, integrado ao AD, e 100% gerenciável via interface web.**