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
| 🔧 **CI/CD 점검** | Jenkins, GitLab, Nexus, Docker Registry |
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

### 🖥️ OS 점검 (10개)
| ID | 항목 | 임계치 |
|----|------|--------|
| OS-001 | 디스크 사용량 | 80% |
| OS-002 | 메모리 사용량 | 85% |
| OS-003 | CPU 사용량 | 90% |
| OS-004 | 시스템 업타임 | - |
| OS-005 | 좀비 프로세스 | 0 |
| OS-006 | 로드 애버리지 | 8.0 |
| OS-007 | Swap 사용량 | 50% |
| OS-008 | 열린 파일 수 | 100,000 |
| OS-009 | 네트워크 연결 | 2,000 |
| OS-010 | 커널 버전 | - |

### ☸️ Kubernetes 클러스터 점검 (10개)
| ID | 항목 | 기준 |
|----|------|------|
| K8S-001 | 노드 상태 | Ready |
| K8S-002 | 노드 CPU | 80% |
| K8S-003 | 노드 메모리 | 80% |
| K8S-004 | Control Plane Pod | Running |
| K8S-005 | etcd 상태 | Running |
| K8S-006 | PV 상태 | Bound |
| K8S-007 | PVC 상태 | Bound |
| K8S-008 | Warning 이벤트 | 50개 |
| K8S-009 | NotReady 노드 | 0 |
| K8S-010 | 클러스터 버전 | - |

### 🚀 K8s 서비스 점검 (10개)
| ID | 항목 | 기준 |
|----|------|------|
| SVC-001 | Deployment | Replica 일치 |
| SVC-002 | StatefulSet | Replica 일치 |
| SVC-003 | DaemonSet | Replica 일치 |
| SVC-004 | Service Endpoints | 0 |
| SVC-005 | Ingress | - |
| SVC-006 | Pod 재시작 과다 (15회+) | 0 |
| SVC-007 | Pending Pod | 0 |
| SVC-008 | Failed Pod | 0 |
| SVC-009 | CronJob | - |
| SVC-010 | Failed Job | 0 |

---

## 📁 프로젝트 구조


```

cmp-infra-check/
│
├── 📄 cmp-infra-check.sh       # 메인 실행 스크립트
├── 📄 README.md                # 프로젝트 문서
├── 📄 .gitignore               # Git 제외 파일
│
├── 📁 config/                  # 설정 파일 (보안 주의!)
│   ├── 📄 inventory.yaml       # 🔒 IP/Port 정보 (gitignore 권장)
│   ├── 📄 inventory.yaml.example  # 인벤토리 예시
│   └── 📄 check_items.yaml     # 점검 항목 정의
│
├── 📁 scripts/                 # Python 스크립트
│   ├── 📄 main.py              # 메인 실행 스크립트
│   ├── 📄 checker.py           # 점검 로직
│   ├── 📄 ssh_executor.py      # SSH 연결 모듈
│   └── 📄 report_generator.py  # 보고서 생성
│
├── 📁 output/                  # 보고서 출력
│   └── 📄 .gitkeep
│
└── 📁 logs/                    # 로그 파일
└── 📄 .gitkeep

```

---

## 🚀 설치

### 1. 저장소 클론

```bash
git clone [https://github.com/your-org/cmp-infra-check.git](https://github.com/your-org/cmp-infra-check.git)
cd cmp-infra-check

```

### 2. 실행 권한 부여

```bash
chmod +x cmp-infra-check.sh

```

### 3. Python 의존성 설치

```bash
pip3 install pyyaml python-docx

```

### 4. 인벤토리 설정

```bash
# 예시 파일 복사
cp config/inventory.yaml.example config/inventory.yaml

# 실제 IP/Port 정보 입력
vi config/inventory.yaml

```

### 5. SSH 키 설정

```bash
# SSH 키 권한 설정
chmod 600 ~/.ssh/id_rsa

# 환경변수 설정 (선택)
export SSH_USER="admin"
export SSH_PRIVATE_KEY_PATH="~/.ssh/id_rsa"

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
  team_name: "플랫폼팀"
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
   담당팀: 플랫폼팀
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

```

---

## 📝 종료 코드

| 코드 | 의미 |
| --- | --- |
| 0 | 모든 항목 정상 |
| 1 | 경고 항목 있음 |
| 2 | 위험 항목 있음 |

---

## 🤝 기여

1. Fork the repository
2. Create feature branch
3. Commit changes
4. Push to branch
5. Open Pull Request

---

## 📄 라이선스

MIT License