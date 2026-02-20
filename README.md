
# 🔍 CMP 인프라 정기점검 시스템

**CMP (Cloud Management Platform) 인프라 자동화 점검 도구**

개발(DEV), 스테이징(STG), 운영(PRD) 환경의 OS, Kubernetes 클러스터, K8s 서비스, CI/CD 인프라, 데이터베이스를 자동으로 점검하고 CSV/DOCX 보고서를 생성합니다.

---

## 📋 목차

- [주요 기능](#-주요-기능)
- [아키텍처](#-아키텍처)
- [점검 항목](#-점검-항목)
- [프로젝트 구조](#-프로젝트-구조)
- [설치](#-설치)
- [설정](#️-설정)
- [사용법](#-사용법)
- [보안](#-보안)
- [Cron 스케줄링](#-cron-스케줄링)

---

## ✨ 주요 기능

| 기능 | 설명 |
|------|------|
| 🖥️ **OS 점검** | 디스크, 메모리, CPU, 프로세스 등 10개 항목 |
| ☸️ **K8s 클러스터 점검** | 노드, Control Plane, etcd, PV/PVC 등 10개 항목 |
| 🚀 **K8s 서비스 점검** | Deployment, StatefulSet, DaemonSet 등 10개 항목 |
| 🔧 **CI/CD 점검** | Jenkins, GitLab, Nexus |
| 🗄️ **DB 점검** | MySQL 연결, Replication 상태 |
| 📊 **보고서 생성** | CSV, DOCX 형식 |
| 🔒 **보안 설계** | IP/Port 정보 별도 파일 관리, SSH 키 인증 |

---

## 🏗️ 아키텍처


```

┌─────────────────────────────────────────────────────────────────┐
│                        CMP 인프라 구성                          │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌──────────────┐   ┌──────────────┐   ┌──────────────┐        │
│  │   CI/CD      │   │    DEV       │   │    STG       │        │
│  │  (Jenkins,   │   │   Cluster    │   │   Cluster    │        │
│  │   GitLab,    │   │ (3M + 3W)    │   │ (3M + 3W)    │        │
│  │   Nexus)     │   │              │   │              │        │
│  └──────────────┘   └──────────────┘   └──────────────┘        │
│                                                                 │
│  ┌──────────────┐   ┌──────────────┐   ┌──────────────┐        │
│  │    PRD       │   │   Database   │   │    NFS       │        │
│  │   Cluster    │   │  (MySQL x2   │   │   Storage    │        │
│  │ (3M + 3W)    │   │  per env)    │   │              │        │
│  └──────────────┘   └──────────────┘   └──────────────┘        │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
│
▼
┌─────────────────────────────────────────────────────────────────┐
│                    점검 시스템 (이 프로젝트)                      │
├─────────────────────────────────────────────────────────────────┤
│  1. SSH로 각 서버 접속하여 OS 점검                               │
│  2. Master 노드에서 kubectl로 K8s 점검                           │
│  3. TCP/HTTP로 서비스 상태 점검                                  │
│  4. 결과 취합 → CSV/DOCX 보고서 생성                             │
└─────────────────────────────────────────────────────────────────┘

```

---

## 📋 점검 항목

### 🖥️ OS 점검 (9개)
| ID | 항목 | 임계치 | 비고 |
|----|------|--------|------|
| OS-001 | 디스크 사용량 | 80% | Root 파티션 |
| OS-002 | 메모리 사용량 | 85% | |
| OS-003 | CPU 사용량 | 90% | |
| OS-004 | 시스템 업타임 | - | |
| OS-005 | 좀비 프로세스 | 0개 | |
| OS-006 | 로드 애버리지 | 8.0 | 1분 평균 |
| OS-007 | 열린 파일 수 | 100,000 | fs.file-nr |
| OS-008 | 네트워크 연결 | 2,000 | Established |
| OS-009 | 커널 버전 | - | |

### ☸️ Kubernetes 클러스터 점검 (7개)
| ID | 항목 | 기준 | 비고 |
|----|------|------|------|
| K8S-001 | 노드 상태 | Ready | |
| K8S-002 | 노드 CPU | 80% | |
| K8S-003 | 노드 메모리 | 80% | |
| K8S-004 | CP Pod 상태 | Running | kube-system |
| K8S-005 | Warning 이벤트 | 50개 | 최근 1시간 |
| K8S-006 | NotReady 노드 | 0개 | |
| K8S-007 | 클러스터 버전 | - | |

### 🚀 K8s 서비스/워크로드 점검 (10개)
| ID | 항목 | 기준 | 비고 |
|----|------|------|------|
| SVC-001 | Deployment | Replica 일치 | |
| SVC-002 | StatefulSet | Replica 일치 | |
| SVC-003 | DaemonSet | Replica 일치 | |
| SVC-004 | Service Endpoints | 연결됨 | |
| SVC-005 | Ingress 상태 | - | 개수 확인 |
| SVC-006 | Pod 재시작 과다 | 15회 미만 | |
| SVC-007 | Pending Pod | 0개 | |
| SVC-008 | Failed Pod | 0개 | |
| SVC-009 | CronJob 상태 | - | 개수 확인 |
| SVC-010 | Failed Job | 0개 | |

### 🔧 인프라 서비스 점검 (CI/CD, DB, Storage)
| 카테고리 | ID | 항목 | 점검 방식 | 기준 |
|----------|----|------|-----------|------|
| **CI/CD** | CICD-001 | Jenkins | HTTP | 200 OK |
| | CICD-002 | GitLab | HTTP | 200 OK |
| | CICD-003 | Nexus | HTTP | 200 OK |
| | CICD-004 | Registry | TCP | Port Open |
| **DB** | DB-001 | MySQL 연결 | TCP | 3306 Open |
| | DB-002 | Replication | Query | Slave Running |
| **Storage**| STG-001 | NFS 마운트 | OS Command | 마운트 확인 |
| | STG-002 | NFS 포트 | TCP | 2049 Open |

### 📱 K8s 애플리케이션 점검
| 카테고리 | ID | 항목 | 기준 (Pod 수) |
|----------|----|------|---------------|
| **ArgoCD** | APP-ARGO-01 | ArgoCD Server | 1개 이상 |
| **Harbor** | APP-HBR-01 | Harbor Core | 1개 이상 |
| | APP-HBR-02 | Harbor Registry | 1개 이상 |
| **Monitoring** | APP-MON-01 | Grafana | 1개 이상 |
| **Logging** | APP-ELK-01 | Elasticsearch | 3개 이상 (Master) |
| | APP-LOKI-01 | Loki Gateway | 1개 이상 |
| | APP-LOKI-02 | Loki R/W | 2개 이상 |
| **Auth** | APP-KEY-01 | Keycloak | 1개 이상 |
| **Middleware** | APP-RABBIT-01 | RabbitMQ | 1개 이상 |
| **CICD** | APP-SONAR-01 | SonarQube | 1개 이상 |
| **Ingress** | APP-TRAEFIK-01 | Traefik | 1개 이상 |

---

## 📁 프로젝트 구조


```

cmp-infra-check/
│
├── 📄 cmp-infra-check.sh       # 메인 실행 스크립트
├── 📄 README.md                # 프로젝트 문서
│
├── 📁 config/                  # 설정 파일
│   ├── 📄 inventory.yaml       # 🔒 IP/Port 정보
│   ├── 📄 dev-inventory.yaml   # DEV 클러스터 정보
│   ├── 📄 stg-inventory.yaml   # STG 클러스터 정보
│   ├── 📄 prd-inventory.yaml   # PRD 클러스터 정보
│   └── 📄 check_items.yaml     # 점검 항목 정의
│
├── 📁 scripts/                 # Python 스크립트
│   ├── 📄 main.py              # 메인 실행 스크립트
│   ├── 📄 checker.py           # 점검 로직
│   ├── 📄 ssh_executor.py      # SSH 연결 모듈
│   └── 📄 report_generator.py  # 보고서 생성
│
└──  📁 output/                  # 보고서 출력

```

---

## 🚀 설치

### 1. 실행 권한 부여

```bash
chmod +x cmp-infra-check.sh

```

### 2. Python 의존성 설치

```bash
pip3 install pyyaml python-docx

```

---

## ⚙️ 설정

### config/inventory.yaml (보안 중요!)

```yaml
# CI/CD 서버
cicd_servers:
  jenkins_primary:
    name: "Jenkins #1"
    hostname: "scsic-ishpjenkins1"
    ip: "10.x.x.x"        # 실제 IP
    ssh_port: xx
    services:
      - name: "Jenkins"
        port: 8080

# 개발 클러스터
dev_cluster:
  name: "개발 클러스터"
  env: "DEV"
  masters:
    - name: "Master #1"
      hostname: "scsic-dicmpmst1"
      ip: "10.x.x.x"
      ssh_port: xx
  workers:
    - name: "Worker #1"
      hostname: "scsic-dicmpwok1"
      ip: "10.x.x.x"
      ssh_port: xx
  databases:
    - name: "DB #1"
      hostname: "scsic-dicmpdb1"
      ip: "10.x.x.x"
      services:
        - name: "MySQL"
          port: xxxx

# SSH 설정
ssh_config:
  private_key_path: "~/.ssh/id_rsa"
  default_user: "admin"
  connect_timeout: 10

# 보고서 설정
report:
  company_name: "CMP 인프라"
  team_name: "클라우드서비스팀"
  output_dir: "./output"

```

---

## 📖 사용법

### 기본 명령어

```bash
# 도움말
./cmp-infra-check.sh --help

# 기본 실행 (주간 보고서)
./cmp-infra-check.sh

# 월간 보고서
./cmp-infra-check.sh --type monthly

# 특정 환경만 점검
./cmp-infra-check.sh --env prd

```

### Python 직접 실행

```bash
cd scripts
python3 main.py
python3 main.py --type monthly

```

---

## 🔒 보안

### 권장 사항

1. **inventory.yaml을 .gitignore에 추가**
```gitignore
config/inventory.yaml
config/secrets.yaml

```


2. **환경변수로 민감 정보 관리**
```bash
export SSH_USER="admin"
export SSH_PRIVATE_KEY_PATH="/secure/path/id_rsa"
export CMP_INVENTORY_PATH="/secure/config/inventory.yaml"

```


3. **SSH 키 권한 설정**
```bash
chmod 600 ~/.ssh/id_rsa
chmod 700 ~/.ssh

```


4. **보고서 파일 보안**
* 보고서에 IP 주소 등 민감 정보가 포함될 수 있음
* output/ 디렉토리 접근 권한 제한



### 파일 권한 예시

```bash
chmod 600 config/inventory.yaml
chmod 644 config/check_items.yaml
chmod 755 cmp-infra-check.sh
chmod 700 logs/

```

---

## ⏰ Cron 스케줄링

### 주간 점검 (매주 월요일 09:00)

```bash
0 9 * * 1 /path/to/cmp-infra-check/cmp-infra-check.sh >> /var/log/cmp-check.log 2>&1

```

### 월간 점검 (매월 1일 09:00)

```bash
0 9 1 * * /path/to/cmp-infra-check/cmp-infra-check.sh --type monthly >> /var/log/cmp-check-monthly.log 2>&1

```

### 환경변수 포함

```bash
0 9 * * 1 SSH_USER=admin SSH_PRIVATE_KEY_PATH=/home/admin/.ssh/id_rsa /path/to/cmp-infra-check.sh >> /var/log/cmp-check.log 2>&1

```

---

## 📊 출력 예시

### 콘솔 출력

```
================================================================
🔍 CMP 인프라 정기점검 시작
   보고서 유형: weekly
   회사: CMP 인프라
   담당팀: 클라우드서비스팀
   점검 환경: ALL
================================================================

📋 CI/CD 서비스 점검 중...
📋 개발 클러스터(DEV) 점검 중...
📋 스테이징 클러스터(STG) 점검 중...
📋 운영 클러스터(PRD) 점검 중...

======================================================================
📊 점검 결과 요약
======================================================================
  총 점검항목: 180
  ✅ 정상: 175
  ⚠️ 경고: 3
  ❌ 위험: 0
  ❓ 확인불가: 2
======================================================================

📂 환경별 결과:
  DEV: ✅58 ⚠️1 ❌0 ❓1
  STG: ✅59 ⚠️1 ❌0 ❓0
  PRD: ✅58 ⚠️1 ❌0 ❓1

📝 보고서 생성 중...
✅ 보고서 생성 완료:
   - CSV: ./output/cmp_infra_check_2025_W49.csv
   - DOCX: ./output/cmp_infra_check_2025_W49.docx