# Guia de Instalação Completa — Helpdesk

> **Versão:** 1.0  
> **Requisitos:** Docker 24+, Docker Compose 2+, Git  
> **Tempo estimado:** 15-30 min

---

## 📋 Pré-requisitos no Servidor

| Item | Mínimo | Recomendado |
|------|--------|-------------|
| **SO** | Ubuntu 22.04 / Debian 12 / Windows Server 2022 | Ubuntu 24.04 LTS |
| **CPU** | 2 vCPUs | 4 vCPUs |
| **RAM** | 2 GB | 4 GB |
| **Disco** | 10 GB livres | 20 GB SSD |
| **Rede** | Porta 389/636 (LDAP) + 80/443 (Web) | Idem |
| **Docker** | 24+ | 26+ |
| **Portainer** | Opcional | ✅ Recomendado |

---

## 🔧 Passo 1 — Preparar o Servidor

### Linux (Ubuntu/Debian)
```bash
# Atualiza sistema
sudo apt update && sudo apt upgrade -y

# Instala Docker
curl -fsSL https://get.docker.com | bash
sudo usermod -aG docker $USER
newgrp docker

# Instala Portainer (gestão visual)
docker volume create portainer_data
docker run -d -p 9443:9443 --name portainer --restart=always \
  -v /var/run/docker.sock:/var/run/docker.sock \
  -v portainer_data:/data portainer/portainer-ce:latest

# Verifica
docker ps | grep portainer
```

### Windows Server
```powershell
# Instala Docker Desktop ou Docker Engine
# Baixe: https://desktop.docker.com/win/main/amd64/Docker%20Desktop%20Installer.exe

# Portainer
docker volume create portainer_data
docker run -d -p 9443:9443 --name portainer --restart=always `
  -v /var/run/docker.sock:/var/run/docker.sock `
  -v portainer_data:/data portainer/portainer-ce:latest
```

> **Acesse Portainer:** `https://IP_DO_SERVIDOR:9443` → crie usuário admin

---

## 🔐 Passo 2 — Certificados SSL

### Opção A: Let's Encrypt (domínio público) — RECOMENDADO
```bash
sudo apt install certbot -y
sudo certbot certonly --standalone -d helpdesk.seudominio.com

# Copia para pasta do projeto
sudo mkdir -p /opt/helpdesk/nginx/certs
sudo cp /etc/letsencrypt/live/helpdesk.seudominio.com/fullchain.pem /opt/helpdesk/nginx/certs/
sudo cp /etc/letsencrypt/live/helpdesk.seudominio.com/privkey.pem /opt/helpdesk/nginx/certs/
sudo chown -R $USER:$USER /opt/helpdesk/nginx/certs
```

### Opção B: Certificado da empresa (CA interna)
```bash
# Coloque seus arquivos em:
# /opt/helpdesk/nginx/certs/fullchain.pem
# /opt/helpdesk/nginx/certs/privkey.pem
```

### Opção C: Auto-assinado (apenas testes)
```bash
mkdir -p nginx/certs
openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
  -keyout nginx/certs/privkey.pem \
  -out nginx/certs/fullchain.pem \
  -subj "/CN=helpdesk.local"
```

---

## 📥 Passo 3 — Baixar o Projeto

### Via Git (recomendado)
```bash
cd /opt
git clone https://github.com/robpinheiro/helpdesk.git
cd helpdesk
```

### Via Portainer (Stack from Repository)
No Portainer: **Stacks → Add stack → Repository** → URL do Git → `docker-compose.yml`

---

## ⚙️ Passo 4 — Configurar Variáveis de Ambiente

```bash
cp .env.example .env
nano .env
```

### **Obrigatórios** (preencha agora):
```bash
# Segurança
SECRET_KEY=gere_com: python3 -c "import secrets; print(secrets.token_urlsafe(50))"
ALLOWED_HOSTS=helpdesk.seudominio.com,192.168.1.50
CSRF_TRUSTED_ORIGINS=https://helpdesk.seudominio.com

# Banco
DB_PASSWORD=senha_forte_postgres_aqui

# LDAP (valores iniciais - configure via Admin depois)
LDAP_URI=ldap://IP_DO_SAMBA4:389
LDAP_BIND_DN=cn=helpdesk,ou=services,dc=empresa,dc=local
LDAP_BIND_PASSWORD=senha_do_service_account
```

### **Opcionais** (configure depois no Admin):
```bash
# Email (configure via Admin → Core → Email Configuration)
# SMTP_HOST=smtp.empresa.local
# SMTP_PORT=587
# SMTP_USER=helpdesk@empresa.local
# SMTP_PASSWORD=senha_smtp
# SMTP_FROM=Helpdesk <helpdesk@empresa.local>
```

---

## 🐳 Passo 5 — Subir a Stack

### Via Portainer (mais fácil)
1. **Stacks → Add stack**
2. Name: `helpdesk`
3. **Repository** → URL do Git (ex: `https://github.com/robpinheiro/helpdesk.git`)
4. Compose path: `docker-compose.yml`
5. **Environment variables** → o Portainer lê o `.env` automaticamente
6. **Deploy the stack**

### Via linha de comando
```bash
docker compose -p helpdesk build --no-cache
docker compose -p helpdesk up -d
```

---

## ✅ Passo 6 — Verificar Saúde

```bash
# Status dos containers
docker ps --filter "name=helpdesk" --format "table {{.Names}}\t{{.Status}}"

# Logs da aplicação
docker logs -f helpdesk-web-1

# Health check
curl -k https://helpdesk.seudominio.com/health/
# Deve retornar: {"status":"healthy","checks":{"database":"ok","cache":"ok","redis":"ok"}}
```

---

## 🔐 Passo 7 — Configuração Inicial (via Admin Django)

### 7.1 Acesse o Admin
- URL: `https://helpdesk.seudominio.com/admin/`
- Login: Use seu usuário do **Active Directory** (precisa estar no grupo `helpdesk_superadmins`)

### 7.2 Configure LDAP (Core → LDAP Configuration)
| Campo | Valor | Como preencher |
|-------|-------|----------------|
| URI do Servidor | `ldap://samba4.interno:389` | Digite |
| DN de Bind | `cn=helpdesk,ou=services,dc=empresa,dc=local` | Digite |
| Senha do Bind | `••••••••` | Digite |
| Base DN dos Usuários | *(clique **Navegar OUs**)* | Selecione a OU |
| Atributo de Login | `sAMAccountName` | Selecione |
| DN do Grupo de Técnicos | *(clique **Navegar Grupos**)* | Selecione o grupo `helpdesk_tecnicos` |

→ **Testar Conexão** → deve mostrar usuários encontrados  
→ **Salvar**

### 7.3 Configure Email (Core → Email Configuration)
1. Preencha SMTP da empresa
2. **E-mail para Teste**: `seu@email.com`
3. **Salvar** → deve enviar e-mail de teste
4. Marque **Ativo** → Salvar

### 7.4 Configure Backup (Core → Backup Configuration)
| Campo | Valor sugerido |
|-------|----------------|
| Frequência | Diário |
| Horário | 02:00 |
| Retenção | 30 dias |
| Destino | Local (`/backups`) ou NFS (`/mnt/backups`) |
| Caminho | `/backups` |

→ Marque **Backup Ativo** → Salvar  
→ **Actions → Executar backup agora** (teste)

---

## 👥 Passo 8 — Grupos no Active Directory (Samba 4)

Crie no AD **antes** de configurar o LDAP:

| Grupo | Finalidade | Exemplo DN |
|-------|------------|------------|
| `helpdesk_superadmins` | Superusuários Django (acesso total) | `cn=helpdesk_superadmins,ou=groups,dc=empresa,dc=local` |
| `helpdesk_admins` | Staff Django (acesso admin limitado) | `cn=helpdesk_admins,ou=groups,dc=empresa,dc=local` |
| `helpdesk_tecnicos` | Técnicos que atendem tickets | `cn=helpdesk_tecnicos,ou=groups,dc=empresa,dc=local` |

> Adicione seu usuário no `helpdesk_superadmins` para acessar o Admin.

---

## 🔄 Passo 9 — Sincronizar Técnicos

```bash
# Via Docker
docker compose -p helpdesk exec web python manage.py sync_ldap_users

# Verifica no Admin: Accounts → Técnicos
```

---

## 🛡️ Passo 10 — Segurança Pós-Deploy

### Firewall (Linux)
```bash
sudo ufw allow 22/tcp    # SSH
sudo ufw allow 80/tcp    # HTTP → HTTPS redirect
sudo ufw allow 443/tcp   # HTTPS
sudo ufw allow 9443/tcp  # Portainer (restrinja IP: `sudo ufw allow from 192.168.1.0/24 to any port 9443`)
sudo ufw enable
```

### Fail2Ban (opcional)
```bash
sudo apt install fail2ban -y
# Configure jail para nginx/auth
```

### Atualizações automáticas
```bash
sudo apt install unattended-upgrades -y
sudo dpkg-reconfigure unattended-upgrades
```

---

## 🔍 Checklist Final

- [ ] Servidor com Docker + Portainer
- [ ] Certificados SSL em `nginx/certs/`
- [ ] Stack deployada no Portainer
- [ ] `.env` preenchido com segredos reais
- [ ] LDAP configurado e testado no Admin
- [ ] Grupo de técnicos sincronizado (Admin → Accounts → Técnicos)
- [ ] Email SMTP configurado e testado
- [ ] Backup configurado e testado (restore em staging)
- [ ] Firewall configurado
- [ ] Health check respondendo OK
- [ ] Documentação de credenciais guardada (KeePass, Bitwarden)

---

## 🆘 Troubleshooting Rápido

| Problema | Solução |
|----------|---------|
| Container web não sobe | `docker logs helpdesk-web-1` → verifica SECRET_KEY, DB_PASSWORD, migrações |
| Erro LDAP | Teste manual: `docker compose exec web python -c "import ldap3; ..."` |
| Email não envia | Teste SMTP: `docker compose exec web python -c "import smtplib; ..."` |
| Backup falha | Verifica `pg_dump` no container postgres + permissões pasta backup |
| Porta 80/443 ocupada | `sudo lsof -i :80` → para serviço conflitante |

---

## 📞 Suporte

- **Logs:** `docker compose -p helpdesk logs -f <serviço>`
- **Shell Django:** `docker compose -p helpdesk exec web python manage.py shell`
- **Migrações:** `docker compose -p helpdesk exec web python manage.py migrate`
- **Collectstatic:** `docker compose -p helpdesk exec web python manage.py collectstatic --noinput`

---

**Pronto!** Seu Helpdesk está no ar em `https://helpdesk.seudominio.com` 🎉