# Guia de Deploy - Helpdesk On-Premises

Este guia detalha o processo completo de deploy em servidor on-premises usando Docker Compose + Portainer.

---

## 1. Preparação do Servidor

### Requisitos Mínimos
- **OS**: Ubuntu 22.04+ / Debian 12+ / RHEL 9+ / Windows Server 2022+ (com WSL2)
- **CPU**: 2 vCPUs
- **RAM**: 4 GB (2 GB absoluto mínimo)
- **Disco**: 20 GB livres (SSD recomendado)
- **Rede**: Acesso à porta 389/636 do Samba 4 / AD
- **Portas**: 80, 443 (HTTP/HTTPS), 9443 (Portainer)

### Instalação Docker + Portainer
```bash
# Atualiza sistema
sudo apt update && sudo apt upgrade -y

# Instala Docker
curl -fsSL https://get.docker.com | bash
sudo usermod -aG docker $USER
newgrp docker  # ou logout/login

# Instala Portainer
docker volume create portainer_data
docker run -d \
  -p 9443:9443 \
  --name portainer \
  --restart=always \
  -v /var/run/docker.sock:/var/run/docker.sock \
  -v portainer_data:/data \
  portainer/portainer-ce:latest

# Verifica
docker ps | grep portainer
```

Acesse `https://IP_SERVIDOR:9443` e configure admin do Portainer.

---

## 2. Certificados SSL

### Opção A: Let's Encrypt (Recomendado para domínio público)
```bash
# Instala certbot
sudo apt install certbot -y

# Gera certificado (modo standalone - para porta 80 livre)
sudo certbot certonly --standalone -d helpdesk.seudominio.com

# Copia para pasta do nginx
sudo mkdir -p /opt/helpdesk/nginx/certs
sudo cp /etc/letsencrypt/live/helpdesk.seudominio.com/fullchain.pem /opt/helpdesk/nginx/certs/
sudo cp /etc/letsencrypt/live/helpdesk.seudominio.com/privkey.pem /opt/helpdesk/nginx/certs/
sudo chown -R $USER:$USER /opt/helpdesk/nginx/certs
```

### Opção B: Certificado Interno (CA da empresa)
```bash
# Coloque seus arquivos em:
# /opt/helpdesk/nginx/certs/fullchain.pem
# /opt/helpdesk/nginx/certs/privkey.pem
```

### Opção C: Auto-assinado (Apenas testes)
```bash
mkdir -p nginx/certs
openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
  -keyout nginx/certs/privkey.pem \
  -out nginx/certs/fullchain.pem \
  -subj "/CN=helpdesk.local"
```

---

## 3. Deploy via Portainer

### 3.1 Clone o repositório no servidor (ou use Git no Portainer)
```bash
cd /opt
git clone https://github.com/seu-usuario/helpdesk.git
cd helpdesk
```

### 3.2 Crie arquivo `.env`
```bash
cp .env.example .env
# Edite com suas configurações
nano .env
```

**Mínimo obrigatório no `.env`:**
```bash
SECRET_KEY=gere_com_python_c_secrets_token_urlsafe_50
DB_PASSWORD=senha_forte_postgres
ALLOWED_HOSTS=helpdesk.seudominio.com,IP_SERVIDOR
CSRF_TRUSTED_ORIGINS=https://helpdesk.seudominio.com

LDAP_URI=ldap://IP_SAMBA4:389
LDAP_BIND_DN=cn=helpdesk,ou=services,dc=empresa,dc=local
LDAP_BIND_PASSWORD=senha_service_account
```

### 3.3 No Portainer
1. **Stacks → Add stack**
2. Name: `helpdesk`
3. **Build method**: Repository
   - Repository URL: `https://github.com/seu-usuario/helpdesk.git` (ou path local `/opt/helpdesk`)
   - Compose path: `docker-compose.yml`
4. **Environment variables**: O Portainer lê o `.env` automaticamente se estiver no mesmo diretório
5. **Deploy the stack**

### 3.4 Aguarde build e saúde dos containers
```bash
# Acompanhe logs
docker logs -f helpdesk-web-1
# Deve aparecer: "Starting gunicorn..." e health check passing
```

---

## 4. Configuração Inicial (Pós-Deploy)

### 4.1 Acesse o Admin
- URL: `https://helpdesk.seudominio.com/admin/`
- Login: Use seu usuário do AD (precisa estar no grupo `helpdesk_superadmins`)

### 4.2 Configure LDAP (Core → LDAP Configuration)
1. Preencha:
   - **URI do Servidor**: `ldap://samba4.interno:389` (ou `ldaps://...:636`)
   - **DN de Bind**: `cn=helpdesk,ou=services,dc=empresa,dc=local`
   - **Senha do Bind**: [senha do service account]
2. **Base DN dos Usuários**: Clique em **Navegar OUs** → selecione a OU onde estão os usuários
3. **Atributo de Login**: `sAMAccountName` (padrão AD)
4. **DN do Grupo de Técnicos**: Clique em **Navegar Grupos** → selecione o grupo `helpdesk_tecnicos`
5. Clique em **Testar Conexão** → deve mostrar usuários encontrados
6. **Salvar**

### 4.3 Configure Email (Core → Email Configuration)
1. Preencha SMTP da empresa
2. **E-mail para Teste**: seu@email.com
3. Clique **Salvar** → deve enviar e-mail de teste
4. Marque **Ativo** → Salvar

### 4.4 Configure Backup (Core → Backup Configuration)
1. **Frequência**: Diário / Semanal / Mensal
2. **Horário**: Ex: 02:00 (madrugada)
3. **Retenção**: 30 dias
4. **Destino**: Local (`/backups`) ou NFS (`/mnt/backups`) ou S3
5. **Caminho**: `/backups` (certifique-se que o volume existe)
6. Marque **Backup Ativo** → Salvar
7. Teste: **Actions → Executar backup agora**

---

## 5. Volumes Persistentes

Os dados ficam em volumes Docker nomeados:
```bash
docker volume ls | grep helpdesk
# helpdesk_postgres_data
# helpdesk_redis_data
# helpdesk_media_files
# helpdesk_static_files
```

### Backup dos volumes (manual)
```bash
# Para backup completo dos volumes
docker run --rm -v helpdesk_postgres_data:/data -v $(pwd):/backup alpine tar czf /backup/pg_data.tar.gz -C /data .
```

---

## 6. Atualização (Update)

### Via Portainer (GitOps)
1. Faça push das mudanças para o Git
2. No Portainer: **Stacks → helpdesk → Update the stack**
3. Marca **Re-pull image** e **Force update**
4. Deploy

### Via linha de comando
```bash
cd /opt/helpdesk
git pull
docker compose -p helpdesk build --no-cache
docker compose -p helpdesk up -d --force-recreate
docker compose -p helpdesk exec web python manage.py migrate
docker compose -p helpdesk exec web python manage.py collectstatic --noinput
```

---

## 7. Monitoramento e Logs

### Logs em tempo real
```bash
# Todos os serviços
docker compose -p helpdesk logs -f

# Apenas web
docker logs -f helpdesk-web-1

# Celery
docker logs -f helpdesk-celery-1
```

### Health Checks
```bash
# Verifica saúde dos containers
docker ps --filter "name=helpdesk" --format "table {{.Names}}\t{{.Status}}"

# Testa endpoint health
curl -k https://helpdesk.seudominio.com/health/
# Deve retornar: {"status":"healthy","checks":{"database":"ok","cache":"ok","redis":"ok"}}
```

### Métricas básicas
```bash
# Uso de recursos
docker stats --no-stream helpdesk-web-1 helpdesk-celery-1 helpdesk-postgres-1 helpdesk-redis-1

# Espaço em disco
df -h /var/lib/docker/volumes/helpdesk_*
```

---

## 8. Troubleshooting Comum

### Container web não sobe (CrashLoopBackOff)
```bash
docker logs helpdesk-web-1
# Verifica: SECRET_KEY, DB_PASSWORD, ALLOWED_HOSTS, migrações pendentes
docker compose -p helpdesk exec web python manage.py migrate
```

### Erro de conexão LDAP
```bash
# Teste manual
docker compose -p helpdesk exec web python -c "
import ldap3
server = ldap3.Server('ldap://samba4.interno:389')
conn = ldap3.Connection(server, user='cn=helpdesk,ou=services,dc=empresa,dc=local', password='senha')
print('Bind:', conn.bind())
conn.search('ou=users,dc=empresa,dc=local', '(sAMAccountName=*)', ldap3.SUBTREE, attributes=['cn'])
print('Users:', len(conn.entries))
"
```

### Email não envia
```bash
# Teste SMTP manual
docker compose -p helpdesk exec web python -c "
import smtplib
s = smtplib.SMTP('smtp.empresa.local', 587)
s.starttls()
s.login('user', 'pass')
s.sendmail('from@test.com', 'to@test.com', 'Subject: Teste\n\nBody')
print('OK')
s.quit()
"
```

### Backup falha
```bash
# Verifica se pg_dump existe no container postgres
docker exec helpdesk-postgres-1 which pg_dump

# Verifica permissões do diretório de backup
ls -la /mnt/backups/
# Deve ser writable pelo usuário do container (root no script)
```

---

## 9. Segurança Pós-Deploy

### Firewall (UFW)
```bash
sudo ufw allow 22/tcp    # SSH
sudo ufw allow 80/tcp    # HTTP (redirect)
sudo ufw allow 443/tcp   # HTTPS
sudo ufw allow 9443/tcp  # Portainer (restrinja IP se possível)
sudo ufw enable
```

### Fail2Ban (opcional)
```bash
sudo apt install fail2ban -y
# Configure jail para nginx/auth
```

### Atualizações automáticas de segurança
```bash
sudo apt install unattended-upgrades -y
sudo dpkg-reconfigure unattended-upgrades
```

---

## 10. Checklist de Entrega

- [ ] Servidor provisionado com Docker + Portainer
- [ ] Certificados SSL instalados em `nginx/certs/`
- [ ] Stack deployada no Portainer
- [ ] `.env` preenchido com segredos reais
- [ ] LDAP configurado e testado no Admin
- [ ] Grupo de técnicos sincronizado (verifique em Admin → Accounts → Técnicos)
- [ ] Email SMTP configurado e testado
- [ ] Backup configurado e testado (restore testado em ambiente de staging)
- [ ] Firewall configurado
- [ ] Monitoramento básico (health check respondendo)
- [ ] Documentação de credenciais guardada em local seguro (KeePass, Bitwarden, etc.)

---

## 11. Rollback Rápido

Se algo der errado no update:
```bash
# Para versão anterior (se tiver tag anterior no Git)
cd /opt/helpdesk
git checkout TAG_ANTERIOR
docker compose -p helpdesk build
docker compose -p helpdesk up -d --force-recreate

# Ou restaura backup
sudo ./scripts/restore.sh /mnt/backups/helpdesk/helpdesk_backup_YYYYMMDD_HHMMSS
```

---

**Dica**: Mantenha este guia impresso ou salvo offline para emergências.