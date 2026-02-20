
# 🔍 CMP 인프라 정기점검 시스템

**CMP (Cloud Management Platform) 인프라 자동화 점검 도구**

개발(DEV), 스테이징(STG), 운영(PRD) 환경의 OS, Kubernetes 클러스터, K8s 서비스, CI/CD 인프라, 데이터베이스를 자동으로 점검하고 CSV/DOCX 보고서를 생성합니다. **단일 인벤토리 파일(`config/inventory.yaml`)을 사용하며, 실행 시 `--cluster` 또는 `--env` 인자로 점검 대상 클러스터를 지정합니다.**

---

## 📋 목차

- [주요 기능](#-주요-기능)
- [아키텍처](#-아키텍처)
- [점검 항목](#-점검-항목)
- [프로젝트 구조](#-프로젝트-구조)
- [설치](#-설치)
- [설정](#️-설정)
- [명령어 인자 (CLI 옵션)](#-명령어-인자-cli-옵션)
- [사용법 및 클러스터별 실행](#-사용법-및-클러스터별-실행)
- [SSL 인증서 도메인 설정](#-ssl-인증서-도메인-설정)
- [사용 시 알아야 할 내용](#-사용-시-알아야-할-내용)
- [보안](#-보안)
- [Cron 스케줄링](#-cron-스케줄링)
- [주간 보고용 수정 사항 요약](#-주간-보고용-수정-사항-요약)

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
├── 📄 cmp-infra-check.sh       # 메인 실행 스크립트 (진입점)
├── 📄 README.md                 # 프로젝트 문서
│
├── 📁 config/                   # 설정 파일
│   ├── 📄 inventory.yaml        # 🔒 단일 인벤토리 (전 클러스터 + CI/CD + SSH/보고서 설정)
│   └── 📄 check_items.yaml      # 점검 항목 정의
│
├── 📁 scripts/                  # Python 스크립트
│   ├── 📄 main.py               # 메인 실행 및 인자 처리
│   ├── 📄 checker.py            # 점검 로직
│   ├── 📄 ssh_executor.py       # SSH 연결 모듈
│   └── 📄 report_generator.py   # CSV/DOCX 보고서 생성
│
└── 📁 output/                   # 보고서 출력 (CSV, DOCX)
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

### config/inventory.yaml (단일 인벤토리, 보안 중요!)

모든 클러스터·CI/CD·SSH·보고서 설정은 **한 파일(`config/inventory.yaml`)에만** 정의합니다. 클러스터별로 파일을 나누지 않습니다.

| 섹션 | 설명 |
|------|------|
| `cicd_servers` | Jenkins, GitLab, Nexus 등 CI/CD 서버 목록 |
| `dev_cluster` / `stg_cluster` / `prd_cluster` | 각 환경별 클러스터(masters, workers, bastion, databases 등) |
| `ssh_config` | SSH 키 경로, 사용자, 타임아웃 (전역) |
| `report` | 회사명, 담당팀, 출력 디렉토리, (선택) SSL 도메인 목록 |

최소 구성 예:

```yaml
# CI/CD 서버
cicd_servers:
  jenkins_primary:
    name: "Jenkins #1"
    hostname: "scsic-ishpjenkins1"
    ip: "10.x.x.x"
    ssh_port: 22
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
      ssh_port: 22
  workers: [ ... ]
  bastion: { name: "Bastion", hostname: "...", ip: "...", ssh_port: 22 }
  databases: [ ... ]
  k8s_api_port: 443

# 스테이징/운영 클러스터도 동일 구조로 dev_cluster, stg_cluster, prd_cluster 키로 정의

# SSH 설정 (전역)
ssh_config:
  private_key_path: "~/.ssh/id_rsa"
  default_user: "admin"
  connect_timeout: 10
  command_timeout: 30

# 보고서 설정
report:
  company_name: "CMP 인프라"
  team_name: "클라우드서비스팀"
  output_dir: "./output"
  # ssl_domains: [ "your-app.example.com" ]   # SSL 점검 대상 도메인 (선택)
```

---

## 📖 명령어 인자 (CLI 옵션)

스크립트(`cmp-infra-check.sh`)는 아래 옵션을 지원하며, `-c`/`--cluster`·`-t`·`-e`·`-o` 등은 내부적으로 Python 스크립트로 전달됩니다.

| 옵션 | 설명 | 기본값 |
|------|------|--------|
| `-c`, `--cluster <클러스터명>` | 점검할 클러스터. 복수 지정 가능 (예: `-c dev_cluster -c stg_cluster`). 지정 시 `--env` 무시 | 없음 |
| `-t`, `--type <weekly\|monthly>` | 보고서 유형 | `weekly` |
| `-e`, `--env <dev\|stg\|prd\|all>` | 점검할 환경. `--cluster` 미지정 시에만 사용 | `all` |
| `-o`, `--output-dir <경로>` | 보고서 출력 디렉토리 | `./output` |
| `--json` | 결과를 JSON으로만 출력 (보고서 파일 미생성) | - |
| `-q`, `--quiet` | 최소 출력 | - |
| `-h`, `--help` | 도움말 표시 | - |

- **클러스터명**: `dev_cluster`, `stg_cluster`, `prd_cluster` (인벤토리 키와 동일).
- **점검 환경 표시**: `--cluster`로 실행 시 화면에는 "점검 환경: DEV_CLUSTER"처럼 지정한 클러스터명이, `--env dev` 등으로 실행 시 "점검 환경: DEV"처럼 표시됩니다.

---

## 📖 사용법 및 클러스터별 실행

### 기본 실행

```bash
# 도움말
./cmp-infra-check.sh --help

# 전체 클러스터 점검 (주간 보고서)
./cmp-infra-check.sh

# 월간 보고서
./cmp-infra-check.sh --type monthly

# 특정 환경만 점검 (--env)
./cmp-infra-check.sh --env prd
./cmp-infra-check.sh --env dev
```

### 클러스터별 실행 (Bastion에서 권장)

각 클러스터 Bastion에 SSH 접속한 뒤, **해당 클러스터만** 점검하려면 `--cluster`를 사용합니다. 실행 로그에 "점검 환경: DEV_CLUSTER"처럼 어떤 클러스터를 점검 중인지 명확히 나옵니다.

```bash
# 개발(DEV) Bastion에서 실행
./cmp-infra-check.sh --cluster dev_cluster

# 스테이징(STG) Bastion에서 실행
./cmp-infra-check.sh --cluster stg_cluster

# 운영(PRD) Bastion에서 실행
./cmp-infra-check.sh --cluster prd_cluster

# 복수 클러스터 지정 (해당 Bastion에서 두 클러스터 모두 접근 가능한 경우)
./cmp-infra-check.sh --cluster dev_cluster --cluster stg_cluster
```

### 기타 예시

```bash
# 최소 출력 + JSON만
./cmp-infra-check.sh -q --json

# 출력 디렉토리 지정
./cmp-infra-check.sh -o /var/reports/cmp-check
```

### Python 직접 실행

```bash
cd scripts
python3 main.py
python3 main.py --type monthly
python3 main.py --cluster dev_cluster --cluster prd_cluster
python3 main.py --env stg -o ./output
```

Python에서 사용 가능한 인자: `--inventory`(기본 `config/inventory.yaml`), `--checks`, `--type`, `--output-dir`, `--env`, `--cluster`, `--json`, `--quiet`.

---

## 🔐 SSL 인증서 도메인 설정

SSL 인증서 만료일 점검 대상을 **인벤토리에서 도메인 목록으로 지정**할 수 있습니다. 설정하지 않으면 기본 도메인(예: google.com, example.com)만 점검됩니다.

### 1) report.ssl_domains (권장)

`config/inventory.yaml`의 `report` 섹션에 `ssl_domains`를 추가합니다.

```yaml
report:
  company_name: "CMP 인프라"
  team_name: "클라우드서비스팀"
  output_dir: "./output"
  ssl_domains:
    - "your-app.example.com"
    - "api.example.com"
    - "grafana.internal.example.com"
```

### 2) 최상위 ssl_domains

`report` 밑이 아니라 인벤토리 **최상위**에 두는 방식도 지원합니다.

```yaml
# inventory.yaml 최상위
ssl_domains:
  - "your-app.example.com"
  - "api.example.com"
```

- **우선순위**: 인벤토리에서 `ssl_domains`를 먼저 찾고, 없으면 `report.ssl_domains`를 사용합니다.
- **치환**: 도메인 문자열은 그대로 점검에 사용됩니다. 환경변수 치환(예: `${DOMAIN}`)은 인벤토리 로드 시 적용되므로, 필요하면 `ssl_domains: ["${APP_DOMAIN}"]` 형태로 설정하고 실행 전에 `export APP_DOMAIN=your-app.example.com` 등으로 지정할 수 있습니다.

---

## 📌 사용 시 알아야 할 내용

1. **실행 위치**  
   - OS·K8s 점검은 **스크립트가 실행되는 호스트**에서 SSH·kubectl을 실행합니다.  
   - **각 클러스터만 점검할 때는 해당 클러스터 Bastion에 접속한 뒤**, 그 Bastion에서 `./cmp-infra-check.sh --cluster <해당_클러스터>` 로 실행하는 구성을 권장합니다. (같은 대역에서 직접 SSH 접속이 되는 환경 전제.)

2. **인벤토리**  
   - 모든 클러스터·CI/CD·SSH·보고서 설정은 **`config/inventory.yaml` 한 파일**에만 둡니다.  
   - 클러스터 키 이름(`dev_cluster`, `stg_cluster`, `prd_cluster`)과 `--cluster` 인자 값은 동일해야 합니다.

3. **보고서**  
   - CSV/DOCX는 기본적으로 `output/` 아래에 `cmp_infra_check_YYYY_Wnn.csv`(주간) 또는 `cmp_infra_check_YYYY_MM.docx`(월간) 형식으로 생성됩니다.  
   - `--output-dir`로 경로를 바꿀 수 있습니다.

4. **환경변수**  
   - `SSH_USER`, `SSH_PRIVATE_KEY_PATH`, `CMP_INVENTORY_PATH` 등으로 SSH·인벤토리 경로를 오버라이드할 수 있습니다. (보안 섹션 참고.)

5. **종료 코드**  
   - `0`: 정상, `1`: 경고 있음, `2`: 위험 있음. Cron/스크립트에서 결과에 따른 후속 처리에 활용할 수 있습니다.

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

### 클러스터별 Bastion에서 주간 점검 (예시)

```bash
# 각 Bastion에 cron 설정: 해당 클러스터만 점검
0 9 * * 1 /path/to/cmp-infra-check.sh --cluster dev_cluster >> /var/log/cmp-check-dev.log 2>&1
0 9 * * 1 /path/to/cmp-infra-check.sh --cluster prd_cluster >> /var/log/cmp-check-prd.log 2>&1
```

---

## 📋 주간 보고용 수정 사항 요약

- **단일 인벤토리 구조**: 클러스터별 파일(예: gpu-inventory.yaml, dev-inventory.yaml 등) 제거, `config/inventory.yaml` 한 파일로 통합.
- **클러스터 지정 방식**: 실행 시 `-c`/`--cluster` 인자로 점검 대상 클러스터 지정 가능. 복수 클러스터 지정 및 `-e`/`--env`(dev/stg/prd/all) 유지.
- **점검 환경 표시**: `--cluster` 사용 시 로그에 점검 대상 클러스터명(예: DEV_CLUSTER) 표시되도록 개선.
- **SSL 인증서 도메인 설정**: 인벤토리 `report.ssl_domains` 또는 최상위 `ssl_domains`로 점검 대상 도메인 목록 설정 가이드 및 지원.
- **문서 정비**: README에 명령어 인자 전체 정리, 클러스터별 실행 예시, SSL 도메인 설정 방법, 사용 시 유의사항 반영.

---

## 📊 출력 예시

### 콘솔 출력 (전체 점검 시)

```
======================================================================
🔍 CMP 인프라 정기점검 시작
   보고서 유형: weekly
   회사: CMP 인프라
   담당팀: 클라우드서비스팀
   점검 환경: ALL
======================================================================

📋 CI/CD 서비스 점검 중...
📋 SSL 인증서 점검 중...
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
```

`--cluster dev_cluster`로 실행한 경우 상단 "점검 환경"에는 `DEV_CLUSTER`처럼 지정한 클러스터명이 표시됩니다.